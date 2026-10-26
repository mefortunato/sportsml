import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => ({
	upcoming: await api.upcoming(
		params.sport,
		params.season ? Number(params.season) : null,
		params.date ? Number(params.date) : null,
		fetch
	)
});
