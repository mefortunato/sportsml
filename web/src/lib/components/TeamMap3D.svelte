<script lang="ts">
	import { dateText, signed } from '$lib/format';
	import { divergeColor, divergeMax, type Pins } from '$lib/rankings';
	import { CUBE_EDGES, positionAt, project, ranksAt, ratingAt, rotate } from '$lib/teammap';
	import type { TeamMap } from '$lib/types';
	import { onDestroy } from 'svelte';

	// Every team as a dot in the 3-D projection of the model's team
	// embeddings, filled by average margin. Drag to turn the space; the
	// timeline (or play) moves every team to where it stood before that
	// date, highlighted teams drawing their path so far.
	let {
		map,
		pins,
		visible = null,
		dateLabel = 'Week',
		frame = $bindable(0),
		ontoggle
	}: {
		map: TeamMap;
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
	const H = $derived(narrow ? 380 : 520);
	let zoom = $state(1);
	const size = $derived((Math.min(W, H) / 2) * 0.62 * zoom);
	const R = $derived((map.teams.length > 100 ? 3.6 : 6) * Math.min(1.4, Math.max(0.8, zoom)));

	// the camera: a slow turn until the reader takes over
	const reduced =
		typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
	let yaw = $state(-0.6);
	let pitch = $state(0.35);
	let spinning = $state(!reduced);
	let playing = $state(false);
	let speed = $state(1);

	const last = $derived(map.dates.length - 1);
	const shown = $derived(Math.round(frame));
	const max = $derived(divergeMax(map.teams.flatMap((t) => t.ratings.filter((r) => r !== null))));
	const ranks = $derived(ranksAt(map.teams, shown));
	const isVisible = (team: string) => !visible || visible.has(team);

	const cx = $derived(W / 2);
	const cy = $derived(H / 2);
	function screen(p: [number, number, number]) {
		const q = project(rotate(p, yaw, pitch), size);
		return { x: cx + q.x, y: cy + q.y, scale: q.scale, depth: q.depth };
	}

	const dots = $derived(
		map.teams
			.map((t) => {
				const p = positionAt(t, frame);
				if (!p) return null;
				const s = screen(p);
				return {
					key: t.team.team,
					team: t.team,
					rating: ratingAt(t, frame),
					...s,
					faded: !isVisible(t.team.team),
					slot: pins[t.team.team] as number | undefined
				};
			})
			.filter((d) => d !== null)
			// far first, so nearer dots paint over them
			.sort((a, b) => a.depth - b.depth)
	);
	const edges = $derived(
		CUBE_EDGES.map(([a, b]) => {
			const [p, q] = [screen(a), screen(b)];
			return { d: `M${p.x.toFixed(1)},${p.y.toFixed(1)}L${q.x.toFixed(1)},${q.y.toFixed(1)}`, back: p.depth + q.depth < 0 };
		})
	);

	let hover = $state<string | null>(null);
	const hovered = $derived(dots.find((d) => d.key === hover) ?? null);

	// paths so far for highlighted teams and the hovered one
	const trails = $derived(
		map.teams
			.filter((t) => t.team.team in pins || t.team.team === hover)
			.map((t) => {
				const points = [];
				for (let i = 0; i <= Math.floor(frame); i++) {
					const p = t.positions[i];
					if (p) points.push(screen(p));
				}
				const now = positionAt(t, frame);
				if (now) points.push(screen(now));
				return {
					key: t.team.team,
					slot: pins[t.team.team] as number | undefined,
					d: points.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(''),
					stops: points.slice(0, -1)
				};
			})
	);

	// labels: highlighted teams, or every team when only a few are shown
	const LABEL_ALL = 12;
	const labels = $derived.by(() => {
		const shownDots = dots.filter((d) => !d.faded);
		const pick = shownDots.length <= LABEL_ALL ? shownDots : shownDots.filter((d) => d.slot);
		const out = pick
			.map((d) => ({ key: d.key, text: d.team.abbr ?? d.team.team, x: d.x + R * d.scale + 6, at: d.y, pinned: !!d.slot }))
			.sort((a, b) => a.at - b.at);
		const LINE = 14;
		for (let i = 1; i < out.length; i++)
			for (let j = 0; j < i; j++) {
				const near = Math.abs(out[i].x - out[j].x) < 7 * Math.max(out[i].text.length, out[j].text.length);
				if (near && Math.abs(out[i].at - out[j].at) < LINE) {
					out[i].at = out[j].at + LINE;
					j = -1;
				}
			}
		return out;
	});

	// ---- animation: playback and the idle turn share one frame loop
	let raf = 0;
	let before = 0;
	const SECONDS_PER_DATE = 0.9;
	function tick(now: number) {
		const dt = before ? Math.min(0.1, (now - before) / 1000) : 0;
		before = now;
		if (spinning && !dragging) yaw += dt * 0.25;
		if (playing) {
			frame = Math.min(last, frame + (dt * speed) / SECONDS_PER_DATE);
			if (frame >= last) playing = false;
		}
		raf = spinning || playing ? requestAnimationFrame(tick) : 0;
		if (!raf) before = 0;
	}
	$effect(() => {
		if ((spinning || playing) && !raf) raf = requestAnimationFrame(tick);
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

	// ---- pointer: drag turns the space, a tap highlights the nearest team
	let svg: SVGSVGElement;
	let dragging = $state(false);
	let start: { x: number; y: number; yaw: number; pitch: number; moved: boolean } | null = null;

	function local(event: PointerEvent) {
		const box = svg.getBoundingClientRect();
		return { x: ((event.clientX - box.left) / box.width) * W, y: ((event.clientY - box.top) / box.height) * H };
	}
	function nearest(x: number, y: number): string | null {
		let found: string | null = null;
		let distance = 16;
		// nearest first; among close ones the frontmost (dots are far-first)
		for (const d of dots) {
			if (d.faded) continue;
			const gap = Math.hypot(d.x - x, d.y - y);
			if (gap <= distance) [found, distance] = [d.key, gap + 0.5];
		}
		return found;
	}
	function down(event: PointerEvent) {
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		start = { x: event.clientX, y: event.clientY, yaw, pitch, moved: false };
	}
	function move(event: PointerEvent) {
		if (start) {
			const [dx, dy] = [event.clientX - start.x, event.clientY - start.y];
			if (!start.moved && Math.hypot(dx, dy) > 4) {
				start.moved = true;
				dragging = true;
				spinning = false;
				hover = null;
			}
			if (start.moved) {
				yaw = start.yaw + dx * 0.01;
				pitch = Math.max(-1.4, Math.min(1.4, start.pitch + dy * 0.01));
				return;
			}
		}
		const p = local(event);
		hover = nearest(p.x, p.y);
	}
	function up(event: PointerEvent) {
		if (start && !start.moved) {
			const p = local(event);
			const team = nearest(p.x, p.y);
			if (team) ontoggle(team);
		}
		start = null;
		dragging = false;
	}

	function key(event: KeyboardEvent) {
		if (event.key === 'ArrowLeft') frame = Math.max(0, Math.round(frame) - 1);
		else if (event.key === 'ArrowRight') frame = Math.min(last, Math.round(frame) + 1);
		else if (event.key === 'ArrowUp') pitch = Math.max(-1.4, pitch - 0.1);
		else if (event.key === 'ArrowDown') pitch = Math.min(1.4, pitch + 0.1);
		else if (event.key === ' ') play();
		else return;
		event.preventDefault();
	}

	function reset() {
		[yaw, pitch, zoom] = [-0.6, 0.35, 1];
	}

	const dateAt = (i: number) => dateText(dateLabel, map.dates[i], map.date_names?.[i]);
	const tipLeft = $derived(hovered ? (hovered.x / W) * 100 : 0);
	const tipTop = $derived(hovered ? (hovered.y / H) * 100 : 0);
</script>

<div class="viewer">
	<div class="stage" bind:clientWidth={width}>
		<div
			class="surface"
			role="slider"
			aria-roledescription="3-D team map"
			aria-label="Teams in a 3-D projection of the model's team embeddings, colored by average predicted margin. Drag to turn; left and right arrows step through {dateLabel.toLowerCase()}s, up and down tilt, space plays."
			aria-valuemin={0}
			aria-valuemax={last}
			aria-valuenow={shown}
			aria-valuetext="Before {dateAt(shown)}"
			tabindex="0"
			onpointerdown={down}
			onpointermove={move}
			onpointerup={up}
			onpointercancel={up}
			onpointerleave={() => (hover = null)}
			onkeydown={key}
			class:grabbing={dragging}
			class:pointing={hover !== null && !dragging}
		>
		<svg bind:this={svg} viewBox="0 0 {W} {H}" aria-hidden="true">
			{#each edges as e, i (i)}
				<path class="edge" class:back={e.back} d={e.d} />
			{/each}
			{#each trails as t (t.key)}
				<path class="trail-halo" d={t.d} />
				<path class="trail" d={t.d} style:stroke={t.slot ? `var(--series-${t.slot})` : 'var(--text)'} />
				{#each t.stops as s, i (i)}
					<circle class="stop" cx={s.x} cy={s.y} r="2" style:fill={t.slot ? `var(--series-${t.slot})` : 'var(--text)'} />
				{/each}
			{/each}
			{#each dots as d (d.key)}
				<circle
					class="dot"
					class:faded={d.faded}
					class:hovered={d.key === hover}
					cx={d.x}
					cy={d.y}
					r={R * d.scale * (d.slot || d.key === hover ? 1.25 : 1)}
					style:fill={d.rating === null ? 'var(--diverge-mid)' : divergeColor(d.rating, max)}
					style:opacity={d.faded ? 0.15 : Math.min(1, 0.55 + 0.45 * d.scale)}
				/>
				{#if d.slot}
					<circle class="pin" cx={d.x} cy={d.y} r={R * d.scale * 1.25 + 3.5} style:stroke="var(--series-{d.slot})" />
				{/if}
			{/each}
			{#each labels as l (l.key)}
				<text class="label" class:pinned={l.pinned} x={l.x} y={l.at} dominant-baseline="middle">{l.text}</text>
			{/each}
		</svg>
		</div>

		{#if hovered && !dragging}
			<div class="tooltip" style:left="{tipLeft}%" style:top="{tipTop}%" class:flip={tipLeft > 60}>
				<div class="tip-head">{hovered.team.name}</div>
				{#if hovered.rating !== null}
					<div class="tip-row">
						<span class="key" style:background={divergeColor(hovered.rating, max)}></span>
						<span>#{ranks.get(hovered.key) ?? '–'} · avg margin</span>
						<span class="tabular">{signed(hovered.rating)}</span>
					</div>
				{/if}
				<div class="tip-hint">{hovered.key in pins ? 'Click to stop highlighting' : 'Click to highlight and trace its path'}</div>
			</div>
		{/if}

		<div class="camera">
			<button class="pill" onclick={() => (spinning = !spinning)} aria-pressed={spinning}
				>{spinning ? 'Stop turning' : 'Turn'}</button
			>
			<button class="pill" onclick={() => (zoom = Math.min(2.5, zoom * 1.25))} aria-label="Zoom in">+</button>
			<button class="pill" onclick={() => (zoom = Math.max(0.6, zoom / 1.25))} aria-label="Zoom out">−</button>
			<button class="pill" onclick={reset}>Reset view</button>
		</div>
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
		<button class="pill speed" onclick={() => (speed = speed >= 4 ? 1 : speed * 2)} aria-label="Playback speed {speed}×"
			>{speed}×</button
		>
	</div>

	<div class="scale" aria-hidden="true">
		<span class="tabular">{signed(-max, 0)}</span>
		<span class="ramp"></span>
		<span class="tabular">{signed(max, 0)}</span>
		<span class="muted">avg margin</span>
		<span class="muted hint">Drag to turn · ← → step through {dateLabel.toLowerCase()}s</span>
	</div>
</div>

<style>
	.stage {
		position: relative;
	}
	.surface {
		touch-action: none;
		cursor: grab;
		user-select: none;
	}
	.surface svg {
		display: block;
		width: 100%;
		height: auto;
	}
	.surface.grabbing {
		cursor: grabbing;
	}
	.surface.pointing {
		cursor: pointer;
	}
	.surface:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 6px;
	}
	.edge {
		fill: none;
		stroke: var(--border);
		stroke-width: 1;
	}
	.edge.back {
		stroke-dasharray: 3 4;
	}
	.dot {
		stroke: var(--surface);
		stroke-width: 1.25;
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
		min-width: 170px;
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
	.key {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}
	.tip-hint {
		color: var(--muted);
		margin-top: 4px;
	}
	.camera {
		position: absolute;
		top: 0;
		right: 0;
		display: flex;
		gap: 4px;
	}
	.camera button,
	.speed {
		cursor: pointer;
		font-size: 0.8rem;
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
		gap: 8px;
		font-size: 0.8rem;
		color: var(--muted);
		margin-top: 10px;
	}
	.ramp {
		width: 140px;
		height: 8px;
		border-radius: 4px;
		background: linear-gradient(to right, var(--diverge-neg), var(--diverge-mid), var(--diverge-pos));
	}
	.hint {
		margin-left: auto;
	}
	@media (max-width: 560px) {
		.ends span:not(.now) {
			display: none;
		}
		.ends {
			justify-content: center;
		}
		.hint {
			margin-left: 0;
		}
	}
</style>
