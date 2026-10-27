<script lang="ts">
	import { pct } from '$lib/format';
	import type { CalibrationBin } from '$lib/types';

	// Predicted win probability (x) vs how often those teams won (y); the
	// diagonal is perfect calibration.
	let {
		series,
		event = 'win'
	}: {
		series: { label: string; slot: number; bins: CalibrationBin[] }[];
		/** What the probability is of: a team winning, or the game going over. */
		event?: 'win' | 'over';
	} = $props();
	const words = $derived(
		event === 'over'
			? { predicted: 'Predicted over probability', actual: 'Actual over rate', did: 'over' }
			: { predicted: 'Predicted win probability', actual: 'Actual win rate', did: 'won' }
	);

	// drawn at the container's own width (square plot), so text stays 12px
	let width = $state(420);
	const M = { top: 12, right: 16, bottom: 40, left: 46 };
	const W = $derived(Math.max(260, Math.round(width)));
	const size = $derived(W - M.left - M.right);
	const H = $derived(size + M.top + M.bottom);
	const x = (p: number) => M.left + p * size;
	const y = (p: number) => M.top + (1 - p) * size;
	const ticks = [0, 0.25, 0.5, 0.75, 1];

	let hover = $state<{ label: string; slot: number; bin: CalibrationBin } | null>(null);
</script>

<div class="chart" bind:clientWidth={width}>
	<svg viewBox="0 0 {W} {H}" role="img" aria-label="Calibration of the {words.predicted.toLowerCase()}">
		{#each ticks as t (t)}
			<line class="grid" x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} />
			<line class="grid" x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} />
			<text class="tick" x={x(0) - 8} y={y(t)} text-anchor="end" dominant-baseline="middle">{pct(t)}</text>
			<text class="tick" x={x(t)} y={y(0) + 18} text-anchor="middle">{pct(t)}</text>
		{/each}
		<text class="axis" x={x(0.5)} y={H - 4} text-anchor="middle">{words.predicted}</text>
		<text class="axis" transform="translate(12 {y(0.5)}) rotate(-90)" text-anchor="middle">{words.actual}</text>
		<line class="diagonal" x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} />

		{#each series as s (s.label)}
			<path
				class="line"
				style:stroke="var(--series-{s.slot})"
				d={s.bins.map((b, i) => `${i ? 'L' : 'M'}${x(b.predicted).toFixed(1)},${y(b.actual).toFixed(1)}`).join('')}
			/>
		{/each}
		{#each series as s (s.label)}
			{#each s.bins as bin (bin.predicted)}
				<g
					role="presentation"
					onpointerenter={() => (hover = { label: s.label, slot: s.slot, bin })}
					onpointerleave={() => (hover = null)}
				>
					<circle class="hit" cx={x(bin.predicted)} cy={y(bin.actual)} r="12" />
					<circle class="dot" cx={x(bin.predicted)} cy={y(bin.actual)} r="5" style:fill="var(--series-{s.slot})" />
				</g>
			{/each}
		{/each}
	</svg>
	{#if hover}
		<div class="tooltip" style:left="{(x(hover.bin.predicted) / W) * 100}%" style:top="{(y(hover.bin.actual) / H) * 100}%"
			class:flip={hover.bin.predicted > 0.55}>
			<div class="tip-head"><span class="swatch" style:background="var(--series-{hover.slot})"></span> {hover.label}</div>
			<div>Predicted {pct(hover.bin.predicted)}, {words.did} {pct(hover.bin.actual)}</div>
			<div class="muted">{hover.bin.n} games</div>
		</div>
	{/if}
</div>

<style>
	.chart {
		position: relative;
		max-width: 460px;
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
	}
	.grid {
		stroke: var(--border);
	}
	.diagonal {
		stroke: var(--muted);
		stroke-opacity: 0.6;
	}
	.tick,
	.axis {
		fill: var(--muted);
		font-size: 12px;
		font-variant-numeric: tabular-nums;
	}
	.line {
		fill: none;
		stroke-width: 2;
		stroke-linejoin: round;
	}
	.hit {
		fill: transparent;
	}
	.dot {
		stroke: var(--surface);
		stroke-width: 2;
		pointer-events: none;
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
		white-space: nowrap;
	}
	.tooltip.flip {
		transform: translate(calc(-100% - 14px), -50%);
	}
	.tip-head {
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.swatch {
		display: inline-block;
		width: 9px;
		height: 9px;
		border-radius: 50%;
	}
</style>
