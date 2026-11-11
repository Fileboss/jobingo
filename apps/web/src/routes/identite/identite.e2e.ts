import { expect, test, type Page } from '@playwright/test';
import { FakeIdentityApi, fictionalIdentity, notAnImage, pngFile } from './identity-api.fake.ts';

const save = (page: Page) => page.getByRole('button', { name: 'Enregistrer', exact: true });
const photoInput = (page: Page) => page.getByLabel('Choisir une photo');
const thumbnail = (page: Page) => page.getByRole('img', { name: 'Votre portrait' });

async function open(page: Page) {
	const api = new FakeIdentityApi();
	await api.install(page);
	await page.goto('/identite');
	return api;
}

test('editing the identity then saving survives a reload', async ({ page }) => {
	const api = await open(page);
	await expect(page.getByRole('link', { name: 'Identité' })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await expect(save(page)).toBeDisabled();

	await page.getByLabel('Nom complet').fill(fictionalIdentity.name);
	await page.getByLabel('E-mail').fill(fictionalIdentity.email);
	await expect(page.getByText('Modifications non enregistrées')).toBeVisible();
	await save(page).click();

	await expect(page.getByText('Identité enregistrée')).toBeVisible();
	expect(api.identity.name).toBe(fictionalIdentity.name);

	await page.reload();
	await expect(page.getByLabel('Nom complet')).toHaveValue(fictionalIdentity.name);
	await expect(page.getByLabel('Téléphone')).toHaveValue('');
});

test('the screen fits a phone, with no horizontal scroll', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 800 });
	await open(page);
	await expect(page.getByLabel('Nom complet')).toBeVisible();

	const width = await page.evaluate(() => document.documentElement.scrollWidth);
	expect(width).toBeLessThanOrEqual(390);
});

test('a failed save keeps the input and says so', async ({ page }) => {
	await open(page);
	await page.getByLabel('Nom complet').fill(fictionalIdentity.name);
	await page.route('**/api/identity', (route) => route.abort());

	await save(page).click();

	await expect(page.getByRole('alert')).toContainText('Votre saisie est intacte');
	await expect(page.getByLabel('Nom complet')).toHaveValue(fictionalIdentity.name);
});

test('a photo can be added, then removed', async ({ page }) => {
	const api = await open(page);
	await expect(thumbnail(page)).toBeHidden();

	await photoInput(page).setInputFiles(pngFile);
	await expect(thumbnail(page)).toBeVisible();
	expect(api.identity.has_photo).toBe(true);

	await page.getByRole('button', { name: 'Retirer' }).click();
	await expect(thumbnail(page)).toBeHidden();
	expect(api.identity.has_photo).toBe(false);
});

test('a refused photo shows the server’s message', async ({ page }) => {
	await open(page);

	await photoInput(page).setInputFiles(notAnImage);

	await expect(page.getByRole('alert')).toContainText(
		'Ce fichier n’est pas une image JPEG ou PNG lisible.'
	);
	await expect(thumbnail(page)).toBeHidden();
});
