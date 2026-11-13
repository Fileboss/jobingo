import type { components } from '#lib/api/schema.d.ts';

export type Offer = components['schemas']['Offer'];
export type ScoredOffer = components['schemas']['ScoredOffer'];
export type OfferScore = components['schemas']['OfferScore'];

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

/** Where an offer stands: the user's decision first, then what scoring found. */
export function standing(
	offer: ScoredOffer
): 'applied' | 'shortlisted' | 'dismissed' | 'filtered' | 'open' {
	if (offer.application_id) return 'applied';
	if (offer.decision) return offer.decision;
	if (offer.state === 'filtered') return 'filtered';
	return 'open';
}

/** What the « Salaire » column sorts on: the top of the range, as the objectives read it. */
export function salarySortValue(offer: Pick<Offer, 'salary_min' | 'salary_max'>): number | null {
	return offer.salary_max ?? offer.salary_min ?? null;
}
