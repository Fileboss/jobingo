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
	await expect(page.getByRole('cell', { name: 'Développeur Python' })).toBeVisible();
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

test('an offer shows its details and its call, and adapts no CV', async ({ page }) => {
	await open(page, '/offres/1');
	await expect(page.getByRole('heading', { name: 'Ingénieur backend senior' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'l’appel #12' })).toHaveAttribute(
		'href',
		'/suivi/appels/12'
	);
	await expect(page.getByRole('link', { name: 'Voir l’annonce d’origine' })).toHaveAttribute(
		'rel',
		'noopener noreferrer'
	);

	// An adapted CV belongs to an application: it is made from there.
	await expect(page.getByRole('button', { name: 'Adapter mon CV' })).toHaveCount(0);
	await expect(page.getByText('Le CV adapté et la lettre se font')).toBeVisible();
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

test('every offer is in one table, sorted by score, with its status', async ({ page }) => {
	const api = await open(page, '/offres');
	await page.getByLabel('Texte des offres').fill('Des offres');
	await page.getByRole('button', { name: 'Extraire les offres' }).click();
	await expect(page.getByText('2 offres ajoutées.')).toBeVisible();

	const titles = page.locator('tbody tr td:nth-child(3) a');
	await expect(titles).toHaveText([
		'Développeur Python',
		'Ingénieur backend senior',
		'Ingénieur plateforme',
		'Développeur Java'
	]);
	const statuses = page.locator('tbody tr td:nth-child(2)');
	await expect(statuses.last()).toHaveText('Filtrée');
	await expect(statuses.first()).toHaveText('À examiner');
	await expect(page.getByRole('button', { name: 'Écartées' })).toHaveCount(0);
	expect(api.texts).toHaveLength(1);
});

test('an offer applied to links to its application', async ({ page }) => {
	const api = new FakeOffersApi();
	api.offers[0] = { ...api.offers[0], application_id: 5 };
	await open(page, '/offres', api);
	await expect(page.getByRole('link', { name: 'Candidature →' })).toHaveAttribute(
		'href',
		'/candidatures/5'
	);
});

test('stale scores are counted and scored again on request', async ({ page }) => {
	const api = new FakeOffersApi();
	api.stale = 2;
	await open(page, '/offres', api);
	await expect(page.getByText('2 offres à noter')).toBeVisible();
	await page.getByRole('button', { name: 'Noter maintenant' }).click();
	await expect(page.getByText('à noter')).toHaveCount(0);
	expect(api.rescoreRequests).toBe(1);
});

test('an offer shows how its score was computed, and the user decides', async ({ page }) => {
	const api = await open(page, '/offres/1');
	await expect(page.getByText('78/100')).toBeVisible();
	await expect(page.getByText('Kubernetes peu pratiqué')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Voir l’appel #21' })).toBeVisible();

	await page.getByRole('button', { name: 'Retenir' }).click();
	await expect(page.getByText('Retenue par vous.')).toBeVisible();
	await page.getByRole('button', { name: 'Annuler' }).click();
	await expect(page.getByRole('button', { name: 'Retenir' })).toBeVisible();
	expect(api.decisions).toEqual(['shortlisted', null]);

	await page.getByRole('button', { name: 'Noter à nouveau' }).click();
	await expect(page.getByText('64/100')).toBeVisible();
	expect(api.scoreRequests).toBe(1);
});

test('a filtered offer says which filter, with no call', async ({ page }) => {
	await open(page, '/offres/4');
	await expect(page.getByText('Écartée par vos filtres, sans appel au modèle.')).toBeVisible();
	await expect(page.getByText('contrat non retenu : CDD')).toBeVisible();
});
