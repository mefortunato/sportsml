import { describe, expect, it } from 'vitest';
import { matchesGame, matchesTeam, normalize, searchTeams, teamScore } from './search';
import type { Team } from './types';

const lions: Team = { team: 'DET', name: 'Detroit Lions', nickname: 'Lions' };
const chiefs: Team = { team: 'KC', name: 'Kansas City Chiefs', nickname: 'Chiefs' };
const kansas: Team = { team: 'Kansas', name: 'Kansas', abbr: 'KU' };
const kstate: Team = { team: 'Kansas State', name: 'Kansas State', abbr: 'KSU' };
const sjsu: Team = { team: 'San José State', name: 'San José State', abbr: 'SJSU' };

describe('team search', () => {
	it('normalizes case, accents and punctuation', () => {
		expect(normalize("  St. Mary's (CA) ")).toBe('st mary s ca');
		expect(normalize('San José')).toBe('san jose');
	});

	it('matches keys, abbreviations, names and nicknames', () => {
		expect(matchesTeam(lions, 'det')).toBe(true);
		expect(matchesTeam(lions, 'lions')).toBe(true);
		expect(matchesTeam(lions, 'detroit l')).toBe(true);
		expect(matchesTeam(kansas, 'ku')).toBe(true);
		expect(matchesTeam(sjsu, 'san jose')).toBe(true);
		expect(matchesTeam(lions, 'chiefs')).toBe(false);
	});

	it('matches word prefixes in any order and substrings', () => {
		expect(matchesTeam(chiefs, 'city kan')).toBe(true);
		expect(matchesTeam(lions, 'troit')).toBe(true);
		expect(teamScore(chiefs, 'city kan')).toBe(2);
		expect(teamScore(lions, 'troit')).toBe(1);
	});

	it('matches everything on an empty query', () => {
		expect(matchesTeam(lions, '')).toBe(true);
		expect(matchesTeam(lions, '  ')).toBe(true);
	});

	it('matches a game by either team', () => {
		const game = { home: lions, away: chiefs };
		expect(matchesGame(game, 'chiefs')).toBe(true);
		expect(matchesGame(game, 'det')).toBe(true);
		expect(matchesGame(game, 'bears')).toBe(false);
	});

	it('ranks exact names over prefixes over looser matches', () => {
		const teams = [kstate, chiefs, kansas];
		expect(searchTeams(teams, 'kansas').map((t) => t.team)).toEqual(['Kansas', 'Kansas State', 'KC']);
		expect(searchTeams(teams, 'kansas', 1).map((t) => t.team)).toEqual(['Kansas']);
		expect(searchTeams(teams, '')).toEqual([]);
	});
});
