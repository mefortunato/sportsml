<script lang="ts">
	import { pct } from '$lib/format';
	import { MARKET_LABELS, pickLabel } from '$lib/markets';
	import {
		KELLY_FRACTION,
		noVig,
		priceMoneyline,
		priceSpread,
		priceTotal,
		validOdds,
		type Quote
	} from '$lib/pricing';
	import type { BookLine, GameHeader, Market, Prediction, Pricing } from '$lib/types';

	// Price the line your sportsbook offers: starts at the Vegas consensus;
	// change any number and every pick, probability and stake updates.
	let {
		game,
		prediction,
		pricing,
		books = []
	}: {
		game: GameHeader;
		prediction: Prediction;
		pricing: Pricing;
		/** Sportsbooks' current lines, to load one into the calculator. */
		books?: (BookLine & { book: string })[];
	} = $props();

	// books quote the home team's handicap: minus the expected home margin
	const consensus = () => ({
		handicap: game.spread == null ? 0 : -game.spread,
		spreadHome: -110,
		spreadAway: -110,
		mlHome: game.moneyline?.home ?? -110,
		mlAway: game.moneyline?.away ?? -110,
		total: game.total_line ?? Math.round((prediction.total ?? 44) * 2) / 2,
		over: game.total_odds?.over ?? -110,
		under: game.total_odds?.under ?? -110
	});
	let line = $state(consensus());
	let source = $state('');
	const reset = () => {
		line = consensus();
		source = '';
	};
	// a book's line, its missing markets and prices from the consensus
	function load(name: string) {
		const b = books.find((x) => x.book === name);
		if (!b) return reset();
		const base = consensus();
		line = {
			handicap: b.spread == null ? base.handicap : -b.spread,
			spreadHome: b.spread_home_odds ?? -110,
			spreadAway: b.spread_away_odds ?? -110,
			mlHome: b.ml_home ?? base.mlHome,
			mlAway: b.ml_away ?? base.mlAway,
			total: b.total ?? base.total,
			over: b.over_odds ?? -110,
			under: b.under_odds ?? -110
		};
	}

	// the moneyline is moved toward the consensus market, not toward the
	// price you enter (a better price is what you are looking for)
	const marketProb = $derived(
		game.moneyline ? noVig(game.moneyline.home, game.moneyline.away) : undefined
	);

	interface Row {
		market: Market;
		quotes: [Quote, Quote] | null;
		describe: (q: Quote) => string;
	}

	const rows = $derived.by<Row[]>(() => {
		const out: Row[] = [];
		const spreadOk = validOdds(line.spreadHome) && validOdds(line.spreadAway) && Number.isFinite(line.handicap);
		out.push({
			market: 'spread',
			quotes: spreadOk
				? priceSpread(prediction, -line.handicap, { home: line.spreadHome, away: line.spreadAway }, pricing)
				: null,
			describe: (q) => {
				const h = q.pick === 'home' ? line.handicap : -line.handicap;
				return `${pickLabel(q.pick, game.home, game.away)} ${h > 0 ? '+' : ''}${h === 0 ? 'PK' : h}`;
			}
		});
		const mlOk = validOdds(line.mlHome) && validOdds(line.mlAway);
		out.push({
			market: 'moneyline',
			quotes: mlOk
				? priceMoneyline(prediction, { home: line.mlHome, away: line.mlAway }, pricing, marketProb)
				: null,
			describe: (q) => pickLabel(q.pick, game.home, game.away)
		});
		const totalOk = validOdds(line.over) && validOdds(line.under) && Number.isFinite(line.total);
		const total = totalOk
			? priceTotal(prediction, line.total, { over: line.over, under: line.under }, pricing)
			: null;
		if (total || prediction.total != null) {
			out.push({
				market: 'total',
				quotes: total,
				describe: (q) => `${pickLabel(q.pick, game.home, game.away)} ${line.total}`
			});
		}
		return out;
	});

	const odds = (value: number) => (value > 0 ? `+${value}` : `${value}`);
	const trustText = $derived(
		(['spread', 'moneyline', 'total'] as Market[])
			.filter((m) => pricing.trust[m] !== undefined)
			.map((m) => `${MARKET_LABELS[m].toLowerCase()} ${pct(pricing.trust[m] ?? 0)}`)
			.join(', ')
	);
</script>

