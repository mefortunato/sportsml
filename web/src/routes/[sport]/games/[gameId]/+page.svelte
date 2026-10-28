<script lang="ts">
	import { links } from '$lib/links';
	import LineCalculator from '$lib/components/LineCalculator.svelte';
	import MarketTable from '$lib/components/MarketTable.svelte';
	import MatchupDetails from '$lib/components/MatchupDetails.svelte';
	import ProbabilityCompare from '$lib/components/ProbabilityCompare.svelte';
	import Sportsbooks from '$lib/components/Sportsbooks.svelte';
	import { gameOdds, withLine } from '$lib/odds';
	import SpreadChart from '$lib/components/SpreadChart.svelte';
	import TotalChart from '$lib/components/TotalChart.svelte';
	import TeamBadge from '$lib/components/TeamBadge.svelte';
	import WinProbBar from '$lib/components/WinProbBar.svelte';
	import { dateText, kickoffLabel, seasonText, marginLabel, signed, spreadLabel } from '$lib/format';

	let { data } = $props();
	const info = $derived(data.info);
	const built = $derived(data.game);
	const result = $derived(built.result);
	// an upcoming game's current sportsbook lines replace the built ones
	const odds = $derived(result ? null : gameOdds(data.odds, built.game_id));
	const live = $derived(withLine(built, built.prediction, odds?.consensus));
	const game = $derived(live.game);
	const prediction = $derived(live.prediction);
	const pickTeam = $derived(
		prediction?.ats_pick ? (prediction.ats_pick === 'home' ? game.home : game.away) : null
	);
	const coveredTeam = $derived(
		result?.covered === 'home' ? game.home : result?.covered === 'away' ? game.away : null
	);
</script>

<div class="container section">
	<a class="small" href={links.upcoming(info.sport)}>← {info.label} upcoming</a>

	<div class="card hero section">
		<div class="meta muted small">
			{dateText(info.date_label, game.date, game.date_name)}, {seasonText(game.season, info.split_season)} · {kickoffLabel(game.kickoff)}{game.neutral ? ' · neutral site' : ''}
		</div>
		<div class="matchup">
			<div class="team">
				<TeamBadge team={game.away} size={56} label="none" />
				<div class="name">{game.away.name}</div>
				{#if result}<div class="score tabular">{result.away_score}</div>{/if}
			</div>
			<div class="at muted">{game.neutral ? 'vs' : '@'}</div>
			<div class="team">
				<TeamBadge team={game.home} size={56} label="none" />
				<div class="name">{game.home.name}</div>
				{#if result}<div class="score tabular">{result.home_score}</div>{/if}
			</div>
		</div>

		<div class="chips">
			<span class="pill">Vegas {spreadLabel(game.home, game.away, game.spread)}</span>
			{#if prediction}
				<span class="pill accent">Model {marginLabel(game.home, game.away, prediction.margin)}</span>
				{#if pickTeam && prediction.edge !== null}
					<span class="pill accent"
						>Model pick: {pickTeam.team} covers (edge {signed(Math.abs(prediction.edge))})</span
					>
				{/if}
			{:else}
				<span class="pill">No model prediction for this game</span>
			{/if}
			{#if result}
				<span class="pill" class:good={coveredTeam !== null}>
					{result.covered === 'push' ? 'Push' : coveredTeam ? `${coveredTeam.team} covered` : 'Final'}
				</span>
			{/if}
		</div>

		<div class="chart">
			<SpreadChart
				home={game.home}
				away={game.away}
				spread={game.spread}
				model={prediction?.margin ?? null}
				result={result?.margin ?? null}
			/>
		</div>
		{#if prediction}
			{#if prediction.market_prob != null}
				<ProbabilityCompare
					home={game.home}
					away={game.away}
					model={prediction.win_prob}
					market={prediction.market_prob}
				/>
			{:else}
				<WinProbBar home={game.home} away={game.away} probability={prediction.win_prob} />
			{/if}
		{/if}
		{#if game.total_line != null || prediction?.total != null}
			<div class="chart">
				<TotalChart line={game.total_line} model={prediction?.total ?? null} result={result?.total ?? null} />
			</div>
		{/if}
		<MarketTable {game} {prediction} {result} />
	</div>

	{#if odds}
		<div class="section">
			<Sportsbooks home={game.home} away={game.away} {odds} />
		</div>
	{/if}

	{#if prediction && !result && info.pricing}
		<div class="section">
			<LineCalculator {game} {prediction} pricing={info.pricing} books={odds?.books ?? []} />
		</div>
	{/if}

	<MatchupDetails matchup={game} dateLabel={info.date_label} splitSeason={info.split_season} />
</div>

<style>
	.hero {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.matchup {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		align-items: center;
		gap: 12px;
	}
	.team {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		text-align: center;
	}
	.name {
		font-weight: 700;
		font-size: 1.1rem;
	}
	.score {
		font-size: 2rem;
		font-weight: 800;
	}
	.at {
		font-size: 1.2rem;
		font-weight: 700;
	}
	.chips {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		justify-content: center;
	}
	.chart {
		max-width: 640px;
		width: 100%;
		margin: 0 auto;
	}
</style>
