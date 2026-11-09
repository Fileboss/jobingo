import { describe, expect, it } from 'vitest';
import { bareAddress, replySubject, splitAddresses, statusLabel } from './format.ts';

describe('replying', () => {
	it('adds Re: once', () => {
		expect(replySubject('Entretien')).toBe('Re: Entretien');
		expect(replySubject('RE : Entretien')).toBe('RE : Entretien');
	});

	it('keeps the address of a sender', () => {
		expect(bareAddress('Camille Roux <camille@volteo.test>')).toBe('camille@volteo.test');
		expect(bareAddress('rh@volteo.test')).toBe('rh@volteo.test');
	});

	it('splits recipients on commas and spaces', () => {
		expect(splitAddresses('a@x.test, b@y.test ;c@z.test')).toEqual([
			'a@x.test',
			'b@y.test',
			'c@z.test'
		]);
	});

	it('says a dry run was only simulated', () => {
		expect(statusLabel({ status: 'sent', dry_run: true })).toBe('Simulé');
		expect(statusLabel({ status: 'sent', dry_run: false })).toBe('Envoyé');
	});
});
