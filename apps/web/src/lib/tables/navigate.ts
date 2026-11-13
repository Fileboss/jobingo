import { goto } from '$app/navigation';
import { page } from '$app/state';
import { withParams } from './table.ts';

let queue: Promise<void> = Promise.resolve();

/**
 * The same page with some params of its address changed: a new history entry, or the
 * current one replaced while typing a search. Scroll and focus stay where they are.
 * Changes run one after the other, each on the address the previous one left: a
 * filter chosen right after clearing the search does not bring the search back.
 */
export function changeParams(
	path: string,
	changes: Record<string, string | null>,
	replace = false
): Promise<void> {
	queue = queue
		.then(() =>
			// eslint-disable-next-line svelte/no-navigation-without-resolve -- the caller resolved the path; only the query changes
			goto(`${path}${withParams(page.url.searchParams, changes)}`, { replace, reset: false })
		)
		.catch(() => {});
	return queue;
}
