<script lang="ts">
	import { dateText, pct, seasonText } from '$lib/format';
	import { links } from '$lib/links';
	import { unitsLabel } from '$lib/markets';
	import PlayedGameCard from '$lib/components/PlayedGameCard.svelte';
	import { headerSearch, useHeaderSearch } from '$lib/headerSearch.svelte';
	import { matchesGame } from '$lib/search';
	import {
		RECENT_SORT_LABELS,
		sortPlayed,
		summarize,
		type MarketRecord,
		type RecentSort,
		type RecentSummary
	} from '$lib/recent';

	let { data } = $props();
	const info = $derived(data.info);
	const recent = $derived(data.recent);
	// oldest to newest, like the upcoming page's dates
	const dates = $derived([...recent.dates].reverse());
	const dayText = $derived(dateText(info.date_label, recent.date, recent.name));
	const windowText = $derived(
		`Last ${recent.dates.length} ${info.date_label.toLowerCase()}${recent.dates.length === 1 ? '' : 's'}`
	);
	const summaries = $derived([
		{ title: dayText, summary: summarize(recent.games) },
		{ title: windowText, summary: summarize(recent.all) }
	]);
	const replayed = $derived(recent.all.some((g) => g.prediction_source === 'replay'));
	const backtested = $derived(recent.all.some((g) => g.prediction_source === 'backtest'));

	const SORTS: RecentSort[] = ['kickoff', 'miss', 'edge'];
	const options = $derived(
		SORTS.filter((s) => s !== 'edge' || recent.games.some((g) => g.prediction.edge != null))
	);
	let sort = $state<RecentSort>('kickoff');
	const active = $derived(options.includes(sort) ? sort : 'kickoff');
	// kept across dates: the reader is following one team back through the window
	useHeaderSearch();
	const query = $derived(headerSearch.query);
	const searching = $derived(query.trim() !== '');
	const games = $derived(sortPlayed(recent.games, active).filter((g) => matchesGame(g, query)));
	// the window's other dates the searched team played on, newest first
	const elsewhere = $derived(
		searching
			? recent.dates.filter(
					(d) =>
						!(d.season === recent.season && d.date === recent.date) &&
						recent.all.some((g) => g.season === d.season && g.date === d.date && matchesGame(g, query))
				)
			: []
	);

	const record = (r: MarketRecord) => `${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ''}`;
	const rate = (r: MarketRecord) =>
		r.wins + r.losses ? pct(r.wins / (r.wins + r.losses)) : '—';

	interface Line {
		label: string;
		model: string;
		vegas: string;
		/** Whether the model beat Vegas (null: nothing to compare). */
		better: boolean | null;
		note?: string;
	}

	function lines(s: RecentSummary): Line[] {
		const out: Line[] = [];
		const w = s.winners;
		out.push({
			label: 'Picked the winner',
			model: `${record(w.model)} (${rate(w.model)})`,
			vegas: w.market ? `${record(w.market)} (${rate(w.market)})` : '—',
			better: w.market ? w.model.wins > w.market.wins : null
		});
		const bets: [string, MarketRecord | null][] = [
			['Against the spread', info.has_spread ? s.spread : null],
			['Moneyline', s.moneyline],
			['Over/under', s.total]
		];
		for (const [label, r] of bets) {
			if (!r) continue;
			out.push({
				label,
				model: `${record(r)} (${rate(r)})`,
				vegas: '',
				better: null,
				note: unitsLabel(r.units)
			});
		}
		if (s.margin)
			out.push({
				label: 'Avg margin miss',
				model: `${s.margin.model.toFixed(1)} pts`,
				vegas: `${s.margin.market.toFixed(1)} pts`,
				better: s.margin.model < s.margin.market
			});
		if (s.points)
			out.push({
				label: 'Avg total miss',
				model: `${s.points.model.toFixed(1)} pts`,
				vegas: `${s.points.market.toFixed(1)} pts`,
				better: s.points.model < s.points.market
			});
		if (s.brier)
			out.push({
				label: 'Brier score',
				model: s.brier.model.toFixed(3),
				vegas: s.brier.market.toFixed(3),
				better: s.brier.model < s.brier.market
			});
		return out;
	}
</script>

