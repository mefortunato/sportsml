import { describe, expect, it } from 'vitest';
import { pickChallenge, revive, scoreAnswer, type ChallengeEntry, type ChallengeRef } from './api';
import type { Market } from './types';

const entry = (id: string, covered: 'home' | 'away' = 'home', total = false) =>
	({
		game: { game_id: id },
		answers: {
			spread: {
				game_id: id,
				market: 'spread',
				outcome: covered,
				odds: { home: -110, away: -110 },
				covered,
				spread: 3,
				model: { ats_pick: 'away', pick: 'away', correct: false, units: -1 }
			},
			...(total
				? {
						total: {
							game_id: id,
							market: 'total',
							outcome: 'under',
							odds: { over: -105, under: 120 },
							total_line: 44.5,
							model: { pick: 'under', correct: true, units: 1.2 }
						}
					}
				: {})
		}
	}) as unknown as ChallengeEntry;

describe('static api', () => {
	it('revives team references', () => {
		const text = JSON.stringify({
			teams: { KC: { team: 'KC', name: 'Kansas City Chiefs' } },
			data: {
				home: { $team: 'KC' },
				list: [{ opp: { $team: 'KC' } }, { $team: 'XX' }],
				n: 1
			}
		});
		const data = revive<Record<string, unknown>>(text);
		expect(data.home).toEqual({ team: 'KC', name: 'Kansas City Chiefs' });
		expect(data.list).toEqual([
			{ opp: { team: 'KC', name: 'Kansas City Chiefs' } },
			{ team: 'XX', name: 'XX' }
		]);
		expect(data.n).toBe(1);
	});

	// an index row for a pool entry
	const ref = (e: ChallengeEntry, shard = 0): ChallengeRef => [
		e.game.game_id,
		shard,
		Object.keys(e.answers) as Market[]
	];

	it('picks unseen games, then any once all are seen', () => {
		const pool = [entry('a'), entry('b'), entry('c')].map((e, i) => ref(e, i));
		for (let i = 0; i < 20; i++) {
			expect(pickChallenge(pool, ['a', 'b'], Math.random)).toEqual(['c', 2, ['spread']]);
		}
		expect(pickChallenge(pool, ['a', 'b', 'c'], () => 0.99)[0]).toBe('c');
		expect(() => pickChallenge([], [])).toThrow();
	});

	it('only picks games playable on the market', () => {
		const pool = [ref(entry('a')), ref(entry('b', 'home', true))];
		for (let i = 0; i < 10; i++) {
			expect(pickChallenge(pool, [], Math.random, 'total')[0]).toBe('b');
		}
		expect(() => pickChallenge(pool, [], Math.random, 'moneyline')).toThrow();
	});

	it('scores any pick like the server, in units at its odds', () => {
		expect(scoreAnswer(entry('a', 'home'), 'home')).toMatchObject({
			pick: 'home',
			correct: true
		});
		expect(scoreAnswer(entry('a', 'home'), 'home').units).toBeCloseTo(100 / 110);
		expect(scoreAnswer(entry('a', 'home'), 'away')).toMatchObject({
			pick: 'away',
			correct: false,
			units: -1
		});
		const total = scoreAnswer(entry('b', 'home', true), 'under', 'total');
		expect(total).toMatchObject({
			correct: true,
			units: 1.2,
			total_line: 44.5
		});
		expect(scoreAnswer(entry('b', 'home', true), 'over', 'total').units).toBe(-1);
		expect(() => scoreAnswer(entry('a'), 'over', 'total')).toThrow();
	});
});
