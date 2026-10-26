import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// `npm run build:artifact`: a static build with no server (data from
// `sportsml web export`), hash routing, and JS/CSS inlined into one page.
const artifact = process.env.VITE_SPORTSML_DATA === 'static';

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
				// Single-page app: FastAPI serves index.html for every non-API path.
				adapter: adapter({ fallback: 'index.html' })
			}
};

export default config;
