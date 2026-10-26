import { sveltekit } from '@sveltejs/kit/vite';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

declare const process: { env: Record<string, string | undefined> };

// The hash-routed static build (npm run build:artifact) is client-only and
// rejects page options, which the server build's root layout sets.
const dropPageOptions: Plugin = {
	name: 'sportsml:drop-page-options',
	enforce: 'pre',
	transform(code, id) {
		if (process.env.VITE_SPORTSML_DATA !== 'static') return;
		if (!id.endsWith('/src/routes/+layout.ts')) return;
		return code.replace(/^export const (ssr|prerender) = .*$/gm, '');
	}
};

export default defineConfig({
	plugins: [dropPageOptions, sveltekit()],
	// `npm run dev` talks to `sportsml web serve` on :8000
	server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
	test: { include: ['src/**/*.test.ts'] }
});
