import { expect, test } from '@playwright/test';

test('the page shows the account from the API, with no CSP violation', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (message) => {
		if (message.type() === 'error') errors.push(message.text());
	});
	await page.route('/api/me', (route) => route.fulfill({ json: { id: 1, username: 'alex' } }));

	await page.goto('/');

	await expect(page.getByRole('heading', { level: 1, name: 'Jobingo' })).toBeVisible();
	await expect(page.getByText('Compte : alex')).toBeVisible();
	expect(errors).toEqual([]);
});

test('the page says so when the API is down', async ({ page }) => {
	await page.route('/api/me', (route) => route.abort());

	await page.goto('/');

	await expect(page.getByRole('alert')).toHaveText('Serveur indisponible');
});
