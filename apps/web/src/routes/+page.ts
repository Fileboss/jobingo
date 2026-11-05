import { api } from '#lib/api/client.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const { data } = await api.GET('/api/me', { fetch });
		return { account: data ?? null };
	} catch {
		return { account: null };
	}
};
