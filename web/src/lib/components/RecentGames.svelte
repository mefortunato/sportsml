<script lang="ts">
	import { handicap } from '$lib/format';
	import type { TeamSummary } from '$lib/types';
	import Sparkline from './Sparkline.svelte';
	import TeamBadge from './TeamBadge.svelte';

	let { summary, dateLabel = 'Week' }: { summary: TeamSummary; dateLabel?: string } = $props();

	const short = $derived(dateLabel.charAt(0).toUpperCase());
	const margins = $derived(summary.recent.map((g) => g.margin).reverse());
	const outcome = (margin: number) => (margin > 0 ? 'W' : margin < 0 ? 'L' : 'T');
</script>

<div class="recent">
	<div class="title">
		<TeamBadge team={summary.team} label="name" size={24} />
		{#if margins.length}
			<Sparkline values={margins} />
		{/if}
	</div>
	{#if summary.recent.length === 0}
		<p class="muted small">No earlier games.</p>
	{:else}
		<table class="small tabular">
			<thead>
				<tr class="muted">
					<th></th>
					<th>Opponent</th>
					<th>Score</th>
					<th>Line</th>
					<th>ATS</th>
					<th class="right">{dateLabel}</th>
				</tr>
			</thead>
			<tbody>
				{#each summary.recent as game (game.game_id)}
					<tr>
						<td>
							<span class="pill" class:good={game.margin > 0} class:bad={game.margin < 0}
								>{outcome(game.margin)}</span
							>
						</td>
						<td class="opp">
							<span class="muted">{game.location === -1 ? '@' : 'vs'}</span>
							<TeamBadge team={game.opp} size={18} />
						</td>
						<td>{game.score ?? '?'}–{game.opp_score ?? '?'}</td>
						<td class="muted">{game.spread === null ? '—' : handicap(game.spread, 'home')}</td>
						<td>
							{#if game.ats}
								<span class:good={game.ats === 'W'} class:bad={game.ats === 'L'} class="ats"
									>{game.ats}</span
								>
							{:else}
								<span class="muted">—</span>
							{/if}
						</td>
						<td class="right muted">{#if game.date_name}{game.date_name}{:else}{short}{game.date}
							’{String(game.season).slice(2)}{/if}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>

<style>
	.title {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 8px;
		gap: 8px;
	}
	table {
		width: 100%;
		border-collapse: collapse;
	}
	th {
		text-align: left;
		font-weight: 500;
		padding: 4px 4px;
	}
	td {
		padding: 5px 4px;
		border-top: 1px solid var(--border);
	}
	.opp {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.right {
		text-align: right;
	}
	.ats {
		font-weight: 700;
	}
	.ats.good {
		color: var(--good);
	}
	.ats.bad {
		color: var(--bad);
	}
</style>
