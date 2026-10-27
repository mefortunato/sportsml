import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => {
	const [upcoming, odds] = await Promise.all([
		api.upcoming(
			params.sport,
			params.season ? Number(params.season) : null,
			params.date ? Number(params.date) : null
		),
		api.odds(params.sport)
	]);
	return { upcoming, odds };
};
