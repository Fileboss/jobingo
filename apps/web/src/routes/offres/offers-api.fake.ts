import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type Offer = Schemas['Offer'];

const offer = (id: number, title: string, extra: Partial<Offer> = {}): Offer => ({
	id,
	title,
	company_name: 'Stratus',
	location: 'Lyon',
	contract: 'CDI',
	remote: 'hybride',
	salary_min: 60000,
	salary_max: 70000,
	url: 'https://stratus.example/jobs/12',
	description_md: 'Vous concevrez les API de notre produit.',
	llm_call_id: 12,
	created_at: '2026-11-07T09:00:00Z',
	updated_at: '2026-11-07T09:00:00Z',
	...extra
});

/** The offers API in memory, for Playwright, with fictional offers. */
export class FakeOffersApi {
	offers: Offer[] = [offer(1, 'Ingénieur backend senior')];
	texts: string[] = [];
	adaptRequests = 0;
	/** What the next intake answers: new offers, a known one completed, or none. */
	intakeAnswer: 'new' | 'merged' | 'none' = 'new';

	async install(page: Page) {
		await page.route('**/api/offers', (route) => route.fulfill({ json: this.offers }));
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
					json: { offers: [this.offers[0]], merged_ids: [1], llm_call_id: 13 }
				});
			}
			const added = [
				offer(2, 'Développeur Python', {
					company_name: 'Agrimetrics',
					salary_min: null,
					salary_max: null
				}),
				offer(3, 'Ingénieur plateforme', { company_name: 'Voltéo', contract: 'CDD' })
			];
			this.offers = [...added, ...this.offers];
			await route.fulfill({
				status: 201,
				json: { offers: added, merged_ids: [], llm_call_id: 13 }
			});
		});
		await page.route(/\/api\/offers\/\d+$/, (route) => {
			const id = Number(route.request().url().split('/').at(-1));
			const found = this.offers.find((o) => o.id === id);
			if (!found) return route.fulfill({ status: 404, json: { detail: 'Offre introuvable' } });
			return route.fulfill({ json: { ...found, drafts: [] } });
		});
		await page.route(/\/api\/offers\/\d+\/cv-drafts\/fr$/, (route) => {
			this.adaptRequests += 1;
			return route.fulfill({
				status: 503,
				json: { message: 'L’IA n’est pas configurée : renseignez ANTHROPIC_API_KEY.' }
			});
		});
	}
}
