import { get } from 'svelte/store';
import { describe, expect, it } from 'vitest';
import { applyAnswer, challengeStore, emptyRecord, loadRecord } from './challenge';
import {
	dateText,
	handicap,
	seasonsText,
	seasonText,
	kickoffLabel,
	marginLabel,
	signed,
	spreadLabel,
	winLoss,
	winRate
} from './format';
import { americanOdds, breakEven, payout, pickLabel, unitsLabel } from './markets';
import type { ChallengeAnswer, Team } from './types';

const KC: Team = { team: 'KC', name: 'Kansas City Chiefs' };
const BUF: Team = { team: 'BUF', name: 'Buffalo Bills' };

describe('format', () => {
	it('names a date by its own name, else the sport label and number', () => {
		expect(dateText('Day', 7, 'Oct 28')).toBe('Oct 28');
		expect(dateText('Week', 9)).toBe('Week 9');
		expect(dateText('Week', 9, null)).toBe('Week 9');
		expect(dateText('Week', null)).toBe('—');
	});

	it('shows a two-year season by the years it spans', () => {
		expect(seasonText(2026)).toBe('2026');
		expect(seasonText(2026, true)).toBe('2025–26');
		expect(seasonsText([2021, 2025])).toBe('2021–2025');
		expect(seasonsText([2022, 2026], true)).toBe('2021–22 to 2025–26');
		expect(seasonsText([2026, 2026], true)).toBe('2025–26');
		expect(seasonsText([])).toBe('');
	});

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

	it('prices bets at American odds', () => {
		expect(payout(-110)).toBeCloseTo(100 / 110);
		expect(payout(150)).toBe(1.5);
		expect(breakEven()).toBeCloseTo(0.5238, 4);
		expect(breakEven(100)).toBe(0.5);
		expect(americanOdds(130)).toBe('+130');
		expect(americanOdds(-150.4)).toBe('−150');
		expect(americanOdds(null)).toBe('—');
		expect(unitsLabel(1.25)).toBe('+1.3 u');
		expect(unitsLabel(-2)).toBe('−2.0 u');
		expect(pickLabel('over', KC, BUF)).toBe('Over');
		expect(pickLabel('away', KC, BUF)).toBe('BUF');
	});

	it('reads nflverse kickoff times', () => {
		expect(kickoffLabel('2026-11-01 13:00')).toBe('Sun, Nov 1 · 1:00 PM ET');
		expect(kickoffLabel('2026-10-26 20:15')).toBe('Mon, Oct 26 · 8:15 PM ET');
		expect(kickoffLabel(null)).toBe('TBD');
	});
});

function answer(id: string, correct: boolean, modelCorrect: boolean): ChallengeAnswer {
	const modelPick = modelCorrect === correct ? 'home' : 'away';
	return {
		game_id: id,
		market: 'spread',
		pick: 'home',
		outcome: correct ? 'home' : 'away',
		odds: { home: -110, away: -110 },
		covered: correct ? 'home' : 'away',
		correct,
		units: correct ? 100 / 110 : -1,
		spread: 3,
		result: { home_score: 20, away_score: 17, margin: 3, covered: 'home' },
		model: {
			margin: 1,
			win_prob: 0.55,
			edge: -2,
			ats_pick: modelPick,
			pick: modelPick,
			correct: modelCorrect,
			units: modelCorrect ? 100 / 110 : -1
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
		expect(record.player).toMatchObject({ wins: 2, losses: 1 });
		expect(record.player.units).toBeCloseTo((2 * 100) / 110 - 1);
		expect(record.model).toMatchObject({ wins: 2, losses: 1 });
		expect(record.agreed).toBe(1); // only game b: same pick as the model
		expect([record.streak, record.bestStreak]).toEqual([0, 2]);
		expect(record.seen).toEqual(['a', 'b', 'c']);
	});

	it('persists across store instances and resets', () => {
		const storage = new MemoryStorage();
		const first = challengeStore('nfl', 'spread', storage);
		first.record(answer('a', true, true));
		const again = challengeStore('nfl', 'spread', storage);
		expect(get(again).player.wins).toBe(1);
		expect(loadRecord('cbb', 'spread', storage).played).toBe(0);
		again.reset();
		expect(get(challengeStore('nfl', 'spread', storage)).played).toBe(0);
	});

	it('keeps one record per market, the spread under its old key', () => {
		const storage = new MemoryStorage();
		challengeStore('nfl', 'total', storage).record(answer('a', true, true));
		expect(loadRecord('nfl', 'total', storage).played).toBe(1);
		expect(loadRecord('nfl', 'spread', storage).played).toBe(0);
		// a record saved before there were markets or units
		storage.setItem(
			'sportsml:challenge:nfl',
			JSON.stringify({ played: 2, player: { wins: 1, losses: 1 }, model: { wins: 2, losses: 0 } })
		);
		const legacy = loadRecord('nfl', 'spread', storage);
		expect(legacy.played).toBe(2);
		expect(legacy.player).toEqual({ wins: 1, losses: 1, units: 0 });
		expect(legacy.seen).toEqual([]);
	});
});
