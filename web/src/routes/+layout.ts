import { api } from '$lib/api';
import type { LayoutLoad } from './$types';

// Single-page app: everything renders in the browser from the API.
export const ssr = false;
export const prerender = false;

export const load: LayoutLoad = async ({ fetch }) => ({ sports: await api.sports(fetch) });
