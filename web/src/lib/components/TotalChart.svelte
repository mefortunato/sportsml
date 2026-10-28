<script lang="ts">
	// Combined points on one axis: the Vegas line, the model's total and the
	// final, with the gap between line and model shaded.
	let {
		line = null,
		model = null,
		result = null
	}: { line?: number | null; model?: number | null; result?: number | null } = $props();

	const WIDTH = 440;
	const GUTTER = 56;
	const PAD = 14;
	const ROW = 26;
	const TOP = 24;

	const rows = $derived(
		[
			{ key: 'vegas', label: 'Vegas', value: line, text: line == null ? '' : `O/U ${line}` },
			{ key: 'model', label: 'Model', value: model, text: model == null ? '' : model.toFixed(1) },
			{ key: 'final', label: 'Final', value: result, text: result == null ? '' : String(result) }
		].filter((row) => row.value !== null && row.value !== undefined) as {
			key: string;
			label: string;
			value: number;
			text: string;
		}[]
	);
	const values = $derived(rows.map((r) => r.value));
	// at least ~30 points of axis around the values (football and basketball
	// totals alike), and 6 beyond the outermost
	const pad = $derived(Math.max(6, (30 - (Math.max(...values) - Math.min(...values))) / 2));
	const low = $derived(Math.floor((Math.min(...values) - pad) / 5) * 5);
	const high = $derived(Math.ceil((Math.max(...values) + pad) / 5) * 5);
	const height = $derived(TOP + rows.length * ROW + 18);
	const x = (value: number) =>
		GUTTER + PAD + ((value - low) / (high - low)) * (WIDTH - GUTTER - 2 * PAD);
	const ticks = $derived.by(() => {
		const step = high - low > 40 ? 10 : 5;
		const out = [];
		for (let t = Math.ceil(low / step) * step; t <= high; t += step) out.push(t);
		return out;
	});
	const gap = $derived(line != null && model != null ? [Math.min(line, model), Math.max(line, model)] : null);
	const textAnchor = (value: number) => (x(value) > WIDTH - 90 ? 'end' : 'start');
	const textX = (value: number) => (textAnchor(value) === 'end' ? x(value) - 10 : x(value) + 10);
</script>

<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-label="Total points: line, model and final" class="chart">
	<text x={GUTTER + 4} y="12" class="side">◀ under</text>
	<text x={WIDTH - 4} y="12" class="side" text-anchor="end">over ▶</text>
	{#if gap && rows.length >= 2}
		<rect x={x(gap[0])} y={TOP - 4} width={Math.max(2, x(gap[1]) - x(gap[0]))} height={2 * ROW} class="edge" rx="3" />
	{/if}
	{#if line != null}
		<line x1={x(line)} x2={x(line)} y1={TOP - 6} y2={TOP + rows.length * ROW - 2} class="zero" />
	{/if}
	{#each rows as row, i (row.key)}
		{@const y = TOP + i * ROW + ROW / 2 - 4}
		<text x={GUTTER - 6} y={y + 4} text-anchor="end" class="row-label">{row.label}</text>
		<line x1={GUTTER + PAD} x2={WIDTH - PAD} y1={y} y2={y} class="track" />
		{#if row.key === 'vegas'}
			<rect x={x(row.value) - 6} y={y - 6} width="12" height="12" transform="rotate(45 {x(row.value)} {y})" class="marker vegas" />
		{:else if row.key === 'model'}
			<circle cx={x(row.value)} cy={y} r="7" class="marker model" />
		{:else}
			<circle cx={x(row.value)} cy={y} r="6" class="marker final" />
		{/if}
		<text x={textX(row.value)} y={y + 4} text-anchor={textAnchor(row.value)} class="value">{row.text}</text>
	{/each}
	{#each ticks as tick (tick)}
		<text x={x(tick)} y={height - 4} text-anchor="middle" class="tick">{tick}</text>
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
