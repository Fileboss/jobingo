import { describe, expect, it } from 'vitest';
import { formatDetail } from './format.ts';

describe('an eval run’s detail', () => {
	it('reads a tally and a list as text, and says when they are empty', () => {
		expect(formatDetail({ 'interview -> recruiter_other': 1 })).toBe(
			'interview -> recruiter_other : 1'
		);
		expect(formatDetail(['fit-01', 'fit-04'])).toBe('fit-01, fit-04');
		expect(formatDetail([])).toBe('aucun');
		expect(formatDetail({})).toBe('aucune');
		expect(formatDetail('13/14')).toBe('13/14');
	});
});
