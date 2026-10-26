import { describe, expect, it } from 'vitest';
import {
	defaultPins,
	filterOptions,
	matchesFilter,
	playoffRanks,
	rankAt,
	reconcilePins,
	togglePin,
	yExtent
} from './rankings';
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
		expect(yExtent(season)).toEqual({ max: 8, step: 2 });
	});
});

describe('division filters', () => {
	const t = (key: string, conference?: string, division?: string) => ({
		team: key,
		name: key,
		conference,
		division
	});
	const teams = [t('A', 'AFC', 'AFC East'), t('B', 'NFC', 'NFC West'), t('C', 'AFC', 'AFC West'), t('D', 'AFC', 'AFC East')];

	it('lists conferences and their divisions from team metadata', () => {
		expect(filterOptions(teams)).toEqual({
			conferences: ['AFC', 'NFC'],
			divisions: { AFC: ['AFC East', 'AFC West'], NFC: ['NFC West'] }
		});
		expect(filterOptions([t('X'), t('Y')])).toEqual({ conferences: [], divisions: {} });
	});

	it('matches a conference or a division', () => {
		expect(teams.filter((x) => matchesFilter(x, {})).length).toBe(4);
		expect(teams.filter((x) => matchesFilter(x, { conference: 'AFC' })).map((x) => x.team)).toEqual(['A', 'C', 'D']);
		expect(
			teams.filter((x) => matchesFilter(x, { conference: 'AFC', division: 'AFC East' })).map((x) => x.team)
		).toEqual(['A', 'D']);
	});

	it('keeps surviving highlights in their slots and fills the rest by rank', () => {
		const rows = ['D', 'A', 'C'].map((key, i) => ({ team: t(key), rating: -i, rank: i + 1, change: null }));
		// B is filtered out, A survives in slot 2; slots 1 and 3 go to D then C
		expect(reconcilePins({ B: 1, A: 2 }, rows)).toEqual({ A: 2, D: 1, C: 3 });
		expect(reconcilePins({ A: 3 }, rows.slice(0, 2))).toEqual({ A: 3, D: 1 });
		expect(reconcilePins({}, [])).toEqual({});
	});
});

describe('playoff marks', () => {
	const marked: RankingSeason = {
		...season,
		playoffs: { D: 'champion', A: 'semifinal', B: 'semifinal', C: 'runner_up' }
	};

	it('filters to the final teams', () => {
		const keep = marked.teams.filter((t) => matchesFilter(t.team, { playoffs: true }, marked.playoffs));
		expect(keep.map((t) => t.team.team)).toEqual(['A', 'B', 'C', 'D']);
		expect(matchesFilter(team('A'), { playoffs: true }, {})).toBe(false);
	});

	it('lists champion, runner-up, then the rest by league rank', () => {
		// at the last date C has no rating, so it is left out
		expect(playoffRanks(marked, 2).map(({ row, stage }) => [row.team.team, row.rank, stage])).toEqual([
			['D', 3, 'champion'],
			['B', 1, 'semifinal'],
			['A', 2, 'semifinal']
		]);
		expect(playoffRanks(season, 2)).toEqual([]);
	});
});
