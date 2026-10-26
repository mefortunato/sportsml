<script lang="ts">
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import { challengeStore, type ChallengeRecord, type ChallengeStore } from '$lib/challenge';
	import MatchupDetails from '$lib/components/MatchupDetails.svelte';
	import Scoreboard from '$lib/components/Scoreboard.svelte';
	import SpreadChart from '$lib/components/SpreadChart.svelte';
	import TeamBadge from '$lib/components/TeamBadge.svelte';
	import { handicap, marginLabel, spreadLabel } from '$lib/format';
	import type { ChallengeAnswer, ChallengeGame, Side } from '$lib/types';
	import { untrack } from 'svelte';
	import { get } from 'svelte/store';

	let { data } = $props();
	const info = $derived(data.info);
	const sport = $derived(page.params.sport ?? '');

	let store = $state<ChallengeStore | null>(null);
	let record = $state<ChallengeRecord | null>(null);
	let game = $state<ChallengeGame | null>(null);
	let answer = $state<ChallengeAnswer | null>(null);
	let pick = $state<Side | null>(null);
	let busy = $state(false);
	let failure = $state<string | null>(null);

	async function next() {
		if (!store) return;
		busy = true;
		failure = null;
		try {
			const seen = get(store).seen.slice(-200);
			game = await api.challengeNext(sport, seen);
			answer = null;
			pick = null;
			window.scrollTo({ top: 0 });
		} catch (error) {
			failure = String(error);
		} finally {
			busy = false;
		}
	}

	async function submit() {
		if (!store || !game || !pick) return;
		busy = true;
		try {
			answer = await api.challengeAnswer(sport, game.game_id, pick);
			store.record(answer);
		} catch (error) {
			failure = String(error);
		} finally {
			busy = false;
		}
	}

	$effect(() => {
		// one record per sport, kept in this browser. Only `sport` is a
		// dependency: next() reads and writes state, which would re-run this.
		const current = challengeStore(sport);
		const unsubscribe = current.subscribe((value) => (record = value));
		untrack(() => {
			store = current;
			next();
		});
		return unsubscribe;
	});

	const teamOf = (side: Side | 'push' | null) =>
		!game || !side || side === 'push' ? null : side === 'home' ? game.home : game.away;
</script>

<div class="container section">
	<div class="intro">
		<div>
			<h1>Beat the model</h1>
			<p class="muted">
				A past game, its Vegas line, and what both teams had done before kickoff. Pick the side
				that covers the spread, then see the result and what the model picked.
			</p>
			<p class="muted small">
				The model never saw these games: its pick for a game from a given season comes from a
				model trained only on earlier seasons.
			</p>
		</div>
	</div>

	{#if record}
		<Scoreboard {record} onreset={() => store?.reset()} />
	{/if}

	{#if failure}
		<p class="error">{failure}</p>
	{/if}

	{#if game}
		{@const g = game}
		<div class="card section pick">
			<div class="muted small">
				{info.date_label}
				{g.date}, {g.season}{g.neutral ? ' · neutral site' : ''} · Line {spreadLabel(
					g.home,
					g.away,
					g.spread
				)}
			</div>

			<div class="choices">
				{#each [['away', g.away], ['home', g.home]] as const as [side, team] (side)}
					{@const chosen = pick === side}
					{@const won = answer && answer.covered === side}
					<button
						class="choice"
						class:chosen
						class:won
						class:lost={answer && chosen && !won}
						disabled={!!answer || busy}
						onclick={() => (pick = side)}
					>
						<TeamBadge {team} size={48} label="none" />
						<span class="team-name">{team.name}</span>
						<span class="line tabular">{side === 'home' ? 'home' : 'away'} {handicap(g.spread ?? 0, side)}</span>
						<span class="covers">covers</span>
					</button>
				{/each}
			</div>

			{#if !answer}
				<button class="primary submit" disabled={!pick || busy} onclick={submit}>
					{pick ? `Lock in ${(pick === 'home' ? g.home : g.away).team}` : 'Pick a side'}
				</button>
			{:else}
				{@const covered = teamOf(answer.covered)}
				{@const modelTeam = teamOf(answer.model.ats_pick)}
				<div class="reveal">
					<div class="final">
						Final: {g.away.team}
						<strong class="tabular">{answer.result.away_score}</strong>
						– <strong class="tabular">{answer.result.home_score}</strong>
						{g.home.team}
						· {covered ? `${covered.team} covered` : 'Push'}
					</div>
					<div class="verdicts">
						<span class="pill" class:good={answer.correct} class:bad={!answer.correct}>
							You: {(answer.pick === 'home' ? g.home : g.away).team} {answer.correct ? '✓' : '✗'}
						</span>
						<span class="pill" class:good={answer.model.correct} class:bad={!answer.model.correct}>
							Model: {marginLabel(g.home, g.away, answer.model.margin)} → {modelTeam?.team ?? '—'}
							{answer.model.correct ? '✓' : '✗'}
						</span>
					</div>
					<p class="muted small trained">
						The model's pick for this {g.season} game comes from a model trained only on seasons
						before {g.season}.
					</p>
					<div class="chart">
						<SpreadChart
							home={g.home}
							away={g.away}
							spread={answer.spread}
							model={answer.model.margin}
							result={answer.result.margin}
						/>
					</div>
					<button class="primary" onclick={next} disabled={busy}>Next game →</button>
				</div>
			{/if}
		</div>

		<MatchupDetails matchup={g} dateLabel={info.date_label} />
	{:else if busy}
		<p class="muted section">Loading a game…</p>
	{/if}
</div>

<style>
	.intro p {
		max-width: 720px;
	}
	.pick {
		display: flex;
		flex-direction: column;
		gap: 16px;
		align-items: center;
		text-align: center;
	}
	.choices {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 16px;
		width: 100%;
		max-width: 640px;
	}
	.choice {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		padding: 16px;
		border-width: 2px;
	}
	.choice.chosen {
		border-color: var(--accent);
		background: var(--accent-soft);
	}
	.choice.won {
		border-color: var(--good);
		background: var(--good-soft);
	}
	.choice.lost {
		border-color: var(--bad);
		background: var(--bad-soft);
	}
	.choice:disabled {
		opacity: 1;
		cursor: default;
	}
	.team-name {
		font-weight: 700;
	}
	.line {
		font-size: 1.2rem;
		font-weight: 800;
	}
	.covers {
		color: var(--muted);
		font-size: 0.85rem;
	}
	.submit {
		min-width: 220px;
	}
	.reveal {
		display: flex;
		flex-direction: column;
		gap: 12px;
		align-items: center;
		width: 100%;
	}
	.final {
		font-size: 1.15rem;
	}
	.trained {
		margin: 0;
		text-align: center;
	}
	.verdicts {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		justify-content: center;
	}
	.chart {
		width: 100%;
		max-width: 640px;
	}
</style>
