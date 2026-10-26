import type {
	ChallengeAnswer,
	ChallengeGame,
	GameDetail,
	Side,
	SportInfo,
	Team,
	Upcoming
} from './types';
import { staticApi } from './static-api';

type Fetch = typeof fetch;

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

async function request<T>(fetcher: Fetch, path: string, init?: RequestInit): Promise<T> {
	const response = await fetcher(`/api${path}`, init);
	if (!response.ok) {
		let detail = response.statusText;
		try {
			detail = (await response.json()).detail ?? detail;
		} catch {
			// not JSON
		}
		throw new ApiError(response.status, String(detail));
	}
	return response.json() as Promise<T>;
}

function query(params: Record<string, string | number | null | undefined | string[]>) {
	const search = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value === null || value === undefined) continue;
		for (const item of Array.isArray(value) ? value : [value]) search.append(key, String(item));
	}
	const text = search.toString();
	return text ? `?${text}` : '';
}

const httpApi = {
	sports: (f: Fetch = fetch) => request<SportInfo[]>(f, '/sports'),
	sport: (sport: string, f: Fetch = fetch) => request<SportInfo>(f, `/${sport}`),
	teams: (sport: string, f: Fetch = fetch) => request<Team[]>(f, `/${sport}/teams`),
	upcoming: (sport: string, season?: number | null, date?: number | null, f: Fetch = fetch) =>
		request<Upcoming>(f, `/${sport}/upcoming${query({ season, date })}`),
	game: (sport: string, gameId: string, f: Fetch = fetch) =>
		request<GameDetail>(f, `/${sport}/games/${encodeURIComponent(gameId)}`),
	challengeNext: (sport: string, exclude: string[] = [], f: Fetch = fetch) =>
		request<ChallengeGame>(f, `/${sport}/challenge/next${query({ exclude })}`),
	challengeAnswer: (sport: string, gameId: string, pick: Side, f: Fetch = fetch) =>
		request<ChallengeAnswer>(f, `/${sport}/challenge/${encodeURIComponent(gameId)}`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ pick })
		})
};

// `npm run build:artifact` sets VITE_SPORTSML_DATA=static: no server, data from
// exported JSON. The constant is replaced at build time, so each build keeps one.
export const api: typeof httpApi =
	import.meta.env.VITE_SPORTSML_DATA === 'static' ? staticApi : httpApi;
