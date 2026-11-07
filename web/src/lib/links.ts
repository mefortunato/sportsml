import { resolve } from '$app/paths';
import type { SportInfo } from './types';

// Internal links go through resolve(), which also prefixes `#` in the
// hash-routed static build (npm run build:artifact).
export const links = {
	home: () => resolve('/'),
	upcoming: (sport: string, season?: number | null, date?: number | null) =>
		resolve('/[sport]/[[season=int]]/[[date]]', {
			sport,
			season: season == null ? undefined : String(season),
			date: season == null || date == null ? undefined : String(date)
		}),
	recent: (sport: string, season?: number | null, date?: number | null) =>
		resolve('/[sport]/recent/[[season=int]]/[[date=int]]', {
			sport,
			season: season == null ? undefined : String(season),
			date: season == null || date == null ? undefined : String(date)
		}),
	game: (sport: string, gameId: string) => resolve('/[sport]/games/[gameId]', { sport, gameId }),
	challenge: (sport: string) => resolve('/[sport]/challenge', { sport }),
	rankings: (sport: string) => resolve('/[sport]/rankings', { sport }),
	teamMap: (sport: string) => resolve('/[sport]/map', { sport }),
	performance: (sport: string) => resolve('/[sport]/performance', { sport })
};

export type PageKey = 'upcoming' | 'recent' | 'rankings' | 'map' | 'performance' | 'challenge';

export interface SportPage {
	key: PageKey;
	label: string;
	href: string;
}

/** A sport's pages, in menu order (only those its export has data for). */
export function sportPages(info: SportInfo): SportPage[] {
	const s = info.sport;
	return [
		{ key: 'upcoming' as const, label: 'Upcoming', href: links.upcoming(s) },
		{ key: 'recent' as const, label: 'Recent', href: links.recent(s) },
		{ key: 'rankings' as const, label: 'Rankings', href: links.rankings(s) },
		...(info.has_team_map ? [{ key: 'map' as const, label: 'Team map', href: links.teamMap(s) }] : []),
		...(info.challenge_games
			? [{ key: 'performance' as const, label: 'Performance', href: links.performance(s) }]
			: []),
		...(info.challenge_games && (info.has_spread || info.markets?.length)
			? [{ key: 'challenge' as const, label: 'Beat the model', href: links.challenge(s) }]
			: [])
	];
}
