import { describe, expect, it } from 'vitest';
import { grade, marketWinner, recentDay, sortPlayed, summarize } from './recent';
import type { GameResult, PlayedGame, Prediction, RecentFile } from './types';

const team = (key: string) => ({ team: key, name: key });
function played(
	id: string,
	prediction: Partial<Prediction>,
	result: Partial<GameResult>,
	lines: Partial<PlayedGame> = {}
): PlayedGame {
	return {
		game_id: id,
		season: 2026,
		date: 9,
		kickoff: null,
		home: team('H'),
		away: team('A'),
		neutral: false,
		spread: 3,
		moneyline: { home: -150, away: 130 },
		total_line: 44.5,
		total_odds: null,
		prediction_source: 'replay',
		prediction: {
			margin: 5,
			win_prob: 0.65,
			edge: 2,
			ats_pick: 'home',
			market_prob: 0.58,
			ml_edge: 0.07,
			ml_pick: 'home',
			total: 47,
			total_edge: 2.5,
			ou_pick: 'over',
			...prediction
		},
		result: {
			home_score: 24,
			away_score: 17,
			margin: 7,
			covered: 'home',
			winner: 'home',
			total: 41,
			went: 'under',
			...result
		},
		...lines
	};
}

describe('grading a played game', () => {
	const game = played('a', {}, {});
	it('scores each market at its odds', () => {
		expect(grade(game, 'winner')).toMatchObject({ pick: 'home', hit: true });
		expect(grade(game, 'spread')).toMatchObject({ hit: true, units: 100 / 110 });
		expect(grade(game, 'moneyline')).toMatchObject({ hit: true, units: 100 / 150 });
		expect(grade(game, 'total')).toMatchObject({ pick: 'over', hit: false, units: -1 });
	});

	it('does not count pushes, ties or games without the line', () => {
		expect(grade(played('p', {}, { covered: 'push' }), 'spread').hit).toBeNull();
		expect(grade(played('t', {}, { winner: 'push' }), 'winner').hit).toBeNull();
		expect(grade(played('n', {}, {}, { spread: null }), 'spread').hit).toBeNull();
		expect(grade(played('m', {}, {}, { moneyline: null }), 'moneyline').hit).toBeNull();
	});

	it("takes the market's favorite from the moneyline, else the spread", () => {
		expect(marketWinner(played('a', { market_prob: 0.4 }, {}))).toBe('away');
		expect(marketWinner(played('b', { market_prob: null }, {}, { spread: -2 }))).toBe('away');
		expect(marketWinner(played('c', { market_prob: null }, {}, { spread: 0 }))).toBeNull();
	});
});

describe('recent summary', () => {
	const games = [
		played('a', {}, {}),
		// the model picks the road underdog, which wins outright
		played(
			'b',
			{ margin: -1, win_prob: 0.45, edge: -4, ats_pick: 'away', ml_edge: -0.13, ml_pick: 'away' },
			{ home_score: 10, away_score: 13, margin: -3, covered: 'away', winner: 'away', total: 23 }
		)
	];
	const s = summarize(games);

	it("tallies the model's records and units next to Vegas", () => {
		expect(s.games).toBe(2);
		expect(s.winners.model).toMatchObject({ wins: 2, losses: 0 });
		expect(s.winners.market).toMatchObject({ wins: 1, losses: 1 });
		expect(s.spread).toMatchObject({ wins: 2, losses: 0, pushes: 0 });
		expect(s.moneyline?.units).toBeCloseTo(100 / 150 + 1.3);
		expect(s.total).toMatchObject({ wins: 0, losses: 2 });
	});

	it('compares the misses and Brier scores', () => {
		expect(s.margin).toEqual({ n: 2, model: (2 + 2) / 2, market: (4 + 6) / 2 });
		expect(s.points?.model).toBeCloseTo((6 + 24) / 2);
		expect(s.brier?.model).toBeCloseTo((0.35 ** 2 + 0.45 ** 2) / 2);
		expect(s.brier?.market).toBeCloseTo((0.42 ** 2 + 0.58 ** 2) / 2);
	});

	it('handles no games', () => {
		const empty = summarize([]);
		expect(empty.spread).toBeNull();
		expect(empty.margin).toBeNull();
		expect(empty.winners.model.wins).toBe(0);
	});

	it('sorts by the model miss or the spread edge', () => {
		expect(sortPlayed(games, 'miss').map((g) => g.game_id)).toEqual(['a', 'b']);
		expect(sortPlayed(games, 'edge').map((g) => g.game_id)).toEqual(['b', 'a']);
		expect(sortPlayed(games, 'kickoff')).toBe(games);
	});
});

describe('recentDay', () => {
	const file: RecentFile = {
		dates: [
			{ season: 2026, date: 9, name: null },
			{ season: 2026, date: 8, name: null }
		],
		by_date: { '2026-9': [played('a', {}, {})], '2026-8': [played('b', {}, {}, { date: 8 })] }
	};

	it('shows the newest date by default, with every recent game for the totals', () => {
		const day = recentDay(file);
		expect([day.season, day.date]).toEqual([2026, 9]);
		expect(day.games.map((g) => g.game_id)).toEqual(['a']);
		expect(day.all.map((g) => g.game_id)).toEqual(['a', 'b']);
	});

	it('picks a date and rejects unknown ones', () => {
		expect(recentDay(file, 2026, 8).games[0].game_id).toBe('b');
		expect(() => recentDay(file, 2026, 3)).toThrow();
	});

	it('is empty without the file (older exports)', () => {
		expect(recentDay(null)).toMatchObject({ date: null, games: [], all: [] });
	});
});
