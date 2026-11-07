import { expect, test, type Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type ObjectivesView = components['schemas']['ObjectivesView'];
type Objectives = components['schemas']['Objectives'];

const defaults: ObjectivesView = {
	objectives: {
		hard_filters: {
			contracts: [],
			remote: [],
			locations: [],
			salary_min_eur: null,
			excluded_keywords: [],
			excluded_companies: []
		},
		weights: { mission: 1, stack: 1, salary: 1, culture: 1 },
		preferences: ''
	},
	updated_at: null,
	offers: [
		{
			offer_id: 1,
			title: 'Ingénieur backend senior',
			company_name: 'Stratus',
			passed: true,
			eliminated_by: [],
			unknown: []
		},
		{
			offer_id: 2,
			title: 'Ingénieur plateforme',
			company_name: 'Voltéo',
			passed: true,
			eliminated_by: [],
			unknown: []
		}
	]
};

async function open(page: Page) {
	const sent: Objectives[] = [];
	await page.route('**/api/objectives', async (route) => {
		if (route.request().method() === 'PUT') {
			const body = route.request().postDataJSON() as Objectives;
			sent.push(body);
			const minimum = body.hard_filters?.salary_min_eur ?? null;
			return route.fulfill({
				json: {
					objectives: body,
					updated_at: '2026-11-07T09:00:00Z',
					offers: defaults.offers.map((offer) =>
						offer.offer_id === 2 && minimum !== null
							? { ...offer, passed: false, eliminated_by: ['salaire sous 55 000 €'] }
							: offer
					)
				}
			});
		}
		return route.fulfill({ json: defaults });
	});
	await page.goto('/objectifs');
	return sent;
}

test('saving the filters shows the offers they keep and drop', async ({ page }) => {
	const sent = await open(page);
	await expect(page.getByText('Jamais enregistrés : rien n’est filtré.')).toBeVisible();
	await expect(page.getByText('2 sur 2 passent.')).toBeVisible();
	const save = page.getByRole('button', { name: 'Enregistrer' });
	await expect(save).toBeDisabled();

	await page.getByRole('checkbox', { name: 'CDI' }).check();
	await page.getByLabel('Salaire minimum').fill('55000');
	await page.getByLabel('Lieux').fill('Lyon, Villeurbanne ,');
	await expect(page.getByText('Modifications non enregistrées.')).toBeVisible();
	await save.click();

	await expect(page.getByText('1 sur 2 passent.')).toBeVisible();
	await expect(page.getByText('salaire sous 55 000 €')).toBeVisible();
	expect(sent.at(-1)?.hard_filters).toMatchObject({
		contracts: ['CDI'],
		salary_min_eur: 55000,
		locations: ['Lyon', 'Villeurbanne']
	});
	await expect(save).toBeDisabled();
});

test('clearing the salary sends no minimum', async ({ page }) => {
	const sent = await open(page);
	await page.getByLabel('Salaire minimum').fill('55000');
	await page.getByLabel('Salaire minimum').fill('');
	await page.getByRole('checkbox', { name: 'CDD' }).check();
	await page.getByRole('button', { name: 'Enregistrer' }).click();
	await expect.poll(() => sent.length).toBe(1);
	expect(sent[0].hard_filters?.salary_min_eur).toBeNull();
});

test('the screen fits a phone, with no horizontal scroll', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 800 });
	await open(page);
	await expect(page.getByText('Ingénieur backend senior')).toBeVisible();
	const width = await page.evaluate(() => document.documentElement.scrollWidth);
	expect(width).toBeLessThanOrEqual(390);
});
