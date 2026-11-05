import { describe, expect, it } from 'vitest';
import { experienceIndexOf, type CvDiagnostic } from './diagnostics.ts';

const text = [
	'## Résumé',
	'',
	'Ingénieur backend.',
	'',
	'## Expériences',
	'',
	'### Nordlys — Ingénieur — 01/2022 – 08/2026',
	'',
	'- Migration Airflow',
	'',
	'### Batiflux — Développeur — 09/2018 – 12/2021',
	'',
	'- Références : alex.moreau@example.fr',
	'',
	'## Formation',
	'',
	'- INSA Lyon, 2016'
].join('\n');

const at = (line_no: number): CvDiagnostic => ({
	code: 'personal_email',
	level: 'warning',
	line_no,
	section: null,
	message: '',
	suggestion: ''
});

describe('experienceIndexOf', () => {
	it('finds the experience holding the line', () => {
		expect(experienceIndexOf(at(9), text)).toBe(0);
		expect(experienceIndexOf(at(13), text)).toBe(1);
	});

	it('counts the title line as part of its experience', () => {
		expect(experienceIndexOf(at(11), text)).toBe(1);
	});

	it('returns null outside the experiences', () => {
		expect(experienceIndexOf(at(3), text)).toBeNull();
		expect(experienceIndexOf(at(5), text)).toBeNull();
		expect(experienceIndexOf(at(17), text)).toBeNull();
	});

	it('returns null for a diagnostic without a line', () => {
		expect(experienceIndexOf(at(0), text)).toBeNull();
	});
});
