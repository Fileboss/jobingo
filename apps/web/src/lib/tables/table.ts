/**
 * Order, search and filters of the Offres and Candidatures tables, as in the POC.
 *
 * Without a chosen sort, rows follow a default order of several levels. A click on a
 * header sorts on that column, a second reverses it, a third goes back to the default
 * order, which also breaks ties. An unknown value (none, empty text) comes after the
 * known ones, in either direction. The state lives in the address: `?tri=<column>&
 * sens=asc|desc&q=<words>` plus each table's filters, so it is shareable and survives
 * « précédent ».
 */

export type Key = string | number | null | undefined;
export type Sort = { column: string; descending: boolean } | null;
/** One level of the default order. */
export type Level<T> = { value: (row: T) => Key; descending?: boolean };

/** Lower case, without accents: « Énergie » finds « energie ». */
export function fold(text: string): string {
	return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
}

/** What a column compares on: text folded, an empty text unknown. */
function comparable(value: Key): string | number | null {
	if (value === null || value === undefined) return null;
	if (typeof value === 'string') return fold(value) || null;
	return value;
}

function compare(a: string | number, b: string | number): number {
	if (typeof a === 'number' && typeof b === 'number') return a - b;
	return String(a).localeCompare(String(b), 'fr');
}

/** The default order: each level breaks the ties of the one before, unknown last. */
export function byLevels<T>(levels: Level<T>[]): (a: T, b: T) => number {
	return (a, b) => {
		for (const level of levels) {
			const [x, y] = [comparable(level.value(a)), comparable(level.value(b))];
			if (x === null && y === null) continue;
			if (x === null) return 1;
			if (y === null) return -1;
			const order = compare(x, y) * (level.descending ? -1 : 1);
			if (order !== 0) return order;
		}
		return 0;
	};
}

/** Rows in the default order, or sorted on one column with that order breaking ties. */
export function orderRows<T>(
	rows: readonly T[],
	defaults: Level<T>[],
	columns: Record<string, (row: T) => Key>,
	sort: Sort
): T[] {
	const ordered = [...rows].sort(byLevels(defaults));
	const getter = sort ? columns[sort.column] : undefined;
	if (!sort || !getter) return ordered;
	const known = ordered.filter((row) => comparable(getter(row)) !== null);
	const unknown = ordered.filter((row) => comparable(getter(row)) === null);
	// Array.prototype.sort is stable: equal rows keep their default order.
	known.sort((a, b) => {
		const order = compare(comparable(getter(a))!, comparable(getter(b))!);
		return sort.descending ? -order : order;
	});
	return [...known, ...unknown];
}

/** A click on a header: ascending, then descending, then the default order. */
export function nextSort(sort: Sort, column: string): Sort {
	if (sort?.column !== column) return { column, descending: false };
	return sort.descending ? null : { column, descending: true };
}

/** Every word of the search appears in one of the texts, case and accents aside. */
export function matches(query: string, texts: string[]): boolean {
	const haystack = texts.map(fold).join(' ');
	return fold(query)
		.split(/\s+/)
		.filter(Boolean)
		.every((word) => haystack.includes(word));
}

/** The sort the address asks for; an unknown column is the default order. */
export function readSort(
	params: { get(name: string): string | null },
	columns: Record<string, unknown>
): Sort {
	const column = params.get('tri');
	if (!column || !(column in columns)) return null;
	return { column, descending: params.get('sens') === 'desc' };
}

/** The address params of a sort. */
export function sortParams(sort: Sort): Record<string, string | null> {
	return sort
		? { tri: sort.column, sens: sort.descending ? 'desc' : 'asc' }
		: { tri: null, sens: null };
}

/** A filter of a table: one value among its choices, or none. A single choice is a box. */
export type Filter = { name: string; label: string; choices: Record<string, string> };

/** The active filters the address asks for; an unknown value is dropped. */
export function readFilters(
	params: { get(name: string): string | null },
	filters: Filter[]
): Record<string, string> {
	const active: Record<string, string> = {};
	for (const filter of filters) {
		const value = params.get(filter.name);
		if (value && value in filter.choices) active[filter.name] = value;
	}
	return active;
}

/** The search part of an address with some params changed; null removes one. */
export function withParams(
	params: { toString(): string },
	changes: Record<string, string | null>
): string {
	const next = new URLSearchParams(params.toString());
	for (const [name, value] of Object.entries(changes)) {
		if (value) next.set(name, value);
		else next.delete(name);
	}
	const search = next.toString();
	return search ? `?${search}` : '';
}
