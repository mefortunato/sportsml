import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => ({
	rankings: await api.rankings(params.sport, fetch)
});
