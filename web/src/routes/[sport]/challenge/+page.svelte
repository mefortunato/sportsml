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
	import {
		atsRecord,
		dateText,
		handicap,
		seasonText,
		marginLabel,
		pct,
		spreadLabel,
		winLoss
	} from '$lib/format';
	import {
		americanOdds,
		MARKET_LABELS,
		pickLabel,
		SPREAD_ODDS,
		totalLabel,
		unitsLabel
	} from '$lib/markets';
	import type {
		ChallengeAnswer,
		ChallengeGame,
		Market,
		Pick,
		StatDef,
		Team,
		TeamSummary
	} from '$lib/types';
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
	let pickCard = $state<HTMLElement>();
	// the advanced stats stay open or closed from game to game
	let advancedOpen = $state(false);

	async function next() {
		if (!store) return;
		busy = true;
		failure = null;
		try {
			const seen = get(store).seen.slice(-200);
			game = await api.challengeNext(sport, seen, market);
			answer = null;
			pick = null;
			// the buttons stay where they are from game to game, so only scroll
			// when the pick card's top has gone off screen
			const top = pickCard?.getBoundingClientRect().top;
			if (top !== undefined && top < 0) window.scrollBy({ top: top - 12 });
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

	// Blind resumes: until the pick is locked in, the two teams show only as
	// "Away" and "Home". Their opponents stay named, so recent form still has
	// context. Answering reveals the real teams.
	const BLIND: Record<'home' | 'away', Team> = {
		away: { team: 'Away', name: 'Away team', abbr: 'A' },
		home: { team: 'Home', name: 'Home team', abbr: 'H' }
	};

	function blindSummary(summary: TeamSummary, side: 'home' | 'away'): TeamSummary {
		return { ...summary, team: BLIND[side] };
	}

	const shown = $derived.by<ChallengeGame | null>(() => {
		const g = game;
		if (!g || answer) return g;
		return {
			...g,
			home: BLIND.home,
			away: BLIND.away,
			summaries: {
				home: blindSummary(g.summaries.home, 'home'),
				away: blindSummary(g.summaries.away, 'away')
			}
		};
	});

	interface Choice {
		pick: Pick;
		title: string;
		line: string;
		note: string;
	}

	// a team's season at a glance, for its card: record, ATS, scoring, last 5
	interface Glance {
		record: string;
		ats: string;
		scored: string;
		allowed: string;
		form: ('W' | 'L' | 'T')[];
		games: string;
	}

	function glance(g: ChallengeGame, side: 'home' | 'away'): Glance {
		const s = g.summaries[side];
		const [scored, allowed] = g.stats;
		const fmt = (stat: StatDef | undefined) => {
			const v = stat ? s.averages[stat.key] : null;
			return v === null || v === undefined ? '—' : v.toFixed(stat?.decimals ?? 1);
		};
		return {
			record: winLoss(s.record),
			ats: atsRecord(s.ats),
			scored: fmt(scored),
			allowed: fmt(allowed),
			// oldest first, so the newest result is on the right
			form: s.recent
				.slice(0, 5)
				.reverse()
				.map((r) => (r.margin > 0 ? 'W' : r.margin < 0 ? 'L' : 'T')),
			// the season the numbers cover: this one, or last season before an opener
			games: s.current_season
				? `${s.games} game${s.games === 1 ? '' : 's'}`
				: `${seasonText(s.season, info.split_season)} season`
		};
	}

	const choices = $derived.by<Choice[]>(() => {
		const g = shown;
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
		const g = shown;
		if (!g) return '';
		if (market === 'moneyline' && g.moneyline)
			return `Moneyline ${g.away.team} ${americanOdds(g.moneyline.away)} · ${g.home.team} ${americanOdds(g.moneyline.home)}`;
		if (market === 'total') return `Over/under ${totalLabel(g.total_line)}`;
		return `Line ${spreadLabel(g.home, g.away, g.spread)}`;
	});

	const prompt: Record<Market, string> = {
		spread: 'Pick the side that covers the spread',
		moneyline: 'Pick the winner, at the posted moneyline odds',
		total: 'Pick whether the combined score goes over or under'
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
				A past game, its Vegas lines, and what both teams had done before kickoff, with the two
				teams kept anonymous: you see their stats, records and recent opponents, but not who they
				are. Choose a market, make your pick, then see the teams, the result and what the model
				picked.
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

	{#if shown}
		{@const g = shown}
		{@const teams = { away: glance(g, 'away'), home: glance(g, 'home') }}
		<div class="card section pick" bind:this={pickCard}>
			<div class="context muted small">
				{dateText(info.date_label, g.date, g.date_name)}, {seasonText(g.season, info.split_season)}{g.neutral ? ' · neutral site' : ''} · {lineText}
			</div>
			<div class="small prompt">{prompt[market]}</div>

			{#snippet panel(side: 'away' | 'home', choice: Choice | null)}
				{@const t = teams[side]}
				{@const team = side === 'home' ? g.home : g.away}
				<span class="head">
					<TeamBadge {team} size={28} label="none" />
					<span class="names">
						<span class="team-name">{team.name}</span>
						<span class="where muted">{side === 'home' ? 'Home' : 'Away'} · {t.games}</span>
					</span>
					{#if choice}
						<span class="line-box">
							<span class="line tabular">{choice.line.replace(/^(home|away) /, '')}</span>
							<span class="covers">{choice.note}</span>
						</span>
					{/if}
				</span>
				<span class="glance tabular">
					<span><b>{t.record}</b><small>Record</small></span>
					<span><b>{t.ats}</b><small>ATS</small></span>
					<span><b>{t.scored}</b><small>Scored</small></span>
					<span><b>{t.allowed}</b><small>Allowed</small></span>
				</span>
				<span class="form">
					<small class="muted">Last {t.form.length || 5}</small>
					{#each t.form as r, i (i)}
						<span class="dot" class:w={r === 'W'} class:l={r === 'L'}>{r}</span>
					{:else}
						<small class="muted">no games yet</small>
					{/each}
				</span>
			{/snippet}

			{#if market === 'total'}
				<div class="choices teams-row">
					{#each ['away', 'home'] as const as side (side)}
						<div class="choice static">{@render panel(side, null)}</div>
					{/each}
				</div>
			{/if}

			<div class="choices" class:totals={market === 'total'} role="group" aria-label={prompt[market]}>
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
							{@render panel(choice.pick, choice)}
						{:else}
							<span class="total-choice">
								<span class="total-icon" aria-hidden="true">{choice.pick === 'over' ? '▲' : '▼'}</span>
								<span class="team-name">{choice.title}</span>
								<span class="line tabular">{choice.line}</span>
								<span class="covers">{choice.note}</span>
							</span>
						{/if}
					</button>
				{/each}
			</div>

			<!-- one slot for both actions, so the button never moves -->
			{#if !answer}
				<button class="primary action" disabled={!pick || busy} onclick={submit}>
					{pick ? `Lock in ${pickLabel(pick, g.home, g.away)}` : 'Make a pick'}
				</button>
			{:else}
				<button class="primary action" onclick={next} disabled={busy}>Next game →</button>
			{/if}

			{#if answer}
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
						The model's pick for this {seasonText(g.season, info.split_season)} game comes from a
						model trained only on seasons before {seasonText(g.season, info.split_season)}.
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
				</div>
			{/if}
		</div>

		<details class="advanced section" bind:open={advancedOpen}>
			<summary class="card">
				<span>
					<strong>Advanced stats</strong>
					<span class="muted small">· {g.stats.length} stats &amp; recent games</span>
				</span>
				<span class="chevron" aria-hidden="true">▾</span>
			</summary>
			<MatchupDetails matchup={g} dateLabel={info.date_label} splitSeason={info.split_season} />
		</details>
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
		gap: 12px;
		align-items: center;
		text-align: center;
	}
	/* one line, so revealing the team names never rewraps it */
	.context {
		max-width: 100%;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.prompt {
		margin-top: -6px;
	}
	.choices {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px;
		width: 100%;
		max-width: 720px;
	}
	.choice {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 10px;
		padding: 12px;
		border-width: 2px;
		text-align: left;
		min-width: 0;
	}
	.choice.static {
		border: 1px solid var(--border);
		border-radius: var(--radius, 10px);
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
	.head {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.names {
		display: flex;
		flex-direction: column;
		min-width: 0;
		flex: 1;
		line-height: 1.2;
	}
	.team-name {
		font-weight: 700;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.where {
		font-size: 0.75rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.line-box {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		line-height: 1.15;
		flex: none;
	}
	.line {
		font-size: 1.15rem;
		font-weight: 800;
	}
	.covers {
		color: var(--muted);
		font-size: 0.75rem;
	}
	.glance {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 4px;
		padding: 8px 0;
		border-top: 1px solid var(--border);
		border-bottom: 1px solid var(--border);
	}
	.glance > span {
		display: flex;
		flex-direction: column;
		align-items: center;
		min-width: 0;
		line-height: 1.2;
	}
	.glance b {
		font-size: 0.95rem;
		white-space: nowrap;
	}
	.glance small {
		color: var(--muted);
		font-size: 0.7rem;
	}
	.form {
		display: flex;
		align-items: center;
		gap: 4px;
		min-width: 0;
	}
	.form small {
		font-size: 0.7rem;
		margin-right: 2px;
	}
	.dot {
		display: inline-grid;
		place-items: center;
		width: 18px;
		height: 18px;
		border-radius: 4px;
		font-size: 0.65rem;
		font-weight: 700;
		background: var(--border);
		color: var(--muted);
		flex: none;
	}
	.dot.w {
		background: var(--good-soft);
		color: var(--good);
	}
	.dot.l {
		background: var(--bad-soft);
		color: var(--bad);
	}
	.totals .choice {
		align-items: center;
	}
	.total-choice {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	.total-icon {
		font-size: 1.1rem;
		color: var(--accent);
	}
	.action {
		min-width: 240px;
		max-width: 100%;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
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
	.advanced > summary {
		list-style: none;
		cursor: pointer;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}
	.advanced > summary::-webkit-details-marker {
		display: none;
	}
	.advanced > summary:hover {
		border-color: var(--accent);
	}
	.chevron {
		transition: transform 0.15s;
		color: var(--muted);
	}
	.advanced[open] .chevron {
		transform: rotate(180deg);
	}
	@media (max-width: 520px) {
		.choices {
			gap: 8px;
		}
		.choice {
			padding: 10px 8px;
			gap: 8px;
		}
		.head {
			flex-wrap: wrap;
			gap: 6px;
		}
		.line-box {
			flex-direction: row;
			align-items: baseline;
			gap: 4px;
			width: 100%;
		}
		.glance {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			row-gap: 6px;
		}
		.form small:first-child {
			display: none;
		}
		.dot {
			width: 16px;
			height: 16px;
		}
	}
</style>
