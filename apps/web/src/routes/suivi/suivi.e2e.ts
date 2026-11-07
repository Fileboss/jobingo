import { expect, test, type Page } from '@playwright/test';
import { FakeObservabilityApi } from './observability-api.fake.ts';

async function open(page: Page, path: string, api = new FakeObservabilityApi()) {
	await api.install(page);
	await page.goto(path);
	return api;
}

test('usage shows the measured figures, with no CSP violation', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (message) => {
		if (message.type() === 'error') errors.push(message.text());
	});
	const api = await open(page, '/suivi');

	await expect(page.getByText('0,0005 $').first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'Suivi de l’IA' })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await expect(page.getByRole('meter', { name: 'Aujourd’hui' })).toBeVisible();
	await expect(page.getByRole('img', { name: /Coût par jour/ })).toBeVisible();
	await expect(page.getByRole('link', { name: 'score_offer' })).toHaveAttribute(
		'href',
		'/suivi/appels?task=score_offer'
	);

	await page.getByRole('button', { name: '7 jours' }).click();
	await expect.poll(() => api.usageDays.at(-1)).toBe(7);
	expect(errors).toEqual([]);
});

test('with no call, usage says nothing is measured yet', async ({ page }) => {
	const api = new FakeObservabilityApi();
	api.measured = false;
	await open(page, '/suivi', api);

	await expect(page.getByText('Pas encore mesuré')).toBeVisible();
	await expect(page.getByRole('img', { name: /Coût par jour/ })).toHaveCount(0);
});

test('calls filter by status through the URL, and open their detail', async ({ page }) => {
	const api = await open(page, '/suivi/appels');
	await expect(page.getByRole('row')).toHaveCount(4);

	await page.getByLabel('Statut').selectOption('failed');

	await expect(page).toHaveURL(/status=failed/);
	await expect(page.getByRole('row')).toHaveCount(2);
	expect(api.callQueries.at(-1)?.get('status')).toBe('failed');
	expect(api.callQueries.at(-1)?.has('task')).toBe(false);

	await page.goto('/suivi/appels');
	await page.getByRole('link', { name: '#3' }).click();
	await expect(page.getByRole('heading', { name: /Appel #3/ })).toBeVisible();
	await expect(page.getByText('<offre>Développeuse Python, Nantes</offre>')).toBeVisible();
	await expect(page.getByText('offer.scored')).toBeVisible();
});

test('an unknown call says so', async ({ page }) => {
	await open(page, '/suivi/appels/99');
	await expect(page.getByText('Cet appel n’existe pas.')).toBeVisible();
});

test('the journal search keeps what is typed while it loads', async ({ page }) => {
	const api = await open(page, '/suivi/journal');
	await expect(page.getByText('sync.failed')).toBeVisible();
	const search = page.getByLabel('Rechercher');

	await search.pressSequentially('offer', { delay: 20 });
	await expect.poll(() => api.eventQueries.at(-1)?.get('q')).toBe('offer');
	await search.pressSequentially('.scored', { delay: 20 });

	await expect.poll(() => api.eventQueries.at(-1)?.get('q')).toBe('offer.scored');
	await expect(search).toBeFocused();
	await expect(search).toHaveValue('offer.scored');
	await expect(page.getByText('sync.failed')).toHaveCount(0);
	await expect(page.getByRole('link', { name: 'appel #3' })).toHaveAttribute(
		'href',
		'/suivi/appels/3'
	);
});

for (const path of ['/suivi', '/suivi/appels', '/suivi/journal', '/suivi/appels/3']) {
	test(`${path} fits a phone, with no horizontal scroll`, async ({ page }) => {
		await page.setViewportSize({ width: 390, height: 800 });
		await open(page, path);
		await expect(page.getByRole('status')).toHaveCount(0);

		const width = await page.evaluate(() => document.documentElement.scrollWidth);
		expect(width).toBeLessThanOrEqual(390);
	});
}
