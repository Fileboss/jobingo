import { expect, test } from '@playwright/test';
import { FakeMailApi } from './mail-api.fake.ts';

test('a sync reads the mailbox and an alert leads to its offers', async ({ page }) => {
	const api = new FakeMailApi();
	await api.install(page);
	await page.goto('/courrier');
	await expect(page.getByRole('link', { name: 'Courrier' })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await expect(page.getByText('Aucun message pour l’instant')).toBeVisible();
	await expect(page.getByText('Serveur local de démonstration')).toBeVisible();
	await expect(page.getByText('Jamais lue.')).toBeVisible();

	await page.getByRole('button', { name: 'Synchroniser' }).click();

	await expect(page.getByRole('status')).toHaveText(
		'2 nouveaux messages · 2 offres lues, dont 1 notée.'
	);
	await expect(page.getByText(/Dernière lecture le/)).toBeVisible();
	expect(api.syncRequests).toBe(1);

	await page.getByRole('button', { name: 'Alertes' }).click();
	await expect(page.getByRole('link', { name: 'Votre profil nous intéresse' })).toHaveCount(0);
	await page.getByRole('link', { name: 'Nouvelles offres pour « python »' }).click();

	await expect(page.getByRole('heading', { name: 'Offres lues' })).toBeVisible();
	await expect(page.getByText('non notée')).toBeVisible();
	await page.getByRole('link', { name: 'Ingénieur logiciel Python' }).click();
	await expect(page).toHaveURL(/\/offres\/5$/);
});

test('an unreachable mailbox is said', async ({ page }) => {
	const api = new FakeMailApi();
	api.syncAnswer = 'unreachable';
	await api.install(page);
	await page.goto('/courrier');
	await page.getByRole('button', { name: 'Synchroniser' }).click();
	await expect(page.getByRole('alert')).toContainText('injoignable');
});

test('a message shows its text, never its HTML', async ({ page }) => {
	const api = new FakeMailApi();
	api.messages = [];
	await api.install(page);
	await page.goto('/courrier');
	await page.getByRole('button', { name: 'Synchroniser' }).click();
	await page.getByRole('link', { name: 'Votre profil nous intéresse' }).click();
	await expect(page.getByTestId('message-body')).toContainText('seriez-vous disponible');
	await expect(page.getByText('pas encore trié')).toBeVisible();
});

test('an unknown message says so', async ({ page }) => {
	await new FakeMailApi().install(page);
	await page.goto('/courrier/99');
	await expect(page.getByText('Ce message n’existe pas.')).toBeVisible();
});

test('/courrier fits a phone, with no horizontal scroll', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 800 });
	await new FakeMailApi().install(page);
	await page.goto('/courrier');
	await page.getByRole('button', { name: 'Synchroniser' }).click();
	await expect(page.getByRole('link', { name: 'Votre profil nous intéresse' })).toBeVisible();
	const width = await page.evaluate(() => document.documentElement.scrollWidth);
	expect(width).toBeLessThanOrEqual(390);
});