<div class="container section">
	<div class="heading">
		<div>
			<h1>
				{info.label} · {recent.date === null ? 'Recent games' : dayText}
				{#if recent.season}<span class="muted">{seasonText(recent.season, info.split_season)}</span>{/if}
			</h1>
			<p class="muted small legend">
				{#if info.has_spread}<span class="key vegas"></span> Vegas line{/if}
				<span class="key model"></span> model's pre-game margin
				<span class="key final"></span> final margin · right of center favors the home team
			</p>
		</div>
		{#if dates.length > 1}
			<nav class="dates">
				{#each dates as d (`${d.season}-${d.date}`)}
					<a
						class="pill"
						class:accent={d.season === recent.season && d.date === recent.date}
						href={links.recent(info.sport, d.season, d.date)}
						>{dateText(info.date_label, d.date, d.name)}</a
					>
				{/each}
			</nav>
		{/if}
	</div>

	{#if recent.all.length === 0}
		<div class="card">
			<h2>No recent games</h2>
			<p class="muted">
				No games have been played lately. See the
				<a href={links.upcoming(info.sport)}>upcoming games</a> or how the model did over whole
				seasons on the <a href={links.performance(info.sport)}>performance page</a>.
			</p>
		</div>
	{:else}
		<div class="summaries">
			{#each summaries as { title, summary } (title)}
				<section class="card summary">
					<h2>{title} <span class="muted small">{summary.games} games</span></h2>
					<table class="small tabular">
						<thead>
							<tr><th></th><th>Model</th><th>Vegas</th></tr>
						</thead>
						<tbody>
							{#each lines(summary) as line (line.label)}
								<tr>
									<th scope="row">{line.label}</th>
									<td class:better={line.better === true}>{line.model}</td>
									<td>
										{#if line.note}
											<span
												class:win={line.note.startsWith('+')}
												class:loss={!line.note.startsWith('+') && line.note !== '0.0 u'}
												>{line.note}</span
											>
										{:else}{line.vegas}{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</section>
			{/each}
		</div>
		<p class="muted small note">
			Records are the model's picks at the lines the games closed at (spread and over/under at
			−110, moneyline at the posted odds); the units column is the profit from 1 unit on each.
			{#if replayed}
				Predictions are the model's before each game: replayed with each team's state built from
				earlier games only, by a model not trained on this season.
			{/if}
			{#if backtested}
				Games from backtested seasons use the walk-forward backtest's predictions.
			{/if}
		</p>

		{#if recent.games.length}
			<div class="toolbar">
				{#if options.length > 1}
					<div class="sort" role="group" aria-label="Order games">
						<span class="muted small">Sort by</span>
						{#each options as option (option)}
							<button
								class="pill"
								class:accent={active === option}
								aria-pressed={active === option}
								onclick={() => (sort = option)}>{RECENT_SORT_LABELS[option]}</button
							>
						{/each}
					</div>
				{/if}
			</div>
			{#if searching}
				<p class="muted small found" aria-live="polite">
					{games.length
						? `${games.length} of ${recent.games.length} games`
						: `No games for “${query.trim()}” this ${info.date_label.toLowerCase()}`}{#if elsewhere.length}
						{' · also played '}
						{#each elsewhere as d, i (`${d.season}-${d.date}`)}
							{i ? ', ' : ''}<a href={links.recent(info.sport, d.season, d.date)}
								>{dateText(info.date_label, d.date, d.name)}</a
							>
						{/each}
					{/if}
				</p>
			{/if}
			<div class="games">
				{#each games as game (game.game_id)}
					<PlayedGameCard {game} sport={info.sport} hasSpread={info.has_spread} />
				{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	.heading {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	.legend {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
		margin: 0;
	}
	.key {
		display: inline-block;
		width: 10px;
		height: 10px;
		margin-left: 6px;
	}
	.key.vegas {
		background: var(--vegas);
		transform: rotate(45deg);
	}
	.key.model {
		background: var(--accent);
		border-radius: 50%;
	}
	.key.final {
		background: var(--text);
		border-radius: 50%;
	}
	.dates {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.dates a:hover {
		text-decoration: none;
	}
	.summaries {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr));
		gap: 16px;
	}
	.summary {
		min-width: 0;
		overflow-x: auto;
	}
	.summary h2 {
		font-size: 1rem;
		margin: 0 0 8px;
	}
	table {
		width: 100%;
		border-collapse: collapse;
	}
	th,
	td {
		padding: 4px 6px;
		text-align: left;
		white-space: nowrap;
		border-bottom: 1px solid var(--border);
	}
	thead th {
		color: var(--muted);
		font-weight: 600;
		font-size: 0.75rem;
	}
	tbody th {
		color: var(--muted);
		font-weight: 600;
	}
	tbody tr:last-child th,
	tbody tr:last-child td {
		border-bottom: none;
	}
	.better {
		color: var(--good);
		font-weight: 700;
	}
	.win {
		color: var(--good);
		font-weight: 600;
	}
	.loss {
		color: var(--bad);
		font-weight: 600;
	}
	.note {
		margin: 12px 0 16px;
	}
	.toolbar {
		display: flex;
		align-items: center;
		gap: 8px 16px;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	.sort {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}
	.found {
		margin: -8px 0 16px;
	}
	.games {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 480px), 1fr));
		gap: 16px;
	}
</style>
