import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => {
	const [game, odds] = await Promise.all([
		api.game(params.sport, params.gameId),
		api.odds(params.sport)
	]);
	return { game, odds };
};
