import type { components } from '#lib/api/schema.d.ts';

export type Offer = components['schemas']['Offer'];

const thousands = (euros: number) => `${Math.round(euros / 1000)} k€`;

/** The stated salary, in thousands of euros, or a dash when the offer states none. */
export function salaryLabel(offer: Pick<Offer, 'salary_min' | 'salary_max'>): string {
	const { salary_min: low, salary_max: high } = offer;
	if (low != null && high != null && low !== high) return `${thousands(low)} – ${thousands(high)}`;
	if (low != null) return high == null ? `dès ${thousands(low)}` : thousands(low);
	if (high != null) return `jusqu’à ${thousands(high)}`;
	return '—';
}

export const remoteLabels: Record<string, string> = {
	remote: 'Télétravail complet',
	hybride: 'Hybride',
	'sur site': 'Sur site',
	'': '—'
};
