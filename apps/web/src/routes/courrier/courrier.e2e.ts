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
		'3 nouveaux messages · 1 classé · 1 masqué · 2 offres lues, dont 1 notée.'
	);
	await expect(page.getByText(/Dernière lecture le/)).toBeVisible();
	expect(api.syncRequests).toBe(1);

	await page.getByRole('button', { name: 'Alertes' }).click();
	await expect(page.getByRole('link', { name: 'Votre candidature chez Voltéo' })).toHaveCount(0);
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

test('a refusal is tied to its application, then confirmed by a click', async ({ page }) => {
	const api = new FakeMailApi();
	await api.install(page);
	await page.goto('/courrier');
	await page.getByRole('button', { name: 'Synchroniser' }).click();

	await page.getByRole('button', { name: /À traiter/ }).click();
	await expect(page.getByText('À confirmer')).toBeVisible();
	await page.getByRole('link', { name: 'Votre candidature chez Voltéo' }).click();

	await expect(page.getByTestId('message-body')).toContainText('ne donnerons pas suite');
	await expect(page.getByText('Voltéo ne donne pas suite')).toBeVisible();
	await expect(page.getByRole('heading', { name: 'Suggestion : Refus' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Confirmer' })).toBeDisabled();

	await page.getByLabel('Rattacher à').selectOption({ label: 'Data engineer · Voltéo' });
	await page.getByRole('button', { name: 'Enregistrer' }).click();
	await expect(page.getByRole('link', { name: 'Data engineer' })).toBeVisible();
	await expect(page.getByText('Rattaché par vous.')).toBeVisible();

	await page.getByRole('button', { name: 'Confirmer' }).click();
	await expect(page.getByText('Confirmée : ajoutée à la chronologie.')).toBeVisible();
	expect(api.decisions).toEqual(['PUT application', 'POST suggestion/accept']);
});

test('a newsletter is hidden without the model, and can be restored', async ({ page }) => {
	const api = new FakeMailApi();
	await api.install(page);
	await page.goto('/courrier');
	await page.getByRole('button', { name: 'Synchroniser' }).click();
	await expect(page.getByRole('link', { name: 'Les nouvelles de la semaine' })).toHaveCount(0);

	await page.getByRole('button', { name: /Masqués/ }).click();
	await page.getByRole('link', { name: 'Les nouvelles de la semaine' }).click();

	await expect(
		page.getByText('Lettre d’information : masquée sans passer par l’IA.')
	).toBeVisible();
	await page.getByRole('button', { name: 'Restaurer' }).click();
	await expect(page.getByRole('button', { name: 'Bloquer l’expéditeur' })).toBeVisible();
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
	await expect(page.getByRole('link', { name: 'Votre candidature chez Voltéo' })).toBeVisible();
	const width = await page.evaluate(() => document.documentElement.scrollWidth);
	expect(width).toBeLessThanOrEqual(390);
});
