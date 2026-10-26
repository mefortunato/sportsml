import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => ({
	game: await api.game(params.sport, params.gameId)
});
