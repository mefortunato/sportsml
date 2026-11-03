// Light/dark theme choice. app.css follows the OS setting unless <html>
// carries data-theme; the header toggle sets it and remembers the choice.
// app.html applies a remembered choice before first paint (keep the storage
// key in sync with the inline script there).

export type Theme = 'light' | 'dark';

export const THEME_KEY = 'sportsml-theme';

export function parseTheme(value: unknown): Theme | null {
	return value === 'light' || value === 'dark' ? value : null;
}

/** The theme on screen: an explicit data-theme, else the OS preference. */
export function effectiveTheme(attr: string | null | undefined, prefersDark: boolean): Theme {
	return parseTheme(attr) ?? (prefersDark ? 'dark' : 'light');
}

export function otherTheme(theme: Theme): Theme {
	return theme === 'dark' ? 'light' : 'dark';
}

// Storage can be missing or throw (private windows, blocked site data,
// sandboxed frames); the toggle still works for the visit without it.
export function storedTheme(): Theme | null {
	try {
		return parseTheme(localStorage.getItem(THEME_KEY));
	} catch {
		return null;
	}
}

export function storeTheme(theme: Theme): void {
	try {
		localStorage.setItem(THEME_KEY, theme);
	} catch {
		// not remembered; still applied
	}
}
