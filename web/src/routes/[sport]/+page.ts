import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, url, fetch }) => {
	const season = url.searchParams.get('season');
	const date = url.searchParams.get('date');
	return {
		upcoming: await api.upcoming(
			params.sport,
			season ? Number(season) : null,
			date ? Number(date) : null,
			fetch
		)
	};
};
