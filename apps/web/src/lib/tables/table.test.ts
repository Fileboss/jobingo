import { describe, expect, it } from 'vitest';
import {
	fold,
	matches,
	nextSort,
	orderRows,
	readFilters,
	readSort,
	withParams,
	type Filter
} from './table.ts';

type Row = { name: string; stars: number | null; fit: number | null };
const defaults = [
	{ value: (row: Row) => row.stars, descending: true },
	{ value: (row: Row) => row.fit, descending: true },
	{ value: (row: Row) => row.name }
];
const columns = { nom: (row: Row) => row.name, fit: (row: Row) => row.fit };
const names = (rows: Row[]) => rows.map((row) => row.name);

const rows: Row[] = [
	{ name: 'Écluse', stars: null, fit: 90 },
	{ name: 'banque', stars: 3, fit: null },
	{ name: 'Atelier', stars: 3, fit: 70 },
	{ name: 'Delta', stars: 5, fit: 40 },
	{ name: 'Cèdre', stars: null, fit: null }
];

describe('the default order', () => {
	it('goes by each level in turn, unknown values last at each', () => {
		expect(names(orderRows(rows, defaults, columns, null))).toEqual([
			'Delta',
			'Atelier',
			'banque',
			'Écluse',
			'Cèdre'
		]);
	});
});

describe('a sort on a column', () => {
	it('sorts ascending and descending, unknown values last both ways', () => {
		const up = orderRows(rows, defaults, columns, { column: 'fit', descending: false });
		expect(names(up)).toEqual(['Delta', 'Atelier', 'Écluse', 'banque', 'Cèdre']);
		const down = orderRows(rows, defaults, columns, { column: 'fit', descending: true });
		expect(names(down)).toEqual(['Écluse', 'Atelier', 'Delta', 'banque', 'Cèdre']);
	});

	it('ignores case and accents in text', () => {
		const sorted = orderRows(rows, defaults, columns, { column: 'nom', descending: false });
		expect(names(sorted)).toEqual(['Atelier', 'banque', 'Cèdre', 'Delta', 'Écluse']);
	});

	it('breaks ties with the default order', () => {
		const tied = [
			{ name: 'B', stars: 1, fit: 50 },
			{ name: 'A', stars: 4, fit: 50 }
		];
		expect(names(orderRows(tied, defaults, columns, { column: 'fit', descending: true }))).toEqual([
			'A',
			'B'
		]);
	});

	it('cycles ascending, descending, then back to the default order', () => {
		const first = nextSort(null, 'fit');
		expect(first).toEqual({ column: 'fit', descending: false });
		const second = nextSort(first, 'fit');
		expect(second).toEqual({ column: 'fit', descending: true });
		expect(nextSort(second, 'fit')).toBeNull();
		expect(nextSort(second, 'nom')).toEqual({ column: 'nom', descending: false });
	});
});

describe('the search', () => {
	it('needs every word, in any text, case and accents aside', () => {
		expect(fold(' Énergie ')).toBe('energie');
		expect(matches('plume energie', ['Data engineer', 'Plume Énergie'])).toBe(true);
		expect(matches('plume java', ['Data engineer', 'Plume Énergie'])).toBe(false);
		expect(matches('  ', ['x'])).toBe(true);
	});
});

describe('the address', () => {
	it('reads a known sort and known filter values, and drops the rest', () => {
		const params = new URLSearchParams('tri=fit&sens=desc&statut=nope&relance=1');
		expect(readSort(params, columns)).toEqual({ column: 'fit', descending: true });
		expect(readSort(new URLSearchParams('tri=inconnu'), columns)).toBeNull();
		const filters: Filter[] = [
			{ name: 'statut', label: 'Statut', choices: { postule: 'Postulé' } },
			{ name: 'relance', label: 'Relance échue', choices: { '1': 'oui' } }
		];
		expect(readFilters(params, filters)).toEqual({ relance: '1' });
	});

	it('changes some params and keeps the others', () => {
		const params = new URLSearchParams('tri=fit&sens=asc&q=data');
		expect(withParams(params, { q: null, statut: 'postule' })).toBe(
			'?tri=fit&sens=asc&statut=postule'
		);
		expect(withParams(new URLSearchParams('q=x'), { q: '' })).toBe('');
	});
});
