<script lang="ts">
	import type { ChallengeRecord } from '$lib/challenge';
	import { pct, winRate } from '$lib/format';

	let { record, onreset }: { record: ChallengeRecord; onreset?: () => void } = $props();

	// win rate needed to break even betting at -110
	const BREAKEVEN = 110 / 210;
	const you = $derived(winRate(record.player.wins, record.player.losses));
	const model = $derived(winRate(record.model.wins, record.model.losses));
</script>

<div class="card scoreboard">
	<div class="side">
		<div class="muted small">You</div>
		<div class="big tabular">{record.player.wins}-{record.player.losses}</div>
		<div class="rate" class:good={you !== null && you >= BREAKEVEN}>
			{you === null ? '—' : pct(you, 1)}
		</div>
	</div>
	<div class="vs muted">vs</div>
	<div class="side">
		<div class="muted small">Model</div>
		<div class="big tabular">{record.model.wins}-{record.model.losses}</div>
		<div class="rate" class:good={model !== null && model >= BREAKEVEN}>
			{model === null ? '—' : pct(model, 1)}
		</div>
	</div>
	<div class="extra small muted">
		<div>{record.played} played · streak {record.streak} (best {record.bestStreak})</div>
		<div>
			agreed with the model {record.played ? pct(record.agreed / record.played) : '—'} · break-even
			{pct(BREAKEVEN, 1)}
		</div>
		{#if onreset && record.played}
			<button class="small" onclick={onreset}>Reset record</button>
		{/if}
	</div>
</div>

<style>
	.scoreboard {
		display: grid;
		grid-template-columns: auto auto auto 1fr;
		gap: 16px;
		align-items: center;
	}
	.side {
		text-align: center;
		min-width: 80px;
	}
	.big {
		font-size: 1.6rem;
		font-weight: 700;
	}
	.rate {
		font-weight: 600;
	}
	.rate.good {
		color: var(--good);
	}
	.extra {
		display: flex;
		flex-direction: column;
		gap: 4px;
		align-items: flex-end;
		text-align: right;
	}
	.extra button {
		padding: 4px 10px;
	}
	@media (max-width: 640px) {
		.scoreboard {
			grid-template-columns: 1fr auto 1fr;
		}
		.extra {
			grid-column: 1 / -1;
			align-items: center;
			text-align: center;
		}
	}
</style>
