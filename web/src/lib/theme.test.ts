import { describe, expect, it } from 'vitest';
import { effectiveTheme, otherTheme, parseTheme } from './theme';

describe('theme', () => {
	it('parses only known themes', () => {
		expect(parseTheme('light')).toBe('light');
		expect(parseTheme('dark')).toBe('dark');
		expect(parseTheme('auto')).toBeNull();
		expect(parseTheme(null)).toBeNull();
	});

	it('prefers an explicit attribute over the OS setting', () => {
		expect(effectiveTheme('light', true)).toBe('light');
		expect(effectiveTheme('dark', false)).toBe('dark');
		expect(effectiveTheme(null, true)).toBe('dark');
		expect(effectiveTheme('', false)).toBe('light');
	});

	it('flips', () => {
		expect(otherTheme('light')).toBe('dark');
		expect(otherTheme('dark')).toBe('light');
	});
});