<div class="card calc">
	<div class="head">
		<h2>Price your line</h2>
		<div class="actions">
			{#if books.length}
				<select
					bind:value={source}
					onchange={() => load(source)}
					aria-label="Load a sportsbook's line"
				>
					<option value="">Consensus</option>
					{#each books as b (b.book)}
						<option value={b.book}>{b.book}</option>
					{/each}
				</select>
			{/if}
			<button class="small" onclick={reset}>Reset to Vegas</button>
		</div>
	</div>
	<p class="muted small">
		Enter the line and odds your sportsbook offers. The model's prediction doesn't change with the
		odds, so every pick and stake below updates as you type.
	</p>

	<div class="inputs">
		<fieldset>
			<legend>Spread</legend>
			<label>
				<span>{game.home.team} handicap</span>
				<input type="number" step="0.5" bind:value={line.handicap} aria-label="{game.home.team} spread handicap" />
			</label>
			<label>
				<span>{game.home.team} odds</span>
				<input type="number" step="5" bind:value={line.spreadHome} aria-label="{game.home.team} spread odds" />
			</label>
			<label>
				<span>{game.away.team} odds</span>
				<input type="number" step="5" bind:value={line.spreadAway} aria-label="{game.away.team} spread odds" />
			</label>
		</fieldset>
		<fieldset>
			<legend>Moneyline</legend>
			<label>
				<span>{game.home.team}</span>
				<input type="number" step="5" bind:value={line.mlHome} aria-label="{game.home.team} moneyline" />
			</label>
			<label>
				<span>{game.away.team}</span>
				<input type="number" step="5" bind:value={line.mlAway} aria-label="{game.away.team} moneyline" />
			</label>
		</fieldset>
		{#if prediction.total != null}
			<fieldset>
				<legend>Over/under</legend>
				<label>
					<span>Total</span>
					<input type="number" step="0.5" bind:value={line.total} aria-label="Total line" />
				</label>
				<label>
					<span>Over odds</span>
					<input type="number" step="5" bind:value={line.over} aria-label="Over odds" />
				</label>
				<label>
					<span>Under odds</span>
					<input type="number" step="5" bind:value={line.under} aria-label="Under odds" />
				</label>
			</fieldset>
		{/if}
	</div>

	<div class="scroll">
		<table class="small">
			<thead>
				<tr>
					<th>Bet</th>
					<th class="num">Odds</th>
					<th class="num" title="The model's probability, moved toward the market by how much its disagreements have paid; below it the win rate the odds need to break even">Win chance</th>
					<th class="num">EV / $100</th>
					<th class="num">Stake</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as row (row.market)}
					<tr class="group"><th colspan="5">{MARKET_LABELS[row.market]}</th></tr>
					{#if row.quotes}
						{#each row.quotes as q (q.pick)}
							<tr class:value={q.ev > 0}>
								<td>{row.describe(q)}</td>
								<td class="num tabular">{odds(q.odds)}</td>
								<td class="num tabular" title="model alone: {pct(q.raw, 1)}">
									{pct(q.prob, 1)}
									<span class="be muted">need {pct(q.breakEven, 1)}</span>
								</td>
								<td class="num tabular ev">{q.ev >= 0 ? '+' : '−'}${Math.abs(q.ev * 100).toFixed(2)}</td>
								<td class="num tabular">{q.stake > 0 ? pct(q.stake, 1) : 'no bet'}</td>
							</tr>
						{/each}
					{:else}
						<tr><td colspan="5" class="muted">Enter a line and odds (at or beyond ±100).</td></tr>
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
	<p class="muted small note">
		Win chances are the model's, moved toward the market by how much of its disagreement has been
		right in the backtest ({trustText}; 0% means its disagreements haven't paid, so only a better
		price than the market's can make a bet worthwhile). Stakes are shares of your bankroll at
		{pct(KELLY_FRACTION)} Kelly.
		Hover a win chance for the model's own number. For entertainment, not betting advice.
	</p>
</div>

<style>
	.calc {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	h2 {
		margin: 0;
	}
	.head button {
		padding: 4px 12px;
	}
	.actions {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	select {
		font: inherit;
		font-size: 0.85rem;
		padding: 4px 6px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text);
	}
	.inputs {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 10px;
	}
	fieldset {
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 8px 10px;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}
	legend {
		font-weight: 700;
		font-size: 0.85rem;
		padding: 0 4px;
	}
	label {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		font-size: 0.85rem;
	}
	input {
		width: 90px;
		font: inherit;
		font-variant-numeric: tabular-nums;
		padding: 4px 6px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text);
		text-align: right;
	}
	.scroll {
		overflow-x: auto;
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
	tr.group th {
		font-weight: 700;
		padding-top: 10px;
	}
	.num {
		text-align: right;
	}
	.be {
		display: block;
		font-size: 0.75rem;
	}
	tr.value td {
		background: var(--good-soft);
	}
	tr.value .ev {
		color: var(--good);
		font-weight: 700;
	}
	.note {
		margin: 0;
	}
	@media (max-width: 480px) {
		th,
		td {
			padding: 4px 3px;
		}
		td {
			white-space: normal;
		}
		td.num {
			white-space: nowrap;
		}
	}
</style>
