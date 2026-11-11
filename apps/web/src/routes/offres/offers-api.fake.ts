import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type Offer = Schemas['ScoredOffer'];
type OfferScore = Schemas['OfferScore'];

export const offer = (id: number, title: string, extra: Partial<Offer> = {}): Offer => ({
	id,
	title,
	company_name: 'Stratus',
	locations: ['Lyon'],
	contract: 'CDI',
	remote: 'hybride',
	salary_min: 60000,
	salary_max: 70000,
	url: 'https://stratus.example/jobs/12',
	description_md: 'Vous concevrez les API de notre produit.',
	llm_call_id: 12,
	message_id: null,
	state: 'scored',
	decision: null,
	created_at: '2026-11-07T09:00:00Z',
	updated_at: '2026-11-07T09:00:00Z',
	current_score: score(id, 78),
	...extra
});

export const score = (
	offerId: number,
	value: number,
	extra: Partial<OfferScore> = {}
): OfferScore => ({
	id: offerId * 10,
	offer_id: offerId,
	passed_filters: true,
	eliminated_by: [],
	unknown: [],
	criteria: { mission: 8, stack: 9, salary: 6, culture: 7 },
	fit_score: value,
	salary_score: 60,
	summary: 'Bon accord avec la plateforme de données visée.',
	strengths: ['Airflow et PostgreSQL'],
	gaps: ['Kubernetes peu pratiqué'],
	weights: { mission: 2, stack: 2, culture: 1 },
	llm_call_id: 21,
	created_at: '2026-11-07T09:00:00Z',
	stale: false,
	...extra
});

/** The offers API in memory, for Playwright, with fictional offers. */
export class FakeOffersApi {
	offers: Offer[] = [
		offer(1, 'Ingénieur backend senior'),
		offer(4, 'Développeur Java', {
			company_name: 'Banque Rhône',
			state: 'filtered',
			current_score: score(4, 0, {
				passed_filters: false,
				eliminated_by: ['contrat non retenu : CDD'],
				criteria: null,
				fit_score: null,
				salary_score: null,
				llm_call_id: null
			})
		})
	];
	stale = 0;
	rescoreRequests = 0;
	scoreRequests = 0;
	decisions: (string | null)[] = [];
	texts: string[] = [];
	/** What the next intake answers: new offers, a known one completed, or none. */
	intakeAnswer: 'new' | 'merged' | 'none' = 'new';

	async install(page: Page) {
		await page.route('**/api/offers', (route) => route.fulfill({ json: this.offers }));
		await page.route('**/api/offers/stale', (route) =>
			route.fulfill({ json: { count: this.stale } })
		);
		await page.route('**/api/offers/rescore', (route) => {
			this.rescoreRequests += 1;
			this.stale = 0;
			return route.fulfill({ json: { scored_ids: [1], unscored_ids: [], error: null } });
		});
		await page.route(/\/api\/offers\/\d+\/score$/, (route) => {
			this.scoreRequests += 1;
			const id = Number(route.request().url().split('/').at(-2));
			const found = this.offers.find((o) => o.id === id)!;
			found.current_score = score(id, 64);
			return route.fulfill({ json: found });
		});
		await page.route(/\/api\/offers\/\d+\/decision$/, (route) => {
			const id = Number(route.request().url().split('/').at(-2));
			const decision = route.request().postDataJSON().decision;
			this.decisions.push(decision);
			const found = this.offers.find((o) => o.id === id)!;
			found.decision = decision;
			return route.fulfill({ json: found });
		});
		await page.route('**/api/offers/intake', async (route) => {
			this.texts.push(route.request().postDataJSON().text);
			if (this.intakeAnswer === 'none') {
				return route.fulfill({
					status: 422,
					json: { message: 'Aucune offre d’emploi n’a été trouvée dans ce texte.' }
				});
			}
			if (this.intakeAnswer === 'merged') {
				return route.fulfill({
					status: 201,
					json: {
						offers: [this.offers[0]],
						merged_ids: [1],
						llm_call_id: 13,
						unscored_ids: [],
						scoring_error: null
					}
				});
			}
			const added = [
				offer(2, 'Développeur Python', {
					company_name: 'Agrimetrics',
					salary_min: null,
					salary_max: null,
					current_score: score(2, 91)
				}),
				offer(3, 'Ingénieur plateforme', {
					company_name: 'Voltéo',
					current_score: score(3, 40)
				})
			];
			this.offers = [...added, ...this.offers];
			await route.fulfill({
				status: 201,
				json: {
					offers: added,
					merged_ids: [],
					llm_call_id: 13,
					unscored_ids: [],
					scoring_error: null
				}
			});
		});
		await page.route(/\/api\/offers\/\d+$/, (route) => {
			const id = Number(route.request().url().split('/').at(-1));
			const found = this.offers.find((o) => o.id === id);
			if (!found) return route.fulfill({ status: 404, json: { detail: 'Offre introuvable' } });
			return route.fulfill({ json: { ...found, application_id: null } });
		});
	}
}
