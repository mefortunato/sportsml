// The API for the static build (npm run build:artifact), which has no server:
// every answer is read from JSON written by `sportsml web export`, and the
// challenge's random pick and scoring run here, mirroring the server.
import type {
	ChallengeAnswer,
	ChallengeGame,
	GameDetail,
	Performance,
	Rankings,
	Side,
	SportInfo,
	Team,
	Upcoming
} from './types';

export interface ChallengeEntry {
	game: ChallengeGame;
	/** The answer to either pick, without the pick-dependent fields. */
	answer: Omit<ChallengeAnswer, 'pick' | 'correct'>;
}

interface Exported<T> {
	teams: Record<string, Team>;
	data: T;
}

/** Parse an exported file, replacing `{"$team": key}` with the team. */
export function revive<T>(text: string): T {
	const parsed = JSON.parse(text) as Exported<T>;
	const resolve = (value: unknown): unknown => {
		if (Array.isArray(value)) return value.map(resolve);
		if (value && typeof value === 'object') {
			const ref = (value as { $team?: string }).$team;
			if (ref !== undefined) return parsed.teams[ref] ?? { team: ref, name: ref };
			return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, resolve(v)]));
		}
		return value;
	};
	return resolve(parsed.data) as T;
}

/** A random pool game not in `exclude` (any game once all have been seen). */
export function pickChallenge(
	pool: ChallengeEntry[],
	exclude: string[] = [],
	random: () => number = Math.random
): ChallengeEntry {
	if (!pool.length) throw new Error('No historical games available');
	const seen = new Set(exclude);
	const fresh = pool.filter((entry) => !seen.has(entry.game.game_id));
	const choices = fresh.length ? fresh : pool;
	return choices[Math.floor(random() * choices.length)];
}

export function scoreAnswer(entry: ChallengeEntry, pick: Side): ChallengeAnswer {
	return { ...entry.answer, pick, correct: pick === entry.answer.covered };
}

const files = new Map<string, Promise<unknown>>();

function load<T>(path: string): Promise<T> {
	if (!files.has(path)) {
		const url = new URL(`data/${path}`, document.baseURI);
		const promise = fetch(url).then(async (response) => {
			if (!response.ok) throw new Error(`Could not load ${path} (${response.status})`);
			return path === 'sports.json' ? response.json() : revive<T>(await response.text());
		});
		promise.catch(() => files.delete(path));
		files.set(path, promise);
	}
	return files.get(path) as Promise<T>;
}

async function sport(name: string): Promise<SportInfo> {
	const info = (await load<SportInfo[]>('sports.json')).find((s) => s.sport === name);
	if (!info) throw new Error(`Unknown sport ${name}`);
	return info;
}

function pool(name: string): Promise<ChallengeEntry[]> {
	return load<ChallengeEntry[]>(`${name}/challenge.json`);
}

export const staticApi = {
	sports: () => load<SportInfo[]>('sports.json'),
	sport: (name: string) => sport(name),
	teams: async (name: string) => {
		const { default: week } = await load<{ default: Upcoming }>(`${name}/upcoming.json`);
		const teams = new Map<string, Team>();
		for (const g of week.games) for (const t of [g.home, g.away]) teams.set(t.team, t);
		return [...teams.values()];
	},
	upcoming: async (name: string, season?: number | null, date?: number | null) => {
		const file = await load<{ default: Upcoming; by_date: Record<string, Upcoming> }>(
			`${name}/upcoming.json`
		);
		if (season == null || date == null) return file.default;
		const week = file.by_date[`${season}-${date}`];
		if (!week) throw new Error(`No games for ${season} ${date}`);
		return week;
	},
	game: async (name: string, gameId: string) => {
		const game = (await load<Record<string, GameDetail>>(`${name}/games.json`))[gameId];
		if (!game) throw new Error(`Unknown game ${gameId}`);
		return game;
	},
	performance: (name: string) => load<Performance>(`${name}/performance.json`),
	rankings: (name: string) => load<Rankings>(`${name}/rankings.json`),
	challengeNext: async (name: string, exclude: string[] = []) =>
		pickChallenge(await pool(name), exclude).game,
	challengeAnswer: async (name: string, gameId: string, pick: Side) => {
		const entry = (await pool(name)).find((e) => e.game.game_id === gameId);
		if (!entry) throw new Error(`Unknown game ${gameId}`);
		return scoreAnswer(entry, pick);
	}
};
