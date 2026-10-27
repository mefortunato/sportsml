import { describe, expect, it } from 'vitest';
import { noVig, normalCdf, priceMoneyline, priceSpread, priceTotal, validOdds } from './pricing';
import type { Prediction, Pricing } from './types';

const prediction: Prediction = {
	margin: 6,
	win_prob: 0.68,
	edge: 3,
	ats_pick: 'home',
	total: 48,
	ou_pick: 'over'
};
const trusted: Pricing = { sigma: 13, total_sigma: 13, trust: { spread: 1, moneyline: 1, total: 1 } };
const untrusted: Pricing = { sigma: 13, total_sigma: 13, trust: { spread: 0, moneyline: 0, total: 0 } };
const juice = { home: -110, away: -110 };

describe('pricing', () => {
	it('computes the normal CDF', () => {
		expect(normalCdf(0)).toBeCloseTo(0.5, 7);
		expect(normalCdf(1.96)).toBeCloseTo(0.975, 4);
		expect(normalCdf(-1)).toBeCloseTo(0.158655, 5);
	});

	it('removes the bookmaker margin from moneylines', () => {
		expect(noVig(-110, -110)).toBeCloseTo(0.5);
		expect(noVig(-200, 170)).toBeCloseTo(2 / 3 / (2 / 3 + 100 / 270));
	});

	it('prices both sides of a spread from the model margin', () => {
		const [away, home] = priceSpread(prediction, 3, juice, trusted);
		expect(home.raw).toBeCloseTo(normalCdf(3 / 13));
		expect(home.prob + away.prob).toBeCloseTo(1);
		expect(home.breakEven).toBeCloseTo(110 / 210);
		expect(home.ev).toBeCloseTo(home.prob * (100 / 110) - (1 - home.prob));
		expect(home.stake).toBeGreaterThan(0);
		expect(away.stake).toBe(0);
		// a line at the model's margin is a coin flip: no bet at -110
		const [, even] = priceSpread(prediction, 6, juice, trusted);
		expect(even.prob).toBeCloseTo(0.5);
		expect(even.ev).toBeLessThan(0);
		expect(even.stake).toBe(0);
	});

	it('trusts the model only as much as the backtest says', () => {
		const [away, home] = priceSpread(prediction, 3, juice, untrusted);
		expect(home.prob).toBeCloseTo(0.5);
		expect(away.prob).toBeCloseTo(0.5);
		expect(home.raw).toBeGreaterThan(0.5); // still shown
		// with no trust, only a better price than even money is worth a bet
		const [, plus] = priceSpread(prediction, 3, { home: 110, away: -130 }, untrusted);
		expect(plus.ev).toBeGreaterThan(0);
		expect(plus.stake).toBeGreaterThan(0);
	});

	it('moves the moneyline toward the consensus market, not the price entered', () => {
		const odds = { home: -150, away: 130 };
		const consensus = 0.6;
		const [, home] = priceMoneyline(prediction, odds, { ...trusted, trust: { moneyline: 0.5 } }, consensus);
		expect(home.prob).toBeCloseTo(0.6 + 0.5 * (0.68 - 0.6));
		const [, alone] = priceMoneyline(prediction, odds, untrusted);
		expect(alone.prob).toBeCloseTo(noVig(-150, 130));
	});

	it('prices the over and under, only with a model total', () => {
		const quotes = priceTotal(prediction, 44.5, { over: -105, under: -115 }, trusted);
		expect(quotes).not.toBeNull();
		const [over, under] = quotes!;
		expect(over.prob).toBeCloseTo(normalCdf(3.5 / 13));
		expect(over.prob + under.prob).toBeCloseTo(1);
		expect(over.odds).toBe(-105);
		expect(priceTotal({ ...prediction, total: null }, 44.5, { over: -110, under: -110 }, trusted)).toBeNull();
	});

	it('accepts only real American odds', () => {
		expect(validOdds(-110)).toBe(true);
		expect(validOdds(150)).toBe(true);
		expect(validOdds(50)).toBe(false);
		expect(validOdds(Number.NaN)).toBe(false);
	});
});
