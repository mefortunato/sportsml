import { describe, expect, it } from 'vitest';
import { pickChallenge, revive, scoreAnswer, type ChallengeEntry } from './api';

const entry = (id: string, covered: 'home' | 'away' | null = 'home') =>
	({
		game: { game_id: id },
		answer: { game_id: id, covered, spread: 3, model: { ats_pick: 'away', correct: false } }
	}) as unknown as ChallengeEntry;

describe('static api', () => {
	it('revives team references', () => {
		const text = JSON.stringify({
			teams: { KC: { team: 'KC', name: 'Kansas City Chiefs' } },
			data: { home: { $team: 'KC' }, list: [{ opp: { $team: 'KC' } }, { $team: 'XX' }], n: 1 }
		});
		const data = revive<Record<string, unknown>>(text);
		expect(data.home).toEqual({ team: 'KC', name: 'Kansas City Chiefs' });
		expect(data.list).toEqual([
			{ opp: { team: 'KC', name: 'Kansas City Chiefs' } },
			{ team: 'XX', name: 'XX' }
		]);
		expect(data.n).toBe(1);
	});

	it('picks unseen games, then any once all are seen', () => {
		const pool = [entry('a'), entry('b'), entry('c')];
		for (let i = 0; i < 20; i++) {
			expect(pickChallenge(pool, ['a', 'b'], Math.random).game.game_id).toBe('c');
		}
		expect(pickChallenge(pool, ['a', 'b', 'c'], () => 0.99).game.game_id).toBe('c');
		expect(() => pickChallenge([], [])).toThrow();
	});

	it('scores either pick like the server', () => {
		expect(scoreAnswer(entry('a', 'home'), 'home')).toMatchObject({ pick: 'home', correct: true });
		expect(scoreAnswer(entry('a', 'home'), 'away')).toMatchObject({ pick: 'away', correct: false });
		expect(scoreAnswer(entry('a', null), 'home').correct).toBe(false);
	});
});
