<script lang="ts">
	import CalibrationChart from '$lib/components/CalibrationChart.svelte';
	import { num, pct } from '$lib/format';
	import { links } from '$lib/links';
	import { MARKET_LABELS, unitsLabel } from '$lib/markets';
	import type { BetRow, Market, Metrics } from '$lib/types';

	let { data } = $props();
	const info = $derived(data.info);
	const perf = $derived(data.performance);
	const market = $derived(perf.overall.market);
	const model = $derived(perf.overall.model);
	const ats = $derived(perf.ats?.[0]);
	const first = $derived(perf.seasons[0]);
	const last = $derived(perf.seasons[perf.seasons.length - 1]);

	// win rate needed to break even betting at -110
	const BREAKEVEN = 110 / 210;
	const fixed = (v: number | null | undefined, digits = 3) =>
		v === null || v === undefined ? '—' : v.toFixed(digits);
	const record = (row: BetRow) => `${row.wins}-${row.losses}${row.pushes ? `-${row.pushes}` : ''}`;
	const roiClass = (row: BetRow) => (row.roi > 0 ? 'win' : '');

	// the betting section's markets: those the backtest scored
	const markets = $derived<Market[]>([
		...(perf.ats ? (['spread'] as const) : []),
		...(perf.moneyline ? (['moneyline'] as const) : []),
		...(perf.totals ? (['total'] as const) : [])
	]);
	let chosen = $state<Market>('spread');
	const market_ = $derived(markets.includes(chosen) ? chosen : (markets[0] ?? 'spread'));
	const betRows = $derived<BetRow[]>(
		market_ === 'moneyline'
			? (perf.moneyline ?? [])
			: market_ === 'total'
				? (perf.totals?.record ?? [])
				: (perf.ats ?? [])
	);
	const edgeLabel = (row: BetRow) =>
		market_ === 'moneyline' ? `${pct(row.min_edge)} pts` : `${row.min_edge} pts`;
	const overCalibration = $derived(
		perf.over_calibration
			? [
					{ label: 'Model', slot: 1, bins: perf.over_calibration.model },
					...(perf.over_calibration.market
						? [{ label: 'Vegas', slot: 2, bins: perf.over_calibration.market }]
						: [])
				]
			: []
	);
	const better = (a: number | undefined, b: number | undefined, lowerIsBetter = false) =>
		a !== undefined && b !== undefined && (lowerIsBetter ? a < b : a > b);

	const calibration = $derived([
		{ label: 'Model', slot: 1, bins: perf.calibration.model },
		...(perf.calibration.market ? [{ label: 'Vegas', slot: 2, bins: perf.calibration.market }] : [])
	]);
	const seasons = $derived(
		Object.entries(perf.by_season).sort(([a], [b]) => Number(b) - Number(a))
	);
	const phases = $derived(Object.entries(perf.by_phase));

	const tiles = $derived<{ label: string; key: keyof Metrics; lower?: boolean; format: (v?: number) => string }[]>([
		{ label: 'Picks the winner', key: 'accuracy', format: (v) => (v === undefined ? '—' : pct(v, 1)) },
		{ label: 'Brier score (lower is better)', key: 'brier', lower: true, format: (v) => fixed(v) },
		{ label: 'Margin error, RMSE (points)', key: 'rmse', lower: true, format: (v) => (v === undefined ? '—' : num(v, 1)) }
	]);
</script>

