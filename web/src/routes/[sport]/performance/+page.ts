import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => ({
	performance: await api.performance(params.sport, fetch)
});
