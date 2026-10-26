<script lang="ts">
	import MatchupDetails from '$lib/components/MatchupDetails.svelte';
	import SpreadChart from '$lib/components/SpreadChart.svelte';
	import TeamBadge from '$lib/components/TeamBadge.svelte';
	import WinProbBar from '$lib/components/WinProbBar.svelte';
	import { kickoffLabel, marginLabel, signed, spreadLabel } from '$lib/format';

	let { data } = $props();
	const info = $derived(data.info);
	const game = $derived(data.game);
	const prediction = $derived(game.prediction);
	const result = $derived(game.result);
	const pickTeam = $derived(
		prediction?.ats_pick ? (prediction.ats_pick === 'home' ? game.home : game.away) : null
	);
	const coveredTeam = $derived(
		result?.covered === 'home' ? game.home : result?.covered === 'away' ? game.away : null
	);
</script>

<div class="container section">
	<a class="small" href="/{info.sport}">← {info.label} upcoming</a>

	<div class="card hero section">
		<div class="meta muted small">
			{info.date_label}
			{game.date}, {game.season} · {kickoffLabel(game.kickoff)}{game.neutral ? ' · neutral site' : ''}
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
			<WinProbBar home={game.home} away={game.away} probability={prediction.win_prob} />
		{/if}
	</div>

	<MatchupDetails matchup={game} dateLabel={info.date_label} />
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
