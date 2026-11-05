<script lang="ts">
	import { dateText } from '$lib/format';
	import { divergeColor, type Pins } from '$lib/rankings';
	import {
		centerAt,
		extent,
		formatMetric,
		goodness,
		positionAt,
		ranksAt,
		recordText,
		spread,
		valueAt
	} from '$lib/teammap';
	import type { TeamMap, TeamMapMetric } from '$lib/types';
	import { onDestroy } from 'svelte';

	// Every team as a dot placed by the model's team embedding (UMAP to 2-D),
	// filled by the chosen metric on a worse-to-better scale. The timeline
	// (or play) moves every team to where it stood before that date;
	// highlighted teams draw their path so far.
	let {
		map,
		metric,
		pins,
		visible = null,
		dateLabel = 'Week',
		frame = $bindable(0),
		ontoggle
	}: {
		map: TeamMap;
		metric: TeamMapMetric;
		pins: Pins;
		/** Teams to emphasize (null: all); the rest fade. */
		visible?: Set<string> | null;
		dateLabel?: string;
		/** Fractional date index shown. */
		frame?: number;
		ontoggle: (team: string) => void;
	} = $props();

	let width = $state(760);
	const W = $derived(Math.max(300, Math.round(width)));
	const narrow = $derived(W < 560);
	const H = $derived(narrow ? 360 : 480);
	const PAD = 24;
	const SIDE = $derived(narrow ? 12 : 40);
	const R = $derived(map.teams.length > 100 ? 4.5 : 6.5);

	// every team's every position fitted to the plot, equal scale on both axes
	const box = $derived(extent(map.teams));
	const scale = $derived(
		Math.min((W - 2 * PAD - 2 * SIDE) / Math.max(box.x1 - box.x0, 1e-6), (H - 2 * PAD) / Math.max(box.y1 - box.y0, 1e-6))
	);
	const px = (x: number) => W / 2 + (x - (box.x0 + box.x1) / 2) * scale;
	const py = (y: number) => H / 2 - (y - (box.y0 + box.y1) / 2) * scale;

	const last = $derived(map.dates.length - 1);
	const shown = $derived(Math.round(frame));
	const rating = $derived(map.metrics.find((m) => m.key === 'rating') ?? metric);
	// the color scale: centered per date, its width fixed for the season
	const half = $derived(spread(metric, map.teams));
	const center = $derived(centerAt(metric, map.teams, shown));
	const colorOf = (v: number | null) => (v === null ? 'var(--diverge-mid)' : divergeColor(goodness(metric, v, center, half), 1));
	const ranks = $derived(ranksAt(map.teams, shown, metric));
	const isVisible = (team: string) => !visible || visible.has(team);

	const dots = $derived(
		map.teams
			.map((t) => {
				const p = positionAt(t, frame);
				if (!p) return null;
				const slot = pins[t.team.team] as number | undefined;
				const faded = !isVisible(t.team.team);
				return { key: t.team.team, series: t, x: px(p[0]), y: py(p[1]), value: valueAt(t, metric.key, frame), faded, slot };
			})
			.filter((d) => d !== null)
			// faded teams first, highlighted ones on top
			.sort((a, b) => Number(!a.faded) - Number(!b.faded) || Number(!!a.slot) - Number(!!b.slot))
	);

	let hover = $state<string | null>(null);
	const hovered = $derived(dots.find((d) => d.key === hover) ?? null);

	// paths so far for highlighted teams and the hovered one
	const trails = $derived(
		map.teams
			.filter((t) => t.team.team in pins || t.team.team === hover)
			.map((t) => {
				const points: { x: number; y: number }[] = [];
				for (let i = 0; i <= Math.floor(frame); i++) {
					const p = t.positions[i];
					if (p) points.push({ x: px(p[0]), y: py(p[1]) });
				}
				const now = positionAt(t, frame);
				if (now) points.push({ x: px(now[0]), y: py(now[1]) });
				return {
					key: t.team.team,
					slot: pins[t.team.team] as number | undefined,
					d: points.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(''),
					stops: points.slice(0, -1)
				};
			})
	);

	// labels: highlighted teams, or every team when only a few are shown;
	// a label overlapping one above it moves below it
	const LABEL_ALL = 12;
	const CHAR_W = 7;
	const labels = $derived.by(() => {
		const shownDots = dots.filter((d) => !d.faded);
		const pick = shownDots.length <= LABEL_ALL ? shownDots : shownDots.filter((d) => d.slot);
		const out = pick
			.map((d) => {
				const text = d.series.team.abbr ?? d.series.team.team;
				const right = d.x < W - 90;
				const x = right ? d.x + R + 7 : d.x - R - 7;
				return { key: d.key, text, x, right, at: d.y, pinned: !!d.slot, span: [right ? x : x - text.length * CHAR_W, right ? x + text.length * CHAR_W : x] };
			})
			.sort((a, b) => a.at - b.at);
		for (let i = 1; i < out.length; i++)
			for (let j = 0; j < i; j++) {
				const overlaps = out[j].span[0] < out[i].span[1] && out[i].span[0] < out[j].span[1] && Math.abs(out[i].at - out[j].at) < 14;
				if (overlaps) {
					out[i].at = out[j].at + 14;
					j = -1;
				}
			}
		return out;
	});

	// ---- playback
	let playing = $state(false);
	let speed = $state(1);
	let raf = 0;
	let before = 0;
	const SECONDS_PER_DATE = 0.9;
	function tick(now: number) {
		const dt = before ? Math.min(0.1, (now - before) / 1000) : 0;
		before = now;
		frame = Math.min(last, frame + (dt * speed) / SECONDS_PER_DATE);
		if (frame >= last) playing = false;
		raf = playing ? requestAnimationFrame(tick) : 0;
		if (!raf) before = 0;
	}
	$effect(() => {
		if (playing && !raf) raf = requestAnimationFrame(tick);
	});
	onDestroy(() => cancelAnimationFrame(raf));
	function play() {
		if (playing) {
			playing = false;
			return;
		}
		if (frame >= last) frame = 0;
		playing = true;
	}

	// ---- pointer: hover finds the nearest dot, a click highlights it
	let svg: SVGSVGElement;
	function nearest(event: PointerEvent): string | null {
		const box = svg.getBoundingClientRect();
		const x = ((event.clientX - box.left) / box.width) * W;
		const y = ((event.clientY - box.top) / box.height) * H;
		let found: string | null = null;
		let distance = 18;
		for (const d of dots) {
			if (d.faded) continue;
			const gap = Math.hypot(d.x - x, d.y - y);
			if (gap < distance) [found, distance] = [d.key, gap];
		}
		return found;
	}

	function key(event: KeyboardEvent) {
		if (event.key === 'ArrowLeft') frame = Math.max(0, Math.round(frame) - 1);
		else if (event.key === 'ArrowRight') frame = Math.min(last, Math.round(frame) + 1);
		else if (event.key === ' ') play();
		else return;
		event.preventDefault();
	}

	const dateAt = (i: number) => dateText(dateLabel, map.dates[i], map.date_names?.[i]);
	const tipLeft = $derived(hovered ? (hovered.x / W) * 100 : 0);
	const tipTop = $derived(hovered ? (hovered.y / H) * 100 : 0);
	// legend ends, worse on the left: for lower-is-better metrics the high value
	const worse = $derived(metric.higher_is_better ? center - half : center + half);
	const better = $derived(metric.higher_is_better ? center + half : center - half);
