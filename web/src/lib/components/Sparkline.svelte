<script lang="ts">
	/** Bar sparkline of margins, oldest to newest; wins up, losses down. */
	let { values, width = 120, height = 34 }: { values: number[]; width?: number; height?: number } =
		$props();

	const max = $derived(Math.max(7, ...values.map((v) => Math.abs(v))));
	const step = $derived(values.length ? width / values.length : width);
	const mid = $derived(height / 2);
</script>

<svg viewBox="0 0 {width} {height}" {width} {height} role="img" aria-label="Recent margins">
	<line x1="0" x2={width} y1={mid} y2={mid} class="axis" />
	{#each values as value, i (i)}
		{@const h = (Math.abs(value) / max) * (mid - 2)}
		<rect
			x={i * step + step * 0.2}
			y={value >= 0 ? mid - h : mid}
			width={step * 0.6}
			height={Math.max(1, h)}
			rx="1.5"
			class={value > 0 ? 'win' : value < 0 ? 'loss' : 'tie'}
		/>
	{/each}
</svg>

<style>
	.axis {
		stroke: var(--border);
	}
	.win {
		fill: var(--good);
	}
	.loss {
		fill: var(--bad);
	}
	.tie {
		fill: var(--muted);
	}
</style>
