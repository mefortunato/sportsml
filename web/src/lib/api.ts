// The site's data: JSON files written by `sportsml web export` next to the
// built site (there is no server). The challenge's random pick and scoring
// run here.
import { base } from '$app/paths';
import { units } from './markets';
import type {
	ChallengeAnswer,
	ChallengeGame,
	GameDetail,
	Market,
	MarketAnswer,
	OddsFile,
	Performance,
	Pick,
	Rankings,
	SportInfo,
	Team,
	Upcoming
} from './types';

export interface ChallengeEntry {
	game: ChallengeGame;
	/** Each playable market's answer, without the pick-dependent fields. */
	answers: Partial<Record<Market, MarketAnswer>>;
}

/** One pool game in `challenge/index.json`: its id, the shard file
 * (`challenge/<shard>.json`) that holds it and the markets it is playable on. */
export type ChallengeRef = [gameId: string, shard: number, markets: Market[]];

export interface ChallengeIndex {
	shard_size: number;
	games: ChallengeRef[];
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

/** A random pool game playable on `market`, not in `exclude` (any such
 * game once all have been seen). */
export function pickChallenge(
	pool: ChallengeRef[],
	exclude: string[] = [],
	random: () => number = Math.random,
	market: Market = 'spread'
): ChallengeRef {
	const playable = pool.filter(([, , markets]) => markets.includes(market));
	if (!playable.length) throw new Error('No historical games available');
	const seen = new Set(exclude);
	const fresh = playable.filter(([gameId]) => !seen.has(gameId));
	const choices = fresh.length ? fresh : playable;
	return choices[Math.floor(random() * choices.length)];
}

/** Score `pick` on `market` (like the snapshot's challenge_answer). */
export function scoreAnswer(
	entry: ChallengeEntry,
	pick: Pick,
	market: Market = 'spread'
): ChallengeAnswer {
	const answer = entry.answers[market];
	if (!answer) throw new Error(`Game ${entry.game.game_id} has no ${market} market`);
	const correct = pick === answer.outcome;
	const odds = answer.odds[pick];
	if (odds === undefined) throw new Error(`No odds for ${pick}`);
	return { ...answer, pick, correct, units: units(odds, correct) };
}

const files = new Map<string, Promise<unknown>>();

function load<T>(path: string): Promise<T> {
	if (!files.has(path)) {
		// the artifact build (hash routing) resolves against its own page; the
		// site build fetches from its base path, whatever route is showing
		const url =
			import.meta.env.VITE_SPORTSML_TARGET === 'artifact'
				? new URL(`data/${path}`, document.baseURI)
				: `${base}/data/${path}`;
		const promise = fetch(url).then(async (response) => {
			if (!response.ok) throw new Error(`Could not load ${path} (${response.status})`);
			// files without team objects are plain JSON
			const plain = path === 'sports.json' || path.endsWith('odds.json');
			return plain ? response.json() : revive<T>(await response.text());
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

// The pool is an index of every game plus shards of full games, so a pick
// fetches one shard of 100 games (~0.5 MB) rather than the whole pool (tens of MB).
function challengeIndex(name: string): Promise<ChallengeIndex> {
	return load<ChallengeIndex>(`${name}/challenge/index.json`);
}

async function challengeEntry(name: string, [gameId, shard]: ChallengeRef) {
	const entries = await load<ChallengeEntry[]>(`${name}/challenge/${shard}.json`);
	const entry = entries.find((e) => e.game.game_id === gameId);
	if (!entry) throw new Error(`Unknown game ${gameId}`);
	return entry;
}

export const api = {
	sports: () => load<SportInfo[]>('sports.json'),
	sport: (name: string) => sport(name),
	teams: async (name: string) => {
		const { default: week } = await load<{ default: Upcoming }>(`${name}/upcoming.json`);
		const teams = new Map<string, Team>();
		for (const g of week.games) for (const t of [g.home, g.away]) teams.set(t.team, t);
		return [...teams.values()];
	},
	upcoming: async (name: string, season?: number | null, date?: number | null) => {
		const file = await load<{
			default: Upcoming;
			by_date: Record<string, Upcoming>;
		}>(`${name}/upcoming.json`);
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
	/** Current sportsbook lines; null when the site was built without them. */
	odds: (name: string) => load<OddsFile>(`${name}/odds.json`).catch(() => null),
	rankings: (name: string) => load<Rankings>(`${name}/rankings.json`),
	challengeNext: async (name: string, exclude: string[] = [], market: Market = 'spread') => {
		const ref = pickChallenge((await challengeIndex(name)).games, exclude, Math.random, market);
		return (await challengeEntry(name, ref)).game;
	},
	challengeAnswer: async (name: string, gameId: string, pick: Pick, market: Market = 'spread') => {
		const ref = (await challengeIndex(name)).games.find(([id]) => id === gameId);
		if (!ref) throw new Error(`Unknown game ${gameId}`);
		return scoreAnswer(await challengeEntry(name, ref), pick, market);
	}
};
