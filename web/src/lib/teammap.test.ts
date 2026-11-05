import { describe, expect, it } from 'vitest';
import {
	centerAt,
	extent,
	formatChange,
	formatMetric,
	goodness,
	positionAt,
	ranksAt,
	recordText,
	spread,
	valueAt
} from './teammap';
import type { TeamMapMetric, TeamMapSeries } from './types';

const series = (
	key: string,
	positions: TeamMapSeries['positions'],
	values: TeamMapSeries['values']
): TeamMapSeries => ({ team: { team: key, name: key }, positions, values });

const metric = (key: string, center: TeamMapMetric['center'], higher = true): TeamMapMetric => ({
	key,
	label: key,
	decimals: 1,
	higher_is_better: higher,
	center
});

const a = series('A', [[0, 0], [1, -1], null], { rating: [2, 4, null], allowed: [null, 20, 30] });
const b = series('B', [[-1, 1], [0, 0], [0.5, 0.5]], { rating: [3, 1, 0], allowed: [null, 10, 20] });

describe('team paths', () => {
	it('moves in a straight line between dates', () => {
		expect(positionAt(a, 0.5)).toEqual([0.5, -0.5]);
		expect(valueAt(a, 'rating', 0.25)).toBeCloseTo(2.5);
	});
	it('stays at the nearest known position where one is missing', () => {
		expect(positionAt(a, 1.2)).toEqual([1, -1]);
		expect(positionAt(a, 2)).toEqual([1, -1]);
	});
	it('has no value before a team has games', () => {
		expect(valueAt(a, 'allowed', 0.2)).toBeNull();
		expect(valueAt(a, 'allowed', 0.8)).toBe(20);
	});
	it('boxes every position on every date', () => {
		expect(extent([a, b])).toEqual({ x0: -1, x1: 1, y0: -1, y1: 1 });
	});
});

describe('metrics', () => {
	it('ranks by a metric, lower first where lower is better', () => {
		expect([...ranksAt([a, b], 0)]).toEqual([['B', 1], ['A', 2]]);
		expect([...ranksAt([a, b], 1, metric('allowed', 'mean', false))]).toEqual([['B', 1], ['A', 2]]);
	});
	it('centers stats on the league average at that date', () => {
		expect(centerAt(metric('allowed', 'mean'), [a, b], 1)).toBe(15);
		expect(centerAt(metric('win_pct', 'half'), [a, b], 1)).toBe(0.5);
	});
	it('scales colors to how far teams spread from the center', () => {
		expect(spread(metric('allowed', 'mean'), [a, b])).toBe(5);
	});
	it('turns the scale around where lower is better', () => {
		expect(goodness(metric('allowed', 'mean', false), 10, 15, 5)).toBe(1);
		expect(goodness(metric('rating', 'zero'), -20, 0, 5)).toBe(-1);
	});
	it('formats each kind of metric', () => {
		expect(formatMetric({ ...metric('win_pct', 'half'), decimals: 3 }, 0.625)).toBe('.625');
		expect(formatMetric(metric('rating', 'zero'), 3)).toBe('+3.0');
		expect(formatMetric(metric('allowed', 'mean'), 21.25)).toBe('21.3');
		expect(formatChange({ ...metric('win_pct', 'half'), decimals: 3 }, -0.125)).toBe('−.125');
		expect(formatChange(metric('allowed', 'mean'), 2)).toBe('+2.0');
		expect(recordText([5, 3, 0])).toBe('5–3');
		expect(recordText([0, 0, 0])).toBeNull();
	});
});
