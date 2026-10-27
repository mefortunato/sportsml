<script lang="ts">
	import { page } from '$app/state';
	import { api } from '$lib/api';
	import { challengeStore, type ChallengeRecord, type ChallengeStore } from '$lib/challenge';
	import MatchupDetails from '$lib/components/MatchupDetails.svelte';
	import ProbabilityCompare from '$lib/components/ProbabilityCompare.svelte';
	import Scoreboard from '$lib/components/Scoreboard.svelte';
	import SpreadChart from '$lib/components/SpreadChart.svelte';
	import TeamBadge from '$lib/components/TeamBadge.svelte';
	import TotalChart from '$lib/components/TotalChart.svelte';
	import { handicap, marginLabel, pct, spreadLabel } from '$lib/format';
	import {
		americanOdds,
		MARKET_LABELS,
		pickLabel,
		SPREAD_ODDS,
		totalLabel,
		unitsLabel
	} from '$lib/markets';
	import type { ChallengeAnswer, ChallengeGame, Market, Pick } from '$lib/types';
	import { untrack } from 'svelte';
	import { get } from 'svelte/store';

	let { data } = $props();
	const info = $derived(data.info);
	const sport = $derived(page.params.sport ?? '');
	const markets = $derived<Market[]>(info.markets?.length ? info.markets : ['spread']);

	const MARKET_KEY = 'sportsml:challenge-market';
	function savedMarket(): Market | null {
		try {
			return (globalThis.localStorage?.getItem(MARKET_KEY) as Market | null) ?? null;
		} catch {
			return null;
		}
	}

	let market = $state<Market>('spread');
	let store = $state<ChallengeStore | null>(null);
	let record = $state<ChallengeRecord | null>(null);
	let game = $state<ChallengeGame | null>(null);
	let answer = $state<ChallengeAnswer | null>(null);
	let pick = $state<Pick | null>(null);
	let busy = $state(false);
	let failure = $state<string | null>(null);

	async function next() {
		if (!store) return;
		busy = true;
		failure = null;
		try {
			const seen = get(store).seen.slice(-200);
			game = await api.challengeNext(sport, seen, market);
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
			answer = await api.challengeAnswer(sport, game.game_id, pick, market);
			store.record(answer);
		} catch (error) {
			failure = String(error);
		} finally {
			busy = false;
		}
	}

	function choose(next: Market) {
		if (next === market) return;
		market = next;
		try {
			globalThis.localStorage?.setItem(MARKET_KEY, next);
		} catch {
			// remembering the market is only a convenience
		}
	}

	$effect(() => {
		// the last market played here, if this sport offers it
		const saved = untrack(savedMarket);
		const offered = markets;
		untrack(() => {
			if (saved && offered.includes(saved)) market = saved;
			else if (!offered.includes(market)) market = offered[0];
		});
	});

	$effect(() => {
		// one record per sport and market, kept in this browser. Only `sport`
		// and `market` are dependencies: next() reads and writes state.
		const current = challengeStore(sport, market);
		const unsubscribe = current.subscribe((value) => (record = value));
		untrack(() => {
			store = current;
			next();
		});
		return unsubscribe;
	});

	interface Choice {
		pick: Pick;
		title: string;
		line: string;
		note: string;
	}

	const choices = $derived.by<Choice[]>(() => {
		const g = game;
		if (!g) return [];
		if (market === 'moneyline' && g.moneyline) {
			return (['away', 'home'] as const).map((side) => ({
				pick: side,
				title: (side === 'home' ? g.home : g.away).name,
				line: americanOdds(g.moneyline?.[side]),
				note: 'wins'
			}));
		}
		if (market === 'total') {
			const odds = g.total_odds;
			return (['over', 'under'] as const).map((side) => ({
				pick: side,
				title: side === 'over' ? 'Over' : 'Under',
				line: totalLabel(g.total_line),
				note: odds ? americanOdds(odds[side]) : americanOdds(SPREAD_ODDS)
			}));
		}
		return (['away', 'home'] as const).map((side) => ({
			pick: side,
			title: (side === 'home' ? g.home : g.away).name,
			line: `${side} ${handicap(g.spread ?? 0, side)}`,
			note: 'covers'
		}));
	});

	const lineText = $derived.by(() => {
		const g = game;
		if (!g) return '';
		if (market === 'moneyline' && g.moneyline)
			return `Moneyline ${g.away.team} ${americanOdds(g.moneyline.away)} · ${g.home.team} ${americanOdds(g.moneyline.home)}`;
		if (market === 'total') return `Over/under ${totalLabel(g.total_line)}`;
		return `Line ${spreadLabel(g.home, g.away, g.spread)}`;
	});

	const prompt: Record<Market, string> = {
		spread: 'Pick the side that covers the spread',
		moneyline: 'Pick the winner, at the posted moneyline odds',
		total: 'Pick whether the combined score goes over or under the line'
	};

	function outcomeText(a: ChallengeAnswer, g: ChallengeGame): string {
		if (a.market === 'moneyline') return `${pickLabel(a.outcome, g.home, g.away)} won`;
		if (a.market === 'total')
			return `${a.result.total} points · ${a.outcome === 'over' ? 'over' : 'under'} ${totalLabel(a.total_line)}`;
		return `${pickLabel(a.outcome, g.home, g.away)} covered`;
	}

	function modelText(a: ChallengeAnswer, g: ChallengeGame): string {
		const m = a.model;
		if (a.market === 'moneyline') {
			const side = m.pick === 'away' ? 'away' : 'home';
			const team = side === 'home' ? g.home : g.away;
			const p = side === 'home' ? m.win_prob : 1 - m.win_prob;
			const v = m.market_prob == null ? null : side === 'home' ? m.market_prob : 1 - m.market_prob;
			return `${team.team} ${pct(p)}${v === null ? '' : ` vs Vegas ${pct(v)}`}`;
		}
		if (a.market === 'total') return `${m.total?.toFixed(1) ?? '—'} points`;
		return marginLabel(g.home, g.away, m.margin);
	}
