<script lang="ts">
	import { links } from '$lib/links';
	import { kickoffLabel, spreadLabel } from '$lib/format';
	import { age, withLine } from '$lib/odds';
	import type { GameOdds, UpcomingGame } from '$lib/types';
	import MarketTable from './MarketTable.svelte';
	import SpreadChart from './SpreadChart.svelte';
	import TeamBadge from './TeamBadge.svelte';
	import WinProbBar from './WinProbBar.svelte';

	let {
		game: built,
		sport,
		odds = null,
		hasSpread = true
	}: { game: UpcomingGame; sport: string; odds?: GameOdds | null; hasSpread?: boolean } = $props();

	// current sportsbook lines, when the site has them, replace the ones it
	// was built with; the picks follow the lines
	const live = $derived(withLine(built, built.prediction, odds?.consensus));
	const game = $derived(live.game);
	const prediction = $derived(live.prediction ?? built.prediction);
	const openSpread = $derived(odds?.open.spread ?? null);
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

	<MarketTable {game} {prediction} {hasSpread} />

	{#if odds}
		<div class="lines muted small">
			Lines from {odds.books.length} book{odds.books.length === 1 ? '' : 's'}, {age(odds.updated)}
			{#if openSpread !== null && game.spread !== null && openSpread !== game.spread}
				· opened {spreadLabel(game.home, game.away, openSpread)}
			{/if}
		</div>
	{/if}
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
