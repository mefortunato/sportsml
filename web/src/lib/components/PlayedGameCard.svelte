<script lang="ts">
	import { links } from '$lib/links';
	import { kickoffLabel } from '$lib/format';
	import { grade } from '$lib/recent';
	import type { PlayedGame } from '$lib/types';
	import MarketTable from './MarketTable.svelte';
	import SpreadChart from './SpreadChart.svelte';
	import TeamBadge from './TeamBadge.svelte';
	import WinProbBar from './WinProbBar.svelte';

	// A played game: the final score, where the result landed next to the
	// line and the model's pre-game margin, and how each of its picks did.
	let {
		game,
		sport,
		hasSpread = true
	}: { game: PlayedGame; sport: string; hasSpread?: boolean } = $props();

	const result = $derived(game.result);
	const winner = $derived(grade(game, 'winner'));
	const verdicts = $derived(
		[
			{ label: 'Winner', grade: winner },
			...(hasSpread ? [{ label: 'Spread', grade: grade(game, 'spread') }] : []),
			{ label: 'Moneyline', grade: grade(game, 'moneyline') },
			{ label: 'Over/under', grade: grade(game, 'total') }
		].filter((v) => v.grade.hit !== null)
	);
	const homeWon = $derived(result.winner === 'home');
	const awayWon = $derived(result.winner === 'away');
</script>

<a class="card game" href={links.game(sport, game.game_id)}>
	<div class="top">
		<div class="score">
			<div class="line" class:won={awayWon}>
				<TeamBadge team={game.away} label="name" />
				<span class="points tabular">{result.away_score ?? '—'}</span>
			</div>
			<div class="line" class:won={homeWon}>
				<TeamBadge team={game.home} label="name" />
				<span class="points tabular">{result.home_score ?? '—'}</span>
			</div>
		</div>
		<div class="meta">
			<span class="muted small">Final{game.neutral ? ' · neutral' : ''}</span>
			{#if game.kickoff}<span class="muted small">{kickoffLabel(game.kickoff)}</span>{/if}
		</div>
	</div>

	<SpreadChart
		home={game.home}
		away={game.away}
		spread={game.spread}
		model={game.prediction.margin}
		result={result.margin}
	/>

	<WinProbBar home={game.home} away={game.away} probability={game.prediction.win_prob} />

	<MarketTable {game} prediction={game.prediction} {result} {hasSpread} />

	{#if verdicts.length}
		<div class="verdicts" aria-label="How the model's picks did">
			{#each verdicts as v (v.label)}
				<span class="pill" class:good={v.grade.hit} class:bad={!v.grade.hit}
					>{v.grade.hit ? '✓' : '✗'} {v.label}</span
				>
			{/each}
			{#if game.prediction_source === 'backtest'}
				<span class="muted small">walk-forward backtest prediction</span>
			{/if}
		</div>
	{/if}
</a>

<style>
	.game {
		/* a grid item: the wide market table scrolls instead of widening it */
		min-width: 0;
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
		align-items: flex-start;
		gap: 8px;
	}
	.score {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
		flex: 1;
		max-width: 300px;
	}
	.line {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		color: var(--muted);
	}
	.line.won {
		color: var(--text);
		font-weight: 700;
	}
	.points {
		font-size: 1.15rem;
		font-weight: 700;
	}
	.meta {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 2px;
		text-align: right;
	}
	.verdicts {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}
</style>
