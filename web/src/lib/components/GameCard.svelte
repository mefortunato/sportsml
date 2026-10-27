<script lang="ts">
	import { links } from '$lib/links';
	import { kickoffLabel } from '$lib/format';
	import type { UpcomingGame } from '$lib/types';
	import MarketTable from './MarketTable.svelte';
	import SpreadChart from './SpreadChart.svelte';
	import TeamBadge from './TeamBadge.svelte';
	import WinProbBar from './WinProbBar.svelte';

	let { game, sport }: { game: UpcomingGame; sport: string } = $props();

	const prediction = $derived(game.prediction);
</script>

<a class="card game" href={links.game(sport, game.game_id)}>
	<div class="top">
		<div class="teams">
			<TeamBadge team={game.away} label="name" />
			<span class="muted at">{game.neutral ? 'vs' : '@'}</span>
			<TeamBadge team={game.home} label="name" />
		</div>
		<span class="muted small">{kickoffLabel(game.kickoff)}</span>
	</div>

	<SpreadChart
		home={game.home}
		away={game.away}
		spread={game.spread}
		model={prediction.margin}
	/>

	<WinProbBar home={game.home} away={game.away} probability={prediction.win_prob} />

	<MarketTable {game} {prediction} />
</a>

<style>
	.game {
		display: flex;
		flex-direction: column;
		gap: 12px;
		color: inherit;
		transition: border-color 0.15s;
	}
	.game:hover {
		text-decoration: none;
		border-color: var(--accent);
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	.teams {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.at {
		font-weight: 600;
	}
</style>
