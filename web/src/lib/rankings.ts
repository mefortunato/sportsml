import type { RankingSeason, Team } from './types';

/** Highlighted teams: team key -> series slot (1-3). The slot stays with the
 * team while it is highlighted, so its color never changes under it. */
export type Pins = Record<string, number>;

export const MAX_PINS = 3;

export interface RankRow {
	team: Team;
	rating: number;
	rank: number;
	/** Places gained since the previous date (null on the first date). */
	change: number | null;
}

function ranked(season: RankingSeason, index: number): RankRow[] {
	return season.teams
		.filter((t) => t.ratings[index] !== null && t.ratings[index] !== undefined)
		.map((t) => ({ team: t.team, rating: t.ratings[index] as number, rank: 0, change: null }))
		.sort((a, b) => b.rating - a.rating)
		.map((row, i) => ({ ...row, rank: i + 1 }));
}

/** Teams ordered by rating at `index`, with the change in rank since index - 1. */
export function rankAt(season: RankingSeason, index: number): RankRow[] {
	const rows = ranked(season, index);
	if (index === 0) return rows;
	const before = new Map(ranked(season, index - 1).map((r) => [r.team.team, r.rank]));
	return rows.map((row) => {
		const previous = before.get(row.team.team);
		return { ...row, change: previous === undefined ? null : previous - row.rank };
	});
}

/** The top teams at the season's latest date. */
export function defaultPins(season: RankingSeason, count = MAX_PINS): Pins {
	const top = rankAt(season, season.dates.length - 1).slice(0, count);
	return Object.fromEntries(top.map((row, i) => [row.team.team, i + 1]));
}

/** Highlight or un-highlight `team`. A new team takes the lowest free slot;
 * with every slot taken it replaces the team in the highest slot. */
export function togglePin(pins: Pins, team: string): Pins {
	if (team in pins) {
		const { [team]: _, ...rest } = pins;
		return rest;
	}
	const used = new Set(Object.values(pins));
	for (let slot = 1; slot <= MAX_PINS; slot++) {
		if (!used.has(slot)) return { ...pins, [team]: slot };
	}
	const [replaced] = Object.entries(pins).find(([, slot]) => slot === MAX_PINS) ?? [];
	const { [replaced as string]: _, ...rest } = pins;
	return { ...rest, [team]: MAX_PINS };
}

/** Symmetric y extent around zero, rounded up to a tick step. */
export function yExtent(season: RankingSeason): { max: number; step: number } {
	let largest = 0;
	for (const t of season.teams)
		for (const v of t.ratings) if (v !== null) largest = Math.max(largest, Math.abs(v));
	const step = largest > 12 ? 5 : largest > 5 ? 2.5 : 1;
	return { max: Math.max(step, Math.ceil(largest / step) * step), step };
}
