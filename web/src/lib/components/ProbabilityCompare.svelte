<script lang="ts">
	import { pct } from '$lib/format';
	import type { Team } from '$lib/types';

	// Win probability bars for the model and Vegas (no-vig), away on the left.
	let {
		home,
		away,
		model,
		market = null
	}: { home: Team; away: Team; model: number; market?: number | null } = $props();

	const rows = $derived(
		[
			{ label: 'Model', p: model },
			{ label: 'Vegas', p: market }
		].filter((r) => r.p !== null && r.p !== undefined) as { label: string; p: number }[]
	);
</script>

<div class="compare" aria-label="Win probability, model and Vegas">
	{#each rows as row (row.label)}
		<div class="row small">
			<span class="label muted">{row.label}</span>
			<span class="tabular">{away.team} {pct(1 - row.p)}</span>
			<div class="bar">
				<div style:width="{(1 - row.p) * 100}%" style:background={away.color ?? 'var(--muted)'}></div>
				<div style:width="{row.p * 100}%" style:background={home.color ?? 'var(--accent)'}></div>
			</div>
			<span class="tabular">{pct(row.p)} {home.team}</span>
		</div>
	{/each}
</div>

<style>
	.compare {
		display: flex;
		flex-direction: column;
		gap: 6px;
		width: 100%;
	}
	.row {
		display: grid;
		grid-template-columns: 48px auto 1fr auto;
		gap: 8px;
		align-items: center;
	}
	.label {
		font-weight: 600;
	}
	.bar {
		display: flex;
		height: 8px;
		border-radius: 999px;
		overflow: hidden;
		background: var(--surface-2);
		gap: 2px;
	}
	.bar div {
		height: 100%;
	}
</style>
