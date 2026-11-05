import { describe, expect, it } from 'vitest';
import { CUBE_EDGES, extent, positionAt, project, ranksAt, ratingAt, rotate } from './teammap';
import type { TeamMapSeries } from './types';

const series = (
	key: string,
	positions: TeamMapSeries['positions'],
	ratings: TeamMapSeries['ratings']
): TeamMapSeries => ({ team: { team: key, name: key }, positions, ratings });

describe('team paths', () => {
	const a = series('A', [[0, 0, 0], [1, 0, -1], null], [2, 4, null]);
	it('moves in a straight line between dates', () => {
		expect(positionAt(a, 0.5)).toEqual([0.5, 0, -0.5]);
		expect(ratingAt(a, 0.25)).toBeCloseTo(2.5);
	});
	it('shows the nearest known date where one is missing', () => {
		expect(positionAt(a, 1.2)).toEqual([1, 0, -1]);
		expect(positionAt(a, 2)).toEqual([1, 0, -1]);
		expect(ratingAt(a, 1.8)).toBe(4);
	});
	it('ranks by rating at a date', () => {
		const b = series('B', [null, null, null], [3, 1, 0]);
		expect([...ranksAt([a, b], 0)]).toEqual([
			['B', 1],
			['A', 2]
		]);
		expect([...ranksAt([a, b], 2)]).toEqual([['B', 1]]);
	});
});

describe('camera', () => {
	it('turns a quarter around the vertical axis', () => {
		const [x, y, z] = rotate([1, 0, 0], Math.PI / 2, 0);
		expect([x, y, z].map((v) => +v.toFixed(6))).toEqual([0, 0, -1]);
	});
	it('draws nearer points larger, with y down on screen', () => {
		const near = project([0, 1, 1], 100);
		const far = project([0, 1, -1], 100);
		expect(near.scale).toBeGreaterThan(1);
		expect(far.scale).toBeLessThan(1);
		expect(near.y).toBeLessThan(0);
	});
	it('has a cube of 12 edges', () => {
		expect(CUBE_EDGES).toHaveLength(12);
	});
});

describe('extent', () => {
	it('boxes every position on every date', () => {
		const t = series('A', [[-1, 0, 0], null, [1, 0.5, 0.2]], [0, 0, 0]);
		const box = extent([t]);
		expect(box.center).toEqual([0, 0.25, 0.1]);
		expect(box.edges).toHaveLength(12);
		expect(box.radius).toBeCloseTo(Math.hypot(1, 0.25, 0.1));
	});
});
