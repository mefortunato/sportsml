<script lang="ts">
	import { marginLabel, pct, signed, spreadLabel } from '$lib/format';
	import { americanOdds, pickLabel, totalLabel } from '$lib/markets';
	import type { GameHeader, GameResult, Prediction, Side } from '$lib/types';

	// One row per market: the line, the model's number, its pick and, once
	// played, how the market finished. Sports without a point spread (hockey,
	// baseball) have no spread row.
	let {
		game,
		prediction,
		result = null,
		hasSpread = true
	}: {
		game: GameHeader;
		prediction: Prediction | null;
		result?: GameResult | null;
		hasSpread?: boolean;
	} = $props();

	interface Row {
		market: string;
		vegas: string;
		model: string;
		pick: string;
		result: string | null;
		/** Whether the model's pick won, once played (null: no pick, or a push). */
		hit: boolean | null;
	}

	const graded = (pick: string | null | undefined, outcome: string | null | undefined) =>
		!result || !pick || !outcome || outcome === 'push' ? null : pick === outcome;

	const team = (side: Side) => (side === 'home' ? game.home : game.away);
	// the moneyline favorite by the market (home on a pick'em)
	const favorite = $derived<Side>(
		prediction?.market_prob != null && prediction.market_prob < 0.5 ? 'away' : 'home'
	);
	const prob = (p: number | null | undefined, side: Side) =>
		p === null || p === undefined ? null : side === 'home' ? p : 1 - p;

	const rows = $derived.by(() => {
		const p = prediction;
		const ml = game.moneyline;
		const fav = favorite;
		const vegasFav = prob(p?.market_prob, fav);
		const modelFav = prob(p?.win_prob, fav);
		const out: Row[] = [];
		if (hasSpread) {
			out.push({
				market: 'Spread',
				vegas: spreadLabel(game.home, game.away, game.spread),
				model: p ? marginLabel(game.home, game.away, p.margin) : '—',
				pick:
					p?.ats_pick && p.edge !== null
						? `${pickLabel(p.ats_pick, game.home, game.away)} (${signed(Math.abs(p.edge))})`
						: '—',
				result: result
					? result.covered === 'push'
						? 'Push'
						: result.covered
							? `${team(result.covered).team} covered`
							: '—'
					: null,
				hit: graded(p?.ats_pick, result?.covered)
			});
		}
		if (ml) {
			out.push({
				market: 'Moneyline',
				vegas: `${team(fav).team} ${americanOdds(ml[fav])}${vegasFav === null ? '' : ` (${pct(vegasFav)})`}`,
				model: modelFav === null ? '—' : `${team(fav).team} ${pct(modelFav)}`,
				pick:
					p?.ml_pick && p.ml_edge != null
						? `${pickLabel(p.ml_pick, game.home, game.away)} ${americanOdds(ml[p.ml_pick])} (+${pct(Math.abs(p.ml_edge), 1)})`
						: '—',
				result: result
					? result.winner === 'push'
						? 'Tie'
						: result.winner
							? `${team(result.winner).team} won`
							: '—'
					: null,
				hit: graded(p?.ml_pick, result?.winner)
			});
		}
		if (game.total_line != null || p?.total != null) {
			out.push({
				market: 'Over/under',
				vegas: totalLabel(game.total_line),
				model: p?.total == null ? '—' : p.total.toFixed(1),
				pick:
					p?.ou_pick && p.total_edge != null
						? `${pickLabel(p.ou_pick, game.home, game.away)} (${signed(p.total_edge)})`
						: '—',
				result: result
					? result.total == null
						? '—'
						: `${result.total}${result.went ? ` · ${result.went === 'push' ? 'push' : result.went}` : ''}`
					: null,
				hit: graded(p?.ou_pick, game.total_line == null ? null : result?.went)
			});
		}
		return out;
	});
	const played = $derived(result !== null);

	// Cells wrap at spaces on narrow cards; the pick's last word stays glued
	// to its ✓/✗ so the mark never lands on a line of its own.
	const lead = (s: string) => s.slice(0, s.lastIndexOf(' ') + 1);
	const last = (s: string) => s.slice(s.lastIndexOf(' ') + 1);
</script>

<div class="scroll">
	<table class="markets small" class:played>
		<thead>
			<tr>
				<th></th>
				<th>Vegas</th>
				<th>Model</th>
				<th>Model pick</th>
				{#if played}<th>Result</th>{/if}
			</tr>
		</thead>
		<tbody>
			{#each rows as row (row.market)}
				<tr>
					<th scope="row">{row.market}</th>
					<td class="tabular" data-label="Vegas">{row.vegas}</td>
					<td class="tabular" data-label="Model">{row.model}</td>
					<td class="tabular pick" data-label="Model pick">
						{lead(row.pick)}<span class="nowrap"
							>{last(row.pick)}{#if row.hit !== null}<span
									class="mark"
									class:hit={row.hit}
									class:miss={!row.hit}
									>{row.hit ? '✓' : '✗'}<span class="sr">{row.hit ? ' won' : ' lost'}</span></span
								>{/if}</span
						>
					</td>
					{#if played}<td class="tabular" data-label="Result">{row.result}</td>{/if}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.scroll {
		overflow-x: auto;
		container-type: inline-size;
	}
	.markets {
		width: 100%;
		border-collapse: collapse;
	}
	th,
	td {
		padding: 4px 6px;
		text-align: left;
		vertical-align: top;
		border-bottom: 1px solid var(--border);
	}
	/* the market names and headers stay on one line; values wrap if the card is narrow */
	th {
		white-space: nowrap;
	}
	.nowrap {
		white-space: nowrap;
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
	.pick {
		color: var(--accent);
		font-weight: 600;
	}
	.mark {
		position: relative;
		margin-left: 4px;
		font-weight: 700;
	}
	.mark.hit {
		color: var(--good);
	}
	.mark.miss {
		color: var(--bad);
	}
	/* too narrow for the columns (phones): each market becomes a small block
	   of labelled values, Vegas / Model / Pick (/ Result) side by side */
	@container (max-width: 400px) {
		thead {
			display: none;
		}
		tbody tr {
			display: grid;
			grid-template-columns: repeat(3, minmax(0, 1fr));
			column-gap: 8px;
			padding: 6px 0;
			border-bottom: 1px solid var(--border);
		}
		.played tbody tr {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		tbody tr:last-child {
			border-bottom: none;
		}
		tbody th {
			grid-column: 1 / -1;
			color: var(--text);
		}
		tbody th,
		tbody td {
			border-bottom: none;
			padding: 2px 0;
		}
		td::before {
			content: attr(data-label);
			display: block;
			color: var(--muted);
			font-weight: 600;
			font-size: 0.75rem;
		}
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
</style>
