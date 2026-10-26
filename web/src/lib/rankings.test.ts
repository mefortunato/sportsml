import { describe, expect, it } from 'vitest';
import { defaultPins, rankAt, togglePin, yExtent } from './rankings';
import type { RankingSeason } from './types';

const team = (key: string) => ({ team: key, name: key });
const season: RankingSeason = {
	season: 2025,
	source: 'backtest',
	dates: [1, 2, 3],
	teams: [
		{ team: team('A'), ratings: [3, 1, -2] },
		{ team: team('B'), ratings: [-1, 2, 6.4] },
		{ team: team('C'), ratings: [-2, -3, null] },
		{ team: team('D'), ratings: [0, 0, -4.4] }
	]
};

describe('power rankings', () => {
	it('ranks by rating with the change since the previous date', () => {
		const rows = rankAt(season, 2);
		expect(rows.map((r) => [r.team.team, r.rank, r.change])).toEqual([
			['B', 1, 0],
			['A', 2, 0],
			['D', 3, 0]
		]);
		expect(rankAt(season, 1).map((r) => [r.team.team, r.change])).toEqual([
			['B', 2],
			['A', -1],
			['D', -1],
			['C', 0]
		]);
		expect(rankAt(season, 0).every((r) => r.change === null)).toBe(true);
	});

	it('highlights the top teams of the latest date', () => {
		expect(defaultPins(season)).toEqual({ B: 1, A: 2, D: 3 });
	});

	it('keeps slots with their teams and reuses freed slots', () => {
		let pins = togglePin({}, 'A');
		pins = togglePin(pins, 'B');
		expect(pins).toEqual({ A: 1, B: 2 });
		pins = togglePin(pins, 'A');
		expect(pins).toEqual({ B: 2 });
		pins = togglePin(pins, 'C');
		expect(pins).toEqual({ B: 2, C: 1 });
		pins = togglePin(togglePin(pins, 'D'), 'A');
		expect(pins).toEqual({ B: 2, C: 1, A: 3 });
	});

	it('uses a symmetric axis on round ticks', () => {
		expect(yExtent(season)).toEqual({ max: 7.5, step: 2.5 });
	});
});
