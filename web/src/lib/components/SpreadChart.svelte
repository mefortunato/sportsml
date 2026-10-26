<script lang="ts">
	import { marginLabel, spreadLabel } from '$lib/format';
	import type { Team } from '$lib/types';

	// All values are the home team's margin: right of center favors the home team.
	let {
		home,
		away,
		spread = null,
		model = null,
		result = null
	}: {
		home: Team;
		away: Team;
		spread?: number | null;
		model?: number | null;
		result?: number | null;
	} = $props();

	const WIDTH = 440;
	const GUTTER = 56;
	const PAD = 14;
	const ROW = 26;
	const TOP = 24;

	const rows = $derived(
		[
			{ key: 'vegas', label: 'Vegas', value: spread, text: spreadLabel(home, away, spread) },
			{
				key: 'model',
				label: 'Model',
				value: model,
				text: model === null ? '' : marginLabel(home, away, model)
			},
			{
				key: 'final',
				label: 'Final',
				value: result,
				text: result === null ? '' : marginLabel(home, away, result)
			}
		].filter((row) => row.value !== null && row.value !== undefined) as {
			key: string;
			label: string;
			value: number;
			text: string;
		}[]
	);

	const range = $derived(
		Math.max(10, Math.ceil(Math.max(0, ...rows.map((r) => Math.abs(r.value))) + 3))
	);
	const height = $derived(TOP + rows.length * ROW + 18);
	const x = (value: number) =>
		GUTTER + PAD + ((value + range) / (2 * range)) * (WIDTH - GUTTER - 2 * PAD);
	const ticks = $derived(
		[-14, -7, 0, 7, 14].filter((t) => Math.abs(t) < range).concat(range > 21 ? [-21, 21] : [])
	);
	const edge = $derived(
		spread !== null && model !== null ? [Math.min(spread, model), Math.max(spread, model)] : null
	);
	const textAnchor = (value: number) => (x(value) > WIDTH - 110 ? 'end' : 'start');
	const textX = (value: number) => (textAnchor(value) === 'end' ? x(value) - 10 : x(value) + 10);
</script>

<svg
	viewBox="0 0 {WIDTH} {height}"
	role="img"
	aria-label="Spread versus model margin"
	class="chart"
>
	<!-- which side favors whom -->
	<rect
		x={GUTTER}
		y={TOP - 6}
		width={x(0) - GUTTER}
		height={rows.length * ROW + 4}
		fill={away.color ?? 'var(--muted)'}
		opacity="0.07"
	/>
	<rect
		x={x(0)}
		y={TOP - 6}
		width={WIDTH - x(0)}
		height={rows.length * ROW + 4}
		fill={home.color ?? 'var(--muted)'}
		opacity="0.07"
	/>
	<text x={GUTTER + 4} y="12" class="side">◀ {away.team} favored</text>
	<text x={WIDTH - 4} y="12" class="side" text-anchor="end">{home.team} favored ▶</text>

	{#if edge && rows.length >= 2}
		<rect
			x={x(edge[0])}
			y={TOP - 4}
			width={Math.max(2, x(edge[1]) - x(edge[0]))}
			height={2 * ROW}
			class="edge"
			rx="3"
		/>
	{/if}

	<line x1={x(0)} x2={x(0)} y1={TOP - 6} y2={TOP + rows.length * ROW - 2} class="zero" />

	{#each rows as row, i (row.key)}
		{@const y = TOP + i * ROW + ROW / 2 - 4}
		<text x={GUTTER - 6} y={y + 4} text-anchor="end" class="row-label">{row.label}</text>
		<line x1={GUTTER + PAD} x2={WIDTH - PAD} y1={y} y2={y} class="track" />
		{#if row.key === 'vegas'}
			<rect
				x={x(row.value) - 6}
				y={y - 6}
				width="12"
				height="12"
				transform="rotate(45 {x(row.value)} {y})"
				class="marker vegas"
			/>
		{:else if row.key === 'model'}
			<circle cx={x(row.value)} cy={y} r="7" class="marker model" />
		{:else}
			<circle cx={x(row.value)} cy={y} r="6" class="marker final" />
		{/if}
		<text x={textX(row.value)} y={y + 4} text-anchor={textAnchor(row.value)} class="value"
			>{row.text}</text
		>
	{/each}

	{#each ticks as tick (tick)}
		<text x={x(tick)} y={height - 4} text-anchor="middle" class="tick"
			>{tick === 0 ? 'even' : Math.abs(tick)}</text
		>
	{/each}
</svg>

<style>
	.chart {
		width: 100%;
		height: auto;
		display: block;
		overflow: visible;
	}
	.side {
		font-size: 10px;
		fill: var(--muted);
		font-weight: 600;
	}
	.row-label {
		font-size: 11px;
		fill: var(--muted);
		font-weight: 600;
	}
	.track {
		stroke: var(--border);
		stroke-width: 1;
	}
	.zero {
		stroke: var(--muted);
		stroke-dasharray: 3 3;
		opacity: 0.7;
	}
	.edge {
		fill: var(--accent-soft);
	}
	.marker.vegas {
		fill: var(--vegas);
	}
	.marker.model {
		fill: var(--accent);
		stroke: var(--surface);
		stroke-width: 2;
	}
	.marker.final {
		fill: var(--text);
	}
	.value {
		font-size: 12px;
		font-weight: 600;
		fill: var(--text);
	}
	.tick {
		font-size: 10px;
		fill: var(--muted);
	}
</style>
