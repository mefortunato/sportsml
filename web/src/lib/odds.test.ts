import { describe, expect, it } from 'vitest';
import { age, moved, withLine } from './odds';
import { noVig } from './pricing';
import type { GameHeader, Prediction } from './types';

const game: GameHeader = {
	game_id: 'g',
	season: 2026,
	date: 8,
	kickoff: null,
	home: { team: 'KC', name: 'Kansas City Chiefs' },
	away: { team: 'BUF', name: 'Buffalo Bills' },
	neutral: false,
	spread: 2.5,
	moneyline: { home: -140, away: 120 },
	total_line: 46.5,
	total_odds: { over: -110, under: -110 }
};
const prediction: Prediction = { margin: 3.5, win_prob: 0.6, edge: 1, ats_pick: 'home', total: 45 };

describe('current lines', () => {
	it('replace the built lines and move the picks with them', () => {
		const live = withLine(game, prediction, {
			spread: 4.5,
			ml_home: -200,
			ml_away: 170,
			total: 44.5,
			over_odds: -105,
			under_odds: -115
		});
		expect(live.game.spread).toBe(4.5);
		expect(live.game.total_odds).toEqual({ over: -105, under: -115 });
		// the model's 3.5 now sits under a 4.5 line: the pick flips to the away side
		expect(live.prediction?.ats_pick).toBe('away');
		expect(live.prediction?.edge).toBeCloseTo(-1);
		expect(live.prediction?.market_prob).toBeCloseTo(noVig(-200, 170));
		expect(live.prediction?.ml_pick).toBe('away');
		expect(live.prediction?.ou_pick).toBe('over');
		expect(live.prediction?.margin).toBe(3.5); // the prediction itself is unchanged
	});

	it('keep the built line for a market the book does not offer', () => {
		const live = withLine(game, prediction, { spread: null, ml_home: null, ml_away: null, total: 47 });
		expect(live.game.spread).toBe(2.5);
		expect(live.game.moneyline).toEqual({ home: -140, away: 120 });
		expect(live.prediction?.ou_pick).toBe('under');
		expect(withLine(game, prediction, null).game).toBe(game);
	});

	it('describe movement and age', () => {
		expect(moved(3, 4.5)).toBe(1.5);
		expect(moved(null, 4.5)).toBeNull();
		const now = new Date('2026-10-30T12:00:00Z');
		expect(age('2026-10-30T11:58:00Z', now)).toBe('2 min ago');
		expect(age('2026-10-30T09:00:00Z', now)).toBe('3 hours ago');
		expect(age(null, now)).toBe('unknown');
	});
});
