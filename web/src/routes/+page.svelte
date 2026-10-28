<script lang="ts">
	import { links } from '$lib/links';
	import { pct, seasonsText } from '$lib/format';
	import { breakEven } from '$lib/markets';
	import type { SportInfo } from '$lib/types';

	let { data } = $props();

	// where each sport's results, box scores and lines come from
	const SOURCES: Record<string, string> = {
		nfl: 'nflverse',
		cfb: 'CollegeFootballData',
		nba: 'ESPN (schedules and box scores via sportsdataverse)'
	};

	// "College football" mid-sentence; acronyms such as NFL stay as they are
	function inSentence(label: string): string {
		return label === label.toUpperCase() ? label : label[0].toLowerCase() + label.slice(1);
	}

	// "A", "A and B", "A, B and C"
	function list(items: string[]): string {
		return items.length < 3
			? items.join(' and ')
			: `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
	}

	function seasons(info: SportInfo): string | null {
		const s = info.backtest?.seasons;
		return s?.length ? seasonsText(s, info.split_season) : null;
	}
</script>

<div class="container section home">
	{#if data.sports.length === 0}
		<div class="card">
			<h1>No data yet</h1>
			<p class="muted">Run <code>sportsml web build</code> to prepare predictions.</p>
		</div>
	{:else}
		<section class="intro">
			<h1>Game predictions, scored against Vegas</h1>
			<p class="lead">
				SportsML predicts every upcoming {list(data.sports.map((s) => inSentence(s.label)))} game: the
				margin, each team's chance to win and the combined points. Each prediction sits next to the
				betting market's spread, moneyline and over/under, so you can see where the model disagrees
				with Vegas and how often that disagreement has been right.
			</p>
		</section>

		<section class="sports" aria-label="Sports">
			{#each data.sports as info (info.sport)}
				{@const bt = info.backtest}
				<article class="card sport">
					<header>
						<h2><a href={links.upcoming(info.sport)}>{info.label}</a></h2>
						{#if seasons(info)}<span class="pill">Tested on {seasons(info)}</span>{/if}
					</header>
					{#if bt?.overall?.model}
						<dl class="record tabular">
							<div>
								<dt>Picks the winner</dt>
								<dd>
									{pct(bt.overall.model.accuracy)}
									{#if bt.overall.market}<span class="muted">Vegas {pct(bt.overall.market.accuracy)}</span>{/if}
								</dd>
							</div>
							{#if bt.ats?.win_pct != null}
								<div>
									<dt>Against the spread</dt>
									<dd>
										{pct(bt.ats.win_pct, 1)}
										<span class="muted">break-even {pct(breakEven(), 1)}</span>
									</dd>
								</div>
							{/if}
							{#if bt.totals?.record?.win_pct != null}
								<div>
									<dt>Over/under picks</dt>
									<dd>
										{pct(bt.totals.record.win_pct, 1)}
										<span class="muted">break-even {pct(breakEven(), 1)}</span>
									</dd>
								</div>
							{/if}
							<div>
								<dt>Games tested</dt>
								<dd>{bt.overall.model.n.toLocaleString('en-US')}</dd>
							</div>
						</dl>
					{/if}
					<nav class="go">
						<a class="pill accent" href={links.upcoming(info.sport)}>Upcoming games</a>
						<a class="pill" href={links.rankings(info.sport)}>Power rankings</a>
						{#if info.challenge_games}
							<a class="pill" href={links.performance(info.sport)}>Performance</a>
						{/if}
						{#if info.has_spread && info.challenge_games}
							<a class="pill" href={links.challenge(info.sport)}>Beat the model</a>
						{/if}
					</nav>
					{#if SOURCES[info.sport]}
						<p class="muted small source">Results, box scores and lines from {SOURCES[info.sport]}.</p>
					{/if}
				</article>
			{/each}
		</section>

		<section class="grid-2 explain">
			<div>
				<h2>How the predictions are made</h2>
				<p>
					A transformer, the kind of neural network behind language models, reads each team's most
					recent games: its box-score stats, results and home field, and in college football how
					strong each opponent was. From the two teams' histories it predicts the margin and the total
					points. The win probability comes from the margin, calibrated on past seasons.
				</p>
				<p>
					The model never sees the betting lines. Comparing with Vegas is the test, not an input.
				</p>
			</div>
			<div>
				<h2>How it is tested</h2>
				<p>
					Every number on this site comes from a walk-forward backtest. For each past season the model
					is trained only on earlier seasons, then that season is replayed week by week (game day
					by game day in the NBA) with each team's state updated from the games played so far. That is the same loop the live
					predictions run, so the record is what the model would really have done.
				</p>
				<p>
					Results and lines refresh daily. The model is retrained monthly during the season.
				</p>
			</div>
		</section>

		<section class="pages">
			<h2>What you can do here</h2>
			<dl>
				<div>
					<dt>Upcoming games</dt>
					<dd>
						This week's games with the Vegas line and the model's margin on one chart, current
						sportsbook prices, and the model's pick on the spread, moneyline and over/under. Sort by
						edge to see the biggest disagreements first.
					</dd>
				</div>
				<div>
					<dt>Game pages</dt>
					<dd>
						Both teams' per-game stats, records and recent results as of kickoff, every sportsbook's
						line, and a calculator to price your own line.
					</dd>
				</div>
				<div>
					<dt>Power rankings</dt>
					<dd>
						Each team's predicted margin against an average opponent on a neutral field, week by
						week, with conference filters and the teams that reached the final four.
					</dd>
				</div>
				<div>
					<dt>Performance</dt>
					<dd>
						The backtest against Vegas: accuracy, calibration, and what betting the model's edges
						would have won or lost on each market.
					</dd>
				</div>
				<div>
					<dt>Beat the model</dt>
					<dd>
						A past game with its lines and both teams' pre-game stats. Make your pick, then see the
						final score and the model's pick. Your record stays in your browser.
					</dd>
				</div>
			</dl>
		</section>

		<section class="card verdict">
			<h2>The honest answer</h2>
			<p>
				The betting market is still more accurate than the model in both sports. Beating the spread
				takes winning more than {pct(breakEven(), 1)} of bets at standard −110 prices, and the model's
				spread picks have not done that reliably. The cards above give each sport's record, and its
				Performance page breaks it down by market, season and size of edge.
			</p>
			<p class="muted small">For entertainment, not betting advice.</p>
		</section>
	{/if}
</div>

<style>
	.home {
		display: grid;
		gap: 28px;
		padding-block-end: 24px;
	}
	.intro h1 {
		font-size: clamp(1.6rem, 4vw, 2.2rem);
		text-wrap: balance;
		max-width: 22ch;
	}
	.lead {
		font-size: 1.05rem;
		line-height: 1.55;
		max-width: 65ch;
		margin: 0;
	}
	.sports {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
		gap: 16px;
	}
	.sport {
		display: grid;
		gap: 14px;
		align-content: start;
	}
	.sport header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
		flex-wrap: wrap;
	}
	.sport h2 {
		margin: 0;
		font-size: 1.3rem;
	}
	.sport h2 a {
		color: var(--text);
	}
	.record {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px 16px;
		margin: 0;
	}
	.record dt {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
	}
	.record dd {
		margin: 2px 0 0;
		font-size: 1.35rem;
		font-weight: 700;
		display: flex;
		align-items: baseline;
		gap: 8px;
		flex-wrap: wrap;
	}
	.record dd .muted {
		font-size: 0.8rem;
		font-weight: 500;
	}
	.go {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.go a:hover {
		text-decoration: none;
	}
	.source {
		margin: 0;
	}
	.explain p,
	.verdict p {
		line-height: 1.55;
		max-width: 65ch;
	}
	.pages dl {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
		gap: 16px 24px;
		margin: 0;
	}
	.pages dt {
		font-weight: 700;
	}
	.pages dd {
		margin: 4px 0 0;
		line-height: 1.5;
		color: var(--muted);
	}
	.verdict p:last-child {
		margin-bottom: 0;
	}
</style>
