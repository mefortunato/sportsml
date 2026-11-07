import type { GameHeader, Team } from './types';

/** Lowercase, accents dropped, punctuation as spaces ("São Paulo" -> "sao paulo"). */
export function normalize(text: string): string {
	return text
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, ' ')
		.trim();
}

function names(team: Team): string[] {
	return [team.team, team.abbr, team.name, team.nickname]
		.filter((n): n is string => !!n)
		.map(normalize);
}

/** How well `query` names `team`, higher is better; null when it doesn't.
 * An exact key, abbreviation, name or nickname beats a name that starts with
 * the query, which beats every query word starting a word of the names,
 * which beats the query appearing anywhere in them. */
export function teamScore(team: Team, query: string): number | null {
	const q = normalize(query);
	if (!q) return 0;
	const all = names(team);
	if (all.includes(q)) return 4;
	if (all.some((n) => n.startsWith(q))) return 3;
	const words = all.flatMap((n) => n.split(' '));
	if (q.split(' ').every((w) => words.some((word) => word.startsWith(w)))) return 2;
	if (all.some((n) => n.includes(q))) return 1;
	return null;
}

/** Whether `query` names `team` (an empty query matches every team). */
export const matchesTeam = (team: Team, query: string) => teamScore(team, query) !== null;

/** Whether either side of a game matches `query`. */
export const matchesGame = (game: Pick<GameHeader, 'home' | 'away'>, query: string) =>
	matchesTeam(game.home, query) || matchesTeam(game.away, query);

/** The teams `query` names, best match first (ties keep their order). */
export function searchTeams(teams: Team[], query: string, limit = 8): Team[] {
	if (!normalize(query)) return [];
	return teams
		.map((team, i) => ({ team, i, score: teamScore(team, query) }))
		.filter((m): m is { team: Team; i: number; score: number } => m.score !== null)
		.sort((a, b) => b.score - a.score || a.i - b.i)
		.slice(0, limit)
		.map((m) => m.team);
}