</script>

<div class="container section">
	<div class="intro">
		<div>
			<h1>Beat the model</h1>
			<p class="muted">
				A past game, its Vegas lines, and what both teams had done before kickoff. Choose a market,
				make your pick, then see the result and what the model picked.
			</p>
			<p class="muted small">
				The model never saw these games: its pick for a game from a given season comes from a
				model trained only on earlier seasons.
			</p>
		</div>
	</div>

	{#if markets.length > 1}
		<div class="tabs" role="tablist" aria-label="Market">
			{#each markets as m (m)}
				<button
					role="tab"
					aria-selected={market === m}
					class:active={market === m}
					disabled={busy}
					onclick={() => choose(m)}>{MARKET_LABELS[m]}</button
				>
			{/each}
		</div>
	{/if}

	{#if record}
		<Scoreboard {record} {market} onreset={() => store?.reset()} />
	{/if}

	{#if failure}
		<p class="error">{failure}</p>
	{/if}

	{#if game}
		{@const g = game}
		<div class="card section pick">
			<div class="muted small">
				{info.date_label}
				{g.date}, {g.season}{g.neutral ? ' · neutral site' : ''} · {lineText}
			</div>
			<div class="small">{prompt[market]}</div>

			<div class="choices">
				{#each choices as choice (choice.pick)}
					{@const chosen = pick === choice.pick}
					{@const won = answer && answer.outcome === choice.pick}
					<button
						class="choice"
						class:chosen
						class:won
						class:lost={answer && chosen && !won}
						disabled={!!answer || busy}
						onclick={() => (pick = choice.pick)}
					>
						{#if choice.pick === 'home' || choice.pick === 'away'}
							<TeamBadge team={choice.pick === 'home' ? g.home : g.away} size={48} label="none" />
						{:else}
							<span class="total-icon" aria-hidden="true">{choice.pick === 'over' ? '▲' : '▼'}</span>
						{/if}
						<span class="team-name">{choice.title}</span>
						<span class="line tabular">{choice.line}</span>
						<span class="covers">{choice.note}</span>
					</button>
				{/each}
			</div>

			{#if !answer}
				<button class="primary submit" disabled={!pick || busy} onclick={submit}>
					{pick ? `Lock in ${pickLabel(pick, g.home, g.away)}` : 'Make a pick'}
				</button>
			{:else}
				<div class="reveal">
					<div class="final">
						Final: {g.away.team}
						<strong class="tabular">{answer.result.away_score}</strong>
						– <strong class="tabular">{answer.result.home_score}</strong>
						{g.home.team}
						· {outcomeText(answer, g)}
					</div>
					<div class="verdicts">
						<span class="pill" class:good={answer.correct} class:bad={!answer.correct}>
							You: {pickLabel(answer.pick, g.home, g.away)} {answer.correct ? '✓' : '✗'}
							{unitsLabel(answer.units, 2)}
						</span>
						<span class="pill" class:good={answer.model.correct} class:bad={!answer.model.correct}>
							Model: {modelText(answer, g)} → {pickLabel(answer.model.pick, g.home, g.away)}
							{answer.model.correct ? '✓' : '✗'}
							{unitsLabel(answer.model.units, 2)}
						</span>
					</div>
					<p class="muted small trained">
						The model's pick for this {g.season} game comes from a model trained only on seasons
						before {g.season}.
					</p>
					<div class="chart">
						{#if answer.market === 'moneyline'}
							<ProbabilityCompare
								home={g.home}
								away={g.away}
								model={answer.model.win_prob}
								market={answer.model.market_prob ?? null}
							/>
						{:else if answer.market === 'total'}
							<TotalChart
								line={answer.total_line ?? null}
								model={answer.model.total ?? null}
								result={answer.result.total ?? null}
							/>
						{:else}
							<SpreadChart
								home={g.home}
								away={g.away}
								spread={answer.spread ?? g.spread}
								model={answer.model.margin}
								result={answer.result.margin}
							/>
						{/if}
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
	.tabs {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-bottom: 12px;
	}
	.tabs button {
		padding: 6px 14px;
		border-radius: 999px;
	}
	.tabs button.active {
		border-color: var(--accent);
		background: var(--accent-soft);
		font-weight: 700;
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
	.total-icon {
		font-size: 2rem;
		line-height: 48px;
		height: 48px;
		color: var(--accent);
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
