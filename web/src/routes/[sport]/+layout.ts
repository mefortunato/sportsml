import { error } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ params, parent }) => {
	const { sports } = await parent();
	const info = sports.find((s) => s.sport === params.sport);
	if (!info) error(404, `Unknown sport ${params.sport}`);
	return { info };
};
