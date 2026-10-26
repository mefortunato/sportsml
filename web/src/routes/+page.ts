import { redirect } from '@sveltejs/kit';
import { links } from '$lib/links';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent }) => {
	const { sports } = await parent();
	if (sports.length === 1) redirect(307, links.upcoming(sports[0].sport));
	return {};
};
