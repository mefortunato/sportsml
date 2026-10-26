import { sveltekit } from '@sveltejs/kit/vite';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

declare const process: { env: Record<string, string | undefined> };

// The hash-routed artifact build (npm run build:artifact) rejects page
// options, which the site build's root layout sets.
const dropPageOptions: Plugin = {
	name: 'sportsml:drop-page-options',
	enforce: 'pre',
	transform(code, id) {
		if (process.env.VITE_SPORTSML_TARGET !== 'artifact') return;
		if (!id.endsWith('/src/routes/+layout.ts')) return;
		return code.replace(/^export const (ssr|prerender) = .*$/gm, '');
	}
};

export default defineConfig({
	plugins: [dropPageOptions, sveltekit()],
	test: { include: ['src/**/*.test.ts'] }
});
