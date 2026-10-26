import { get } from 'svelte/store';
import { describe, expect, it } from 'vitest';
import { applyAnswer, challengeStore, emptyRecord, loadRecord } from './challenge';
import {
	handicap,
	kickoffLabel,
	marginLabel,
	signed,
	spreadLabel,
	winLoss,
	winRate
} from './format';
import type { ChallengeAnswer, Team } from './types';

const KC: Team = { team: 'KC', name: 'Kansas City Chiefs' };
const BUF: Team = { team: 'BUF', name: 'Buffalo Bills' };

describe('format', () => {
	it('labels spreads sportsbook-style from the home margin', () => {
		expect(spreadLabel(KC, BUF, 3.5)).toBe('KC −3.5');
		expect(spreadLabel(KC, BUF, -6)).toBe('BUF −6');
		expect(spreadLabel(KC, BUF, 0)).toBe("Pick'em");
		expect(spreadLabel(KC, BUF, null)).toBe('No line');
	});

	it('gives each side its handicap', () => {
		expect(handicap(3.5, 'home')).toBe('−3.5');
		expect(handicap(3.5, 'away')).toBe('+3.5');
		expect(handicap(0, 'home')).toBe('PK');
	});

	it('formats margins and records', () => {
		expect(signed(2.25)).toBe('+2.3');
		expect(signed(-1)).toBe('−1.0');
		expect(marginLabel(KC, BUF, -4.24)).toBe('BUF by 4.2');
		expect(winLoss({ wins: 8, losses: 3, ties: 1 })).toBe('8-3-1');
		expect(winRate(0, 0)).toBeNull();
		expect(winRate(3, 1)).toBe(0.75);
	});

	it('reads nflverse kickoff times', () => {
		expect(kickoffLabel('2026-11-01 13:00')).toBe('Sun, Nov 1 · 1:00 PM ET');
		expect(kickoffLabel('2026-10-26 20:15')).toBe('Mon, Oct 26 · 8:15 PM ET');
		expect(kickoffLabel(null)).toBe('TBD');
	});
});

function answer(id: string, correct: boolean, modelCorrect: boolean): ChallengeAnswer {
	return {
		game_id: id,
		pick: 'home',
		covered: correct ? 'home' : 'away',
		correct,
		spread: 3,
		result: { home_score: 20, away_score: 17, margin: 3, covered: 'home' },
		model: {
			margin: 1,
			win_prob: 0.55,
			edge: -2,
			ats_pick: modelCorrect === correct ? 'home' : 'away',
			correct: modelCorrect
		}
	};
}

class MemoryStorage {
	items = new Map<string, string>();
	getItem = (k: string) => this.items.get(k) ?? null;
	setItem = (k: string, v: string) => void this.items.set(k, v);
	removeItem = (k: string) => void this.items.delete(k);
}

describe('challenge record', () => {
	it('counts player and model results and streaks', () => {
		let record = emptyRecord();
		record = applyAnswer(record, answer('a', true, false));
		record = applyAnswer(record, answer('b', true, true));
		record = applyAnswer(record, answer('c', false, true));
		expect(record.played).toBe(3);
		expect(record.player).toEqual({ wins: 2, losses: 1 });
		expect(record.model).toEqual({ wins: 2, losses: 1 });
		expect(record.agreed).toBe(1); // only game b: same pick as the model
		expect([record.streak, record.bestStreak]).toEqual([0, 2]);
		expect(record.seen).toEqual(['a', 'b', 'c']);
	});

	it('persists across store instances and resets', () => {
		const storage = new MemoryStorage();
		const first = challengeStore('nfl', storage);
		first.record(answer('a', true, true));
		const again = challengeStore('nfl', storage);
		expect(get(again).player.wins).toBe(1);
		expect(loadRecord('cbb', storage).played).toBe(0);
		again.reset();
		expect(get(challengeStore('nfl', storage)).played).toBe(0);
	});
});