<div class="container section">
	<h1>Model performance</h1>
	<p class="muted intro">
		Every number here is from games the model had not seen. For each season from {first} to {last},
		a model trained only on earlier seasons predicted it one {info.date_label.toLowerCase()} at a time,
		with each {info.date_label.toLowerCase()}'s results added as they happened. These are the same
		predictions you play against in <a href={links.challenge(info.sport)}>Beat the model</a>.
		{#if market}Vegas is the closing line on the same {model.n} games.{/if}
	</p>

	<div class="tiles">
		{#each tiles as tile (tile.key)}
			{@const m = model[tile.key] as number | undefined}
			{@const v = market?.[tile.key] as number | undefined}
			<div class="card tile">
				<div class="muted small">{tile.label}</div>
				<div class="pair">
					<div>
						<div class="big" class:win={better(m, v, tile.lower)}>{tile.format(m)}</div>
						<div class="muted small">Model</div>
					</div>
					{#if market}
						<div>
							<div class="big" class:win={better(v, m, tile.lower)}>{tile.format(v)}</div>
							<div class="muted small">Vegas</div>
						</div>
					{/if}
				</div>
			</div>
		{/each}
		{#if perf.totals}
			{@const t = perf.totals}
			<div class="card tile">
				<div class="muted small">Total points error, RMSE</div>
				<div class="pair">
					<div>
						<div class="big" class:win={t.rmse.model < t.rmse.market}>{num(t.rmse.model, 1)}</div>
						<div class="muted small">Model</div>
					</div>
					<div>
						<div class="big" class:win={t.rmse.market < t.rmse.model}>{num(t.rmse.market, 1)}</div>
						<div class="muted small">Vegas line</div>
					</div>
				</div>
			</div>
		{/if}
		{#if ats}
			<div class="card tile">
				<div class="muted small">Against the spread (model's side every game)</div>
				<div class="pair">
					<div>
						<div class="big" class:win={(ats.win_pct ?? 0) > BREAKEVEN}>{ats.win_pct === null ? '—' : pct(ats.win_pct, 1)}</div>
						<div class="muted small">{record(ats)}</div>
					</div>
					<div>
						<div class="big muted">{pct(BREAKEVEN, 1)}</div>
						<div class="muted small">break-even at −110</div>
					</div>
				</div>
			</div>
		{/if}
	</div>

	<div class="card section">
		<h2>By season</h2>
		<div class="scroll">
			<table>
				<thead>
					<tr>
						<th>Season</th>
						<th class="num">Games</th>
						<th class="num">Accuracy</th>
						{#if market}<th class="num">Vegas</th>{/if}
						<th class="num">Brier</th>
						{#if market}<th class="num">Vegas</th>{/if}
						<th class="num">RMSE</th>
						{#if market}<th class="num">Vegas</th>{/if}
						{#if perf.ats_by_season}<th class="num">ATS</th>{/if}
						{#if perf.moneyline_by_season}<th class="num">Moneyline</th>{/if}
						{#if perf.totals_by_season}<th class="num">Over/under</th>{/if}
					</tr>
				</thead>
				<tbody>
					{#each seasons as [season, s] (season)}
						{@const row = perf.ats_by_season?.[season]}
						<tr>
							<td>{season}</td>
							<td class="num tabular">{s.model.n}</td>
							<td class="num tabular" class:win={better(s.model.accuracy, s.market?.accuracy)}>{pct(s.model.accuracy, 1)}</td>
							{#if s.market}<td class="num tabular muted">{pct(s.market.accuracy, 1)}</td>{/if}
							<td class="num tabular" class:win={better(s.model.brier, s.market?.brier, true)}>{fixed(s.model.brier)}</td>
							{#if s.market}<td class="num tabular muted">{fixed(s.market.brier)}</td>{/if}
							<td class="num tabular" class:win={better(s.model.rmse, s.market?.rmse, true)}>{num(s.model.rmse, 1)}</td>
							{#if s.market}<td class="num tabular muted">{num(s.market.rmse, 1)}</td>{/if}
							{#if row}
								<td class="num tabular">{record(row)} ({row.win_pct === null ? '—' : pct(row.win_pct, 1)})</td>
							{/if}
							{#if perf.moneyline_by_season}
								{@const ml = perf.moneyline_by_season[season]}
								<td class="num tabular" class:win={ml && ml.roi > 0}>
									{ml ? `${record(ml)} (${unitsLabel(ml.units ?? 0)})` : '—'}
								</td>
							{/if}
							{#if perf.totals_by_season}
								{@const ou = perf.totals_by_season[season]}
								<td class="num tabular" class:win={ou && ou.roi > 0}>
									{ou ? `${record(ou)} (${ou.win_pct === null ? '—' : pct(ou.win_pct, 1)})` : '—'}
								</td>
							{/if}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="muted small">Green marks where the model beat Vegas.</p>
	</div>

	<div class="grid-2 section">
		<div class="card">
			<h2>Calibration</h2>
			<p class="muted small">
				When the model gives a team a 70% chance, does that team win about 70% of the time? Points
				on the diagonal are perfectly calibrated.
			</p>
			<div class="legend small">
				{#each calibration as s (s.label)}
					<span><span class="swatch" style:background="var(--series-{s.slot})"></span> {s.label}</span>
				{/each}
			</div>
			<CalibrationChart series={calibration} />
			<details>
				<summary class="small">Table</summary>
				<table class="small">
					<thead>
						<tr><th>Source</th><th class="num">Predicted</th><th class="num">Won</th><th class="num">Games</th></tr>
					</thead>
					<tbody>
						{#each calibration as s (s.label)}
							{#each s.bins as b (b.predicted)}
								<tr>
									<td>{s.label}</td>
									<td class="num tabular">{pct(b.predicted)}</td>
									<td class="num tabular">{pct(b.actual)}</td>
									<td class="num tabular">{b.n}</td>
								</tr>
							{/each}
						{/each}
					</tbody>
				</table>
			</details>
		</div>

		<div class="stack">
			{#if markets.length}
				<div class="card">
					<h2>Betting the model's edge</h2>
					{#if markets.length > 1}
						<div class="tabs" role="tablist" aria-label="Market">
							{#each markets as m (m)}
								<button role="tab" aria-selected={market_ === m} class:active={market_ === m} onclick={() => (chosen = m)}
									>{MARKET_LABELS[m]}</button
								>
							{/each}
						</div>
					{/if}
					<p class="muted small">
						{#if market_ === 'moneyline'}
							Bet the team the model rates more likely to win than the market's odds imply (vig
							removed), when the gap is more than a few percentage points. Profit is at the posted
							moneyline: favorites pay less than a unit, underdogs more.
						{:else if market_ === 'total'}
							Bet the over when the model's total is above the line by more than a few points, the
							under when it is below. Profit is at the posted over/under odds.
						{:else}
							Take the model's side against the spread only when it disagrees with Vegas by more than
							a few points. Above {pct(BREAKEVEN, 1)} would make money at −110.
						{/if}
					</p>
					<div class="scroll">
					<table>
						<thead>
							<tr>
								<th>Edge over</th>
								<th class="num">Bets</th>
								<th class="num">W-L-P</th>
								<th class="num">Win %</th>
								<th class="num">95% range</th>
								<th class="num">Units</th>
								<th class="num">ROI</th>
							</tr>
						</thead>
						<tbody>
							{#each betRows as row (row.min_edge)}
								<tr>
									<td class="tabular">{edgeLabel(row)}</td>
									<td class="num tabular">{row.bets}</td>
									<td class="num tabular">{record(row)}</td>
									<td class="num tabular" class:win={market_ === 'spread' && (row.win_pct ?? 0) > BREAKEVEN}>{row.win_pct === null ? '—' : pct(row.win_pct, 1)}</td>
									<td class="num tabular muted">
										{row.ci95_low === null || row.ci95_high === null ? '—' : `${pct(row.ci95_low)}–${pct(row.ci95_high)}`}
									</td>
									<td class="num tabular">{row.units === undefined ? '—' : unitsLabel(row.units)}</td>
									<td class="num tabular {roiClass(row)}">{pct(row.roi, 1)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
					</div>
					{#if market_ === 'spread' && perf.edge_correlation}
						{@const c = perf.edge_correlation}
						<p class="muted small">
							Correlation between the model's edge and how the game finished against the spread:
							{c.r.toFixed(3)} (95% range {c.ci95_low.toFixed(3)} to {c.ci95_high.toFixed(3)}).
							{c.ci95_low > 0 ? 'Above zero: the model knows something the line does not.' : 'A range that includes zero means no reliable edge over the line.'}
						</p>
					{:else if market_ === 'total' && perf.totals}
						{@const t = perf.totals}
						<p class="muted small">
							On {t.n} games the model's total missed by {num(t.rmse.model, 1)} points (RMSE), the line
							by {num(t.rmse.market, 1)}.
							{#if t.brier.model !== undefined}
								Over/under Brier score: model {fixed(t.brier.model)}{t.brier.market !== undefined ? `, Vegas ${fixed(t.brier.market)}` : ''}.
							{/if}
							Correlation between the model's edge and how the total finished against the line:
							{t.edge_correlation.r.toFixed(3)} (95% range {t.edge_correlation.ci95_low.toFixed(3)} to
							{t.edge_correlation.ci95_high.toFixed(3)}).
						</p>
					{:else if market_ === 'moneyline' && market}
						<p class="muted small">
							The moneyline's win probabilities are the Vegas column of the Brier score and
							calibration above: the model beats the market's odds only where its probabilities are
							better.
						</p>
					{/if}
				</div>
			{/if}

			{#if overCalibration.length}
				<div class="card">
					<h2>Over/under calibration</h2>
					<p class="muted small">
						When the model gives the over a 60% chance, does the game go over about 60% of the time?
					</p>
					<div class="legend small">
						{#each overCalibration as s (s.label)}
							<span><span class="swatch" style:background="var(--series-{s.slot})"></span> {s.label}</span>
						{/each}
					</div>
					<CalibrationChart series={overCalibration} event="over" />
				</div>
			{/if}

			<div class="card">
				<h2>Early season vs. the rest</h2>
				<div class="scroll">
				<table>
					<thead>
						<tr>
							<th></th>
							<th class="num">Games</th>
							<th class="num">Accuracy</th>
							<th class="num">Brier</th>
							{#if market}<th class="num">Vegas Brier</th>{/if}
						</tr>
					</thead>
					<tbody>
						{#each phases as [phase, p] (phase)}
							<tr>
								<td>{phase.replace('dates', `${info.date_label.toLowerCase()}s`)}</td>
								<td class="num tabular">{p.model.n}</td>
								<td class="num tabular">{pct(p.model.accuracy, 1)}</td>
								<td class="num tabular">{fixed(p.model.brier)}</td>
								{#if p.market}<td class="num tabular muted">{fixed(p.market.brier)}</td>{/if}
							</tr>
						{/each}
					</tbody>
				</table>
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	.intro {
		max-width: 72ch;
	}
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 12px;
		margin-top: 16px;
	}
	.tile {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.pair {
		display: flex;
		gap: 24px;
	}
	.big {
		font-size: 1.5rem;
		font-weight: 700;
	}
	.win {
		color: var(--good);
	}
	.scroll {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
	}
	th {
		text-align: left;
		font-size: 0.8rem;
		color: var(--muted);
		font-weight: 600;
		padding: 6px 8px;
		border-bottom: 1px solid var(--border);
		white-space: nowrap;
	}
	td {
		padding: 5px 8px;
		border-bottom: 1px solid var(--border);
	}
	.num {
		text-align: right;
		white-space: nowrap;
	}
	.stack {
		display: flex;
		flex-direction: column;
		gap: 16px;
		min-width: 0;
	}
	.grid-2 > .card {
		min-width: 0;
	}
	.tabs {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin: 4px 0 8px;
	}
	.tabs button {
		padding: 4px 12px;
		border-radius: 999px;
	}
	.tabs button.active {
		border-color: var(--accent);
		background: var(--accent-soft);
		font-weight: 700;
	}
	.legend {
		display: flex;
		gap: 16px;
		margin-bottom: 4px;
	}
	.swatch {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 50%;
	}
	details {
		margin-top: 8px;
	}
	summary {
		cursor: pointer;
		color: var(--accent);
	}
</style>
