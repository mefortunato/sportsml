import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// A static site: no server, data from `sportsml web export` (static/data).
//   npm run build           GitHub Pages: path routing under BASE_PATH, with
//                           404.html booting the app for deep links
//   npm run build:artifact  one page (hash routing, JS/CSS inlined), e.g.
//                           for a claude.ai artifact
const artifact = process.env.VITE_SPORTSML_TARGET === 'artifact';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: artifact
		? {
				adapter: adapter({
					pages: 'build-artifact',
					assets: 'build-artifact',
					fallback: 'index.html'
				}),
				router: { type: 'hash' },
				output: { bundleStrategy: 'inline' }
			}
		: {
				adapter: adapter({ fallback: '404.html' }),
				paths: { base: process.env.BASE_PATH ?? '' }
			}
};

export default config;
