import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent }) => {
	const { sports } = await parent();
	if (sports.length === 1) redirect(307, `/${sports[0].sport}`);
	return {};
};
