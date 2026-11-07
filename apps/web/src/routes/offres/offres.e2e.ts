import { expect, test, type Page } from '@playwright/test';
import { FakeOffersApi } from './offers-api.fake.ts';

async function open(page: Page, path: string, api = new FakeOffersApi()) {
	await api.install(page);
	await page.goto(path);
	return api;
}

test('pasted text becomes offers in the list', async ({ page }) => {
	const api = await open(page, '/offres');
	await expect(page.getByRole('link', { name: 'Ingénieur backend senior' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Offres' })).toHaveAttribute('aria-current', 'page');

	await page.getByLabel('Texte des offres').fill('Nouvelles offres pour vous : …');
	await page.getByRole('button', { name: 'Extraire les offres' }).click();

	await expect(page.getByText('2 offres ajoutées.')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Développeur Python' })).toBeVisible();
	await expect(page.getByLabel('Texte des offres')).toHaveValue('');
	expect(api.texts).toEqual(['Nouvelles offres pour vous : …']);
	await expect(page.getByText('60 k€ – 70 k€').first()).toBeVisible();
});

test('a known offer is said to be completed', async ({ page }) => {
	const api = new FakeOffersApi();
	api.intakeAnswer = 'merged';
	await open(page, '/offres', api);
	await page.getByLabel('Texte des offres').fill('Ingénieur backend senior — Stratus');
	await page.getByRole('button', { name: 'Extraire les offres' }).click();
	await expect(page.getByText('1 déjà connue, complétée.')).toBeVisible();
});

test('a text without offer says so and keeps the text', async ({ page }) => {
	const api = new FakeOffersApi();
	api.intakeAnswer = 'none';
	await open(page, '/offres', api);
	await page.getByLabel('Texte des offres').fill('Bonjour');
	await page.getByRole('button', { name: 'Extraire les offres' }).click();
	await expect(page.getByRole('alert')).toContainText('Aucune offre');
	await expect(page.getByLabel('Texte des offres')).toHaveValue('Bonjour');
});

test('an offer shows its details, its call and a way to adapt the CV', async ({ page }) => {
	const api = await open(page, '/offres/1');
	await expect(page.getByRole('heading', { name: 'Ingénieur backend senior' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'l’appel #12' })).toHaveAttribute(
		'href',
		'/suivi/appels/12'
	);
	await expect(page.getByRole('link', { name: 'Voir l’annonce d’origine' })).toHaveAttribute(
		'rel',
		'noopener noreferrer'
	);

	await page.getByRole('button', { name: 'Adapter mon CV' }).click();
	await expect(page.getByRole('alert')).toContainText('ANTHROPIC_API_KEY');
	expect(api.adaptRequests).toBe(1);
});

test('an unknown offer says so', async ({ page }) => {
	await open(page, '/offres/99');
	await expect(page.getByText('Cette offre n’existe pas.')).toBeVisible();
});

for (const path of ['/offres', '/offres/1']) {
	test(`${path} fits a phone, with no horizontal scroll`, async ({ page }) => {
		await page.setViewportSize({ width: 390, height: 800 });
		await open(page, path);
		await expect(page.getByText('Ingénieur backend senior').first()).toBeVisible();
		const width = await page.evaluate(() => document.documentElement.scrollWidth);
		expect(width).toBeLessThanOrEqual(390);
	});
}
