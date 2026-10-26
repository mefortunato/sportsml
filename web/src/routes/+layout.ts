import { api } from '$lib/api';
import type { LayoutLoad } from './$types';

// Single-page app: everything renders in the browser from the API. Not
// literals on purpose: SvelteKit then loads this module rather than reading
// the options from source, so vite.config.ts can drop them from the static
// (hash-routed) build, which is client-only anyway and rejects page options.
const server = import.meta.env.VITE_SPORTSML_DATA !== 'static';
export const ssr = !server;
export const prerender = !server;

export const load: LayoutLoad = async ({ fetch }) => ({ sports: await api.sports(fetch) });
