import type { UpcomingGame } from './types';

/** How the upcoming games are ordered: by kickoff, or biggest edge first. */
export type GameSort = 'kickoff' | 'spread' | 'moneyline' | 'total';

export const SORT_LABELS: Record<GameSort, string> = {
	kickoff: 'Kickoff',
	spread: 'Spread edge',
	moneyline: 'Moneyline edge',
	total: 'Over/under edge'
};

/** The model's disagreement with the market on `sort`'s market, or null
 * where the game has no line (or the model no prediction) for it. */
export function edgeOf(game: UpcomingGame, sort: GameSort): number | null {
	const p = game.prediction;
	const value =
		sort === 'spread'
			? p.edge
			: sort === 'moneyline'
				? p.ml_edge
				: sort === 'total'
					? p.total_edge
					: null;
	return value === null || value === undefined || !Number.isFinite(value) ? null : value;
}

/** The orders worth offering: kickoff, and each market some game has an edge on. */
export function sortOptions(games: UpcomingGame[]): GameSort[] {
	const markets: GameSort[] = ['spread', 'moneyline', 'total'];
	return ['kickoff', ...markets.filter((m) => games.some((g) => edgeOf(g, m) !== null))];
}

/** `games` biggest absolute edge first on `sort`'s market; games without
 * that line follow in kickoff order. Kickoff keeps the given order. */
export function sortGames(games: UpcomingGame[], sort: GameSort): UpcomingGame[] {
	if (sort === 'kickoff') return games;
	const size = (g: UpcomingGame) => {
		const edge = edgeOf(g, sort);
		return edge === null ? -1 : Math.abs(edge);
	};
	// Array.prototype.sort is stable: equal edges keep kickoff order
	return [...games].sort((a, b) => size(b) - size(a));
}
