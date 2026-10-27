<script lang="ts">
	import { handicap, num, spreadLabel } from '$lib/format';
	import { americanOdds } from '$lib/markets';
	import { age } from '$lib/odds';
	import type { BookOffer, GameOdds, Team } from '$lib/types';

	// Every book's line, the best price on each side highlighted, and how
	// the consensus moved since the line was first seen.
	let { home, away, odds }: { home: Team; away: Team; odds: GameOdds } = $props();

	const isBest = (offer: BookOffer | null, book: string, odds: number | null, points?: number | null) =>
		!!offer && offer.book === book && offer.odds === odds && (points == null || offer.points === points);

	// the consensus spread over time, as a small line chart (home margin up)
	const W = 220;
	const H = 44;
	const points = $derived(
		odds.history.filter((p) => p.spread !== null && p.spread !== undefined) as {
			t: string;
			spread: number;
		}[]
	);
	const path = $derived.by(() => {
		if (points.length < 2) return '';
		const times = points.map((p) => new Date(p.t).getTime());
		const lo = Math.min(...points.map((p) => p.spread)) - 0.5;
		const hi = Math.max(...points.map((p) => p.spread)) + 0.5;
		const t0 = times[0];
		const t1 = times[times.length - 1] || t0 + 1;
		return points
			.map((p, i) => {
				const x = 4 + ((times[i] - t0) / Math.max(1, t1 - t0)) * (W - 8);
				const y = 4 + ((hi - p.spread) / (hi - lo)) * (H - 8);
				return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join('');
	});
	const c = $derived(odds.consensus);
</script>

<div class="card books">
	<div class="head">
		<h2>Sportsbooks</h2>
		<span class="muted small">updated {age(odds.updated)}</span>
	</div>

	<div class="scroll">
		<table class="small">
			<thead>
				<tr>
					<th>Book</th>
					<th class="num">{away.team}</th>
					<th class="num">{home.team}</th>
					<th class="num">{away.team} ML</th>
					<th class="num">{home.team} ML</th>
					<th class="num">Over</th>
					<th class="num">Under</th>
				</tr>
			</thead>
			<tbody>
				{#each odds.books as b (b.book)}
					<tr>
						<td>{b.book}</td>
						<td class="num tabular" class:best={isBest(odds.best.spread.away, b.book, b.spread_away_odds, b.spread)}>
							{b.spread === null ? '—' : `${handicap(b.spread, 'away')} ${b.spread_away_odds === null ? '' : americanOdds(b.spread_away_odds)}`}
						</td>
						<td class="num tabular" class:best={isBest(odds.best.spread.home, b.book, b.spread_home_odds, b.spread)}>
							{b.spread === null ? '—' : `${handicap(b.spread, 'home')} ${b.spread_home_odds === null ? '' : americanOdds(b.spread_home_odds)}`}
						</td>
						<td class="num tabular" class:best={isBest(odds.best.moneyline.away, b.book, b.ml_away)}>{americanOdds(b.ml_away)}</td>
						<td class="num tabular" class:best={isBest(odds.best.moneyline.home, b.book, b.ml_home)}>{americanOdds(b.ml_home)}</td>
						<td class="num tabular" class:best={isBest(odds.best.total.over, b.book, b.over_odds, b.total)}>
							{b.total === null ? '—' : `${num(b.total)} ${b.over_odds === null ? '' : americanOdds(b.over_odds)}`}
						</td>
						<td class="num tabular" class:best={isBest(odds.best.total.under, b.book, b.under_odds, b.total)}>
							{b.total === null ? '—' : `${num(b.total)} ${b.under_odds === null ? '' : americanOdds(b.under_odds)}`}
						</td>
					</tr>
				{/each}
				<tr class="consensus">
					<td>Consensus</td>
					<td class="num tabular">{c.spread === null ? '—' : handicap(c.spread, 'away')}</td>
					<td class="num tabular">{c.spread === null ? '—' : handicap(c.spread, 'home')}</td>
					<td class="num tabular">{americanOdds(c.ml_away)}</td>
					<td class="num tabular">{americanOdds(c.ml_home)}</td>
					<td class="num tabular" colspan="2">{c.total === null ? '—' : num(c.total)}</td>
				</tr>
			</tbody>
		</table>
	</div>
	<p class="muted small note">Highlighted: the best price on each side. Spreads without a price are −110.</p>

	<div class="movement small">
		<div>
			<span class="muted">Spread</span>
			{spreadLabel(home, away, odds.open.spread)} → <strong>{spreadLabel(home, away, c.spread)}</strong>
		</div>
		<div>
			<span class="muted">Total</span>
			{odds.open.total === null ? '—' : num(odds.open.total)} → <strong>{c.total === null ? '—' : num(c.total)}</strong>
		</div>
		{#if path}
			<svg viewBox="0 0 {W} {H}" width={W} height={H} role="img" aria-label="Consensus spread over time">
				<path d={path} class="trend" />
			</svg>
		{/if}
	</div>
</div>

<style>
	.books {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	h2 {
		margin: 0;
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
		white-space: nowrap;
		border-bottom: 1px solid var(--border);
		text-align: left;
	}
	thead th {
		color: var(--muted);
		font-weight: 600;
		font-size: 0.75rem;
	}
	.num {
		text-align: right;
	}
	td.best {
		background: var(--good-soft);
		font-weight: 700;
	}
	tr.consensus td {
		font-weight: 600;
		border-bottom: none;
	}
	.note {
		margin: 0;
	}
	.movement {
		display: flex;
		gap: 16px;
		align-items: center;
		flex-wrap: wrap;
	}
	.trend {
		fill: none;
		stroke: var(--accent);
		stroke-width: 2;
	}
</style>
