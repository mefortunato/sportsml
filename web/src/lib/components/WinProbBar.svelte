<script lang="ts">
	import { pct } from '$lib/format';
	import type { Team } from '$lib/types';

	/** `probability`: P(home team wins). Away on the left, home on the right. */
	let { home, away, probability }: { home: Team; away: Team; probability: number } = $props();
</script>

<div class="wrap" aria-label="Win probability">
	<div class="labels small">
		<span><strong>{away.team}</strong> {pct(1 - probability)}</span>
		<span class="muted">win probability</span>
		<span>{pct(probability)} <strong>{home.team}</strong></span>
	</div>
	<div class="bar">
		<div style:width="{(1 - probability) * 100}%" style:background={away.color ?? 'var(--muted)'}></div>
		<div style:width="{probability * 100}%" style:background={home.color ?? 'var(--accent)'}></div>
	</div>
</div>

<style>
	.labels {
		display: flex;
		justify-content: space-between;
		margin-bottom: 4px;
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
