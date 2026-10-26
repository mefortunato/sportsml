import { resolve } from '$app/paths';

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
	game: (sport: string, gameId: string) => resolve('/[sport]/games/[gameId]', { sport, gameId }),
	challenge: (sport: string) => resolve('/[sport]/challenge', { sport })
};
