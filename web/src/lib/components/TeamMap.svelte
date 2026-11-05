<script lang="ts">
	import { signed } from '$lib/format';
	import { divergeColor, divergeMax, type Pins } from '$lib/rankings';
	import type { TeamMap } from '$lib/types';

	// Every team as a dot placed by the model's team embedding (UMAP to 2-D),
	// filled by average margin on a diverging scale. Teams close together are
	// ones the model represents alike. Hover finds the nearest dot; click
	// highlights it (the same highlights as the line chart).
	let {
		map,
		pins,
		visible = null,
		ontoggle
	}: {
		map: TeamMap;
		pins: Pins;
		/** Teams to emphasize (null: all); the rest fade. */
		visible?: Set<string> | null;
		ontoggle: (team: string) => void;
	} = $props();

	let width = $state(760);
	const W = $derived(Math.max(300, Math.round(width)));
	const narrow = $derived(W < 560);
	const H = $derived(narrow ? 340 : 440);
	const PAD = 28;
	const R = $derived(map.points.length > 100 ? 4.5 : 6);

	// equal scale on both axes (UMAP distances mean the same either way)
	const scale = $derived(Math.min(W - 2 * PAD, H - 2 * PAD) / 2);
	const px = (x: number) => W / 2 + x * scale;
	const py = (y: number) => H / 2 - y * scale;

	const max = $derived(divergeMax(map.points.map((p) => p.rating)));
	const ranks = $derived(
		new Map(
			[...map.points].sort((a, b) => b.rating - a.rating).map((p, i) => [p.team.team, i + 1])
		)
	);
	const isVisible = (team: string) => !visible || visible.has(team);
	// faded teams first, then the rest, highlighted ones on top
	const order = $derived(
		[...map.points].sort(
			(a, b) =>
				Number(isVisible(a.team.team)) - Number(isVisible(b.team.team)) ||
				Number(a.team.team in pins) - Number(b.team.team in pins)
		)
	);

	// labels for highlighted teams, or every team when only a few are shown
	const LABEL_ALL = 12;
	const labelled = $derived.by(() => {
		const shown = map.points.filter((p) => isVisible(p.team.team));
		const pick = shown.length <= LABEL_ALL ? shown : shown.filter((p) => p.team.team in pins);
		return pick.map((p) => ({
			key: p.team.team,
			text: p.team.abbr ?? p.team.team,
			x: px(p.x),
			y: py(p.y),
			right: px(p.x) < W - 90
		}));
	});

	let hover = $state<string | null>(null);
	const hovered = $derived(map.points.find((p) => p.team.team === hover) ?? null);
	let svg: SVGSVGElement;

	function locate(event: PointerEvent) {
		const box = svg.getBoundingClientRect();
		const mx = ((event.clientX - box.left) / box.width) * W;
		const my = ((event.clientY - box.top) / box.height) * H;
		let nearest: string | null = null;
		let distance = 20;
		for (const p of map.points) {
			if (!isVisible(p.team.team)) continue;
			const d = Math.hypot(px(p.x) - mx, py(p.y) - my);
			if (d < distance) [nearest, distance] = [p.team.team, d];
		}
		hover = nearest;
	}

	const tipLeft = $derived(hovered ? (px(hovered.x) / W) * 100 : 0);
	const tipTop = $derived(hovered ? (py(hovered.y) / H) * 100 : 0);
</script>

<div
	class="map"
	bind:clientWidth={width}
	onpointermove={locate}
	onpointerdown={locate}
	onpointerleave={() => (hover = null)}
	onclick={() => hover && ontoggle(hover)}
	role="presentation"
	class:pointing={hover !== null}
>
	<svg
		bind:this={svg}
		viewBox="0 0 {W} {H}"
		role="img"
		aria-label="Teams placed by how alike the model sees them, colored by average predicted margin"
	>
		{#each order as p (p.team.team)}
			{@const slot = pins[p.team.team]}
			<circle
				class="dot"
				class:faded={!isVisible(p.team.team)}
				class:hovered={p.team.team === hover}
				cx={px(p.x)}
				cy={py(p.y)}
				r={slot || p.team.team === hover ? R + 1.5 : R}
				style:fill={divergeColor(p.rating, max)}
			/>
			{#if slot}
				<circle class="pin" cx={px(p.x)} cy={py(p.y)} r={R + 4.5} style:stroke="var(--series-{slot})" />
			{/if}
		{/each}
		{#each labelled as l (l.key)}
			<text
				class="label"
				class:pinned={l.key in pins}
				x={l.right ? l.x + R + 7 : l.x - R - 7}
				y={l.y}
				text-anchor={l.right ? 'start' : 'end'}
				dominant-baseline="middle">{l.text}</text
			>
		{/each}
	</svg>

	{#if hovered}
		<div class="tooltip" style:left="{tipLeft}%" style:top="{tipTop}%" class:flip={tipLeft > 60}>
			<div class="tip-head">{hovered.team.name}</div>
			<div class="tip-row">
				<span class="dot-key" style:background={divergeColor(hovered.rating, max)}></span>
				<span>#{ranks.get(hovered.team.team)} · avg margin</span>
				<span class="tabular">{signed(hovered.rating)}</span>
			</div>
			<div class="tip-hint">{hovered.team.team in pins ? 'Click to stop highlighting' : 'Click to highlight'}</div>
		</div>
	{/if}

	<div class="scale" aria-hidden="true">
		<span class="tabular">{signed(-max, 0)}</span>
		<span
			class="ramp"
			style:background="linear-gradient(to right, var(--diverge-neg), var(--diverge-mid), var(--diverge-pos))"
		></span>
		<span class="tabular">{signed(max, 0)}</span>
		<span class="muted">avg margin</span>
	</div>
</div>

<style>
	.map {
		position: relative;
	}
	.map.pointing {
		cursor: pointer;
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
		touch-action: pan-y;
	}
	.dot {
		stroke: var(--surface);
		stroke-width: 1.5;
		transition: opacity 120ms;
	}
	.dot.faded {
		opacity: 0.18;
	}
	.dot.hovered {
		stroke: var(--text);
		stroke-width: 2;
	}
	.pin {
		fill: none;
		stroke-width: 2.5;
	}
	.label {
		fill: var(--muted);
		font-size: 12px;
		font-weight: 500;
		paint-order: stroke;
		stroke: var(--surface);
		stroke-width: 3px;
		stroke-linejoin: round;
		pointer-events: none;
	}
	.label.pinned {
		fill: var(--text);
		font-weight: 600;
	}
	.tooltip {
		position: absolute;
		transform: translate(14px, -50%);
		pointer-events: none;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow);
		padding: 8px 10px;
		font-size: 0.8rem;
		min-width: 160px;
	}
	.tooltip.flip {
		transform: translate(calc(-100% - 14px), -50%);
	}
	.tip-head {
		font-weight: 600;
		margin-bottom: 4px;
	}
	.tip-row {
		display: grid;
		grid-template-columns: auto 1fr auto;
		gap: 6px;
		align-items: center;
	}
	.dot-key {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}
	.tip-hint {
		color: var(--muted);
		margin-top: 4px;
	}
	.scale {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.8rem;
		color: var(--muted);
		margin-top: 4px;
	}
	.ramp {
		width: 140px;
		height: 8px;
		border-radius: 4px;
	}
</style>
