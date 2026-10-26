import { api } from '$lib/api';
import type { LayoutLoad } from './$types';

// Single-page app: everything renders in the browser from the exported
// data. Not literals on purpose: SvelteKit then loads this module rather than
// reading the options from source, so vite.config.ts can drop them from the
// hash-routed artifact build, which is client-only anyway and rejects them.
const hashRouted = import.meta.env.VITE_SPORTSML_TARGET === 'artifact';
export const ssr = hashRouted;
export const prerender = hashRouted;

export const load: LayoutLoad = async () => ({ sports: await api.sports() });
