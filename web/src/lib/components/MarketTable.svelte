<script lang="ts">
	import { marginLabel, pct, signed, spreadLabel } from '$lib/format';
	import { americanOdds, pickLabel, totalLabel } from '$lib/markets';
	import type { GameHeader, GameResult, Prediction, Side } from '$lib/types';

	// One row per market: the line, the model's number, its pick and, once
	// played, how the market finished.
	let {
		game,
		prediction,
		result = null
	}: { game: GameHeader; prediction: Prediction | null; result?: GameResult | null } = $props();

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
		const out = [
			{
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
					: null
			}
		];
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
					: null
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
					: null
			});
		}
		return out;
	});
	const played = $derived(result !== null);
</script>

<div class="scroll">
	<table class="markets small">
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
					<td class="tabular">{row.vegas}</td>
					<td class="tabular">{row.model}</td>
					<td class="tabular pick">{row.pick}</td>
					{#if played}<td class="tabular">{row.result}</td>{/if}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.scroll {
		overflow-x: auto;
	}
	.markets {
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
	.pick {
		color: var(--accent);
		font-weight: 600;
	}
</style>