</script>

<div class="viewer">
	<div
		class="stage"
		bind:clientWidth={width}
		role="slider"
		tabindex="0"
		aria-roledescription="team map"
		aria-label="Teams placed by how alike the model sees them, colored by {metric.label.toLowerCase()}. Left and right arrows step through {dateLabel.toLowerCase()}s, space plays."
		aria-valuemin={0}
		aria-valuemax={last}
		aria-valuenow={shown}
		aria-valuetext="Before {dateAt(shown)}"
		onpointermove={(e) => (hover = nearest(e))}
		onpointerdown={(e) => (hover = nearest(e))}
		onpointerleave={() => (hover = null)}
		onclick={() => hover && ontoggle(hover)}
		onkeydown={key}
		class:pointing={hover !== null}
	>
		<svg bind:this={svg} viewBox="0 0 {W} {H}" aria-hidden="true">
			{#each trails as t (t.key)}
				<path class="trail-halo" d={t.d} />
				<path class="trail" d={t.d} style:stroke={t.slot ? `var(--series-${t.slot})` : 'var(--text)'} />
				{#each t.stops as s, i (i)}
					<circle class="stop" cx={s.x} cy={s.y} r="2.25" style:fill={t.slot ? `var(--series-${t.slot})` : 'var(--text)'} />
				{/each}
			{/each}
			{#each dots as d (d.key)}
				<circle
					class="dot"
					class:faded={d.faded}
					class:hovered={d.key === hover}
					cx={d.x}
					cy={d.y}
					r={d.slot || d.key === hover ? R + 1.5 : R}
					style:fill={colorOf(d.value)}
				/>
				{#if d.slot}
					<circle class="pin" cx={d.x} cy={d.y} r={R + 5} style:stroke="var(--series-{d.slot})" />
				{/if}
			{/each}
			{#each labels as l (l.key)}
				<text class="label" class:pinned={l.pinned} x={l.x} y={l.at} text-anchor={l.right ? 'start' : 'end'} dominant-baseline="middle"
					>{l.text}</text
				>
			{/each}
		</svg>

		{#if hovered}
			{@const t = hovered.series}
			{@const record = recordText(t.records?.[shown])}
			<div class="tooltip" style:left="{tipLeft}%" style:top="{tipTop}%" class:flip={tipLeft > 60}>
				<div class="tip-head">
					{t.team.name}
					{#if record}<span class="muted">&nbsp;· {record}</span>{/if}
				</div>
				<div class="tip-row">
					<span class="key" style:background={colorOf(hovered.value)}></span>
					<span>{metric.label}{#if ranks.has(hovered.key)} · #{ranks.get(hovered.key)}{/if}</span>
					<span class="tabular">{formatMetric(metric, hovered.value)}</span>
				</div>
				{#if metric.key !== 'rating'}
					<div class="tip-row">
						<span></span>
						<span class="muted">{rating.label}</span>
						<span class="tabular">{formatMetric(rating, valueAt(t, 'rating', frame))}</span>
					</div>
				{/if}
				<div class="tip-hint">{hovered.key in pins ? 'Click to stop highlighting' : 'Click to highlight and trace its path'}</div>
			</div>
		{/if}
	</div>

	<div class="timeline">
		<button class="play" onclick={play} aria-label={playing ? 'Pause' : 'Play the season'}>
			{#if playing}
				<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2" width="3.5" height="12" rx="1" /><rect x="9.5" y="2" width="3.5" height="12" rx="1" /></svg>
			{:else}
				<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11a.8.8 0 0 0 1.2.7l9-5.5a.8.8 0 0 0 0-1.4l-9-5.5A.8.8 0 0 0 4 2.5z" /></svg>
			{/if}
		</button>
		<div class="track">
			<input
				id="team-map-date"
				type="range"
				min="0"
				max={last}
				step="any"
				value={frame}
				oninput={(e) => {
					playing = false;
					frame = +(e.currentTarget as HTMLInputElement).value;
				}}
				onchange={(e) => (frame = Math.round(+(e.currentTarget as HTMLInputElement).value))}
				aria-label="{dateLabel} shown"
				aria-valuetext={dateAt(shown)}
			/>
			<div class="ends muted small">
				<span>{dateAt(0)}</span>
				<span class="now">Before {dateAt(shown)}</span>
				<span>{dateAt(last)}</span>
			</div>
		</div>
		<button class="pill speed" onclick={() => (speed = speed >= 4 ? 1 : speed * 2)} aria-label="Playback speed {speed}×">{speed}×</button>
	</div>

	<div class="scale">
		<span class="muted">Worse</span>
		<span class="tabular">{formatMetric(metric, worse)}</span>
		<span class="ramp" aria-hidden="true"></span>
		<span class="tabular">{formatMetric(metric, better)}</span>
		<span class="muted">Better</span>
		<span class="muted center"
			>· {metric.center === 'mean' ? 'gray: league average' : 'gray'} {formatMetric(metric, center)}</span
		>
	</div>
</div>

<style>
	.stage {
		position: relative;
		touch-action: pan-y;
	}
	.stage.pointing {
		cursor: pointer;
	}
	.stage:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 6px;
	}
	.stage svg {
		display: block;
		width: 100%;
		height: auto;
	}
	.dot {
		stroke: var(--surface);
		stroke-width: 1.5;
	}
	.dot.faded {
		opacity: 0.15;
	}
	.dot.hovered {
		stroke: var(--text);
		stroke-width: 2;
	}
	.pin {
		fill: none;
		stroke-width: 2.5;
	}
	.trail,
	.trail-halo {
		fill: none;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.trail-halo {
		stroke: var(--surface);
		stroke-width: 4.5;
		opacity: 0.8;
	}
	.trail {
		stroke-width: 2;
	}
	.stop {
		stroke: var(--surface);
		stroke-width: 1;
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
		min-width: 190px;
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
		grid-template-columns: 8px 1fr auto;
		gap: 6px;
		align-items: center;
	}
	.key {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}
	.tip-hint {
		color: var(--muted);
		margin-top: 4px;
	}
	.timeline {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-top: 8px;
	}
	.play {
		flex: none;
		width: 40px;
		height: 40px;
		border-radius: 50%;
		border: 0;
		background: var(--accent);
		color: #fff;
		display: grid;
		place-items: center;
		cursor: pointer;
	}
	.play svg {
		width: 16px;
		height: 16px;
		fill: currentColor;
	}
	.play:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.speed {
		cursor: pointer;
		font-size: 0.8rem;
	}
	.track {
		flex: 1;
		min-width: 0;
	}
	.track input {
		width: 100%;
		accent-color: var(--accent);
	}
	.ends {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		font-variant-numeric: tabular-nums;
	}
	.ends .now {
		color: var(--text);
		font-weight: 600;
	}
	.scale {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px 8px;
		font-size: 0.8rem;
		margin-top: 10px;
	}
	.ramp {
		width: 120px;
		height: 8px;
		border-radius: 4px;
		background: linear-gradient(to right, var(--diverge-neg), var(--diverge-mid), var(--diverge-pos));
	}
	@media (max-width: 560px) {
		.ends span:not(.now) {
			display: none;
		}
		.ends {
			justify-content: center;
		}
	}
</style>
