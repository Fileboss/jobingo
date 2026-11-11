import { expect, test, type Page } from '@playwright/test';
import { FakeCvApi, fictionalCv } from './cv-api.fake.ts';

const textMode = (page: Page) => page.getByRole('button', { name: 'Texte', exact: true });
const formMode = (page: Page) => page.getByRole('button', { name: 'Fiches', exact: true });
const textEditor = (page: Page) => page.getByRole('textbox', { name: 'Texte du CV' });
const resume = (page: Page) => page.getByRole('textbox', { name: 'Résumé' });
const save = (page: Page) => page.getByRole('button', { name: 'Enregistrer', exact: true });

async function open(page: Page, stored: string | null = fictionalCv) {
	const api = new FakeCvApi();
	if (stored) api.store(stored);
	await api.install(page);
	await page.goto('/cv');
	return api;
}

test('the home leads to the CV, with no CSP violation', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (message) => {
		if (message.type() === 'error') errors.push(message.text());
	});
	await new FakeCvApi().install(page);

	await page.goto('/');

	await expect(page).toHaveURL(/\/cv$/);
	await expect(page.getByRole('heading', { level: 1, name: 'Mon CV' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Mon CV' })).toHaveAttribute('aria-current', 'page');
	expect(errors).toEqual([]);
});

test('a new account sees an inviting empty state, then can write', async ({ page }) => {
	await open(page, null);

	await expect(page.getByRole('heading', { name: 'Un classeur neuf' })).toBeVisible();
	await expect(save(page)).toBeHidden();

	await page.getByRole('button', { name: 'Remplir les fiches' }).click();
	await expect(resume(page)).toBeVisible();
	await expect(save(page)).toBeDisabled();
});

test('the page says so when the API is down, and offers a retry', async ({ page }) => {
	const api = new FakeCvApi();
	api.failing = true;
	await api.install(page);

	await page.goto('/cv');
	await expect(page.getByRole('alert')).toContainText('Le serveur ne répond pas');

	api.failing = false;
	await page.getByRole('button', { name: 'Réessayer' }).click();
	await expect(page.getByRole('heading', { name: 'Un classeur neuf' })).toBeVisible();
});

test('typing in the form then saving survives a reload', async ({ page }) => {
	await open(page);

	await resume(page).fill('Ingénieure données, dix ans de métier.');
	await expect(page.getByText('Modifications non enregistrées')).toBeVisible();
	await save(page).click();

	await expect(page.getByText(/Version 2, enregistrée/)).toBeVisible();
	await page.reload();
	await expect(resume(page)).toHaveValue('Ingénieure données, dix ans de métier.');
});

test('a CV waiting for its ids can be saved with no edit', async ({ page }) => {
	const api = new FakeCvApi();
	api.store(fictionalCv);
	api.document = { ...api.document, needs_save: true };
	await api.install(page);
	await page.goto('/cv');

	await expect(page.getByText('attend un enregistrement')).toBeVisible();
	await save(page).click();

	await expect(page.getByText(/Version 2, enregistrée/)).toBeVisible();
});

test('typing in the text mode then saving survives a reload', async ({ page }) => {
	await open(page);
	await textMode(page).click();

	await textEditor(page).fill('## Résumé\n\nÉcrit en texte.\n');
	await save(page).click();
	await expect(page.getByText(/Version 2, enregistrée/)).toBeVisible();

	await page.reload();
	await expect(resume(page)).toHaveValue('Écrit en texte.');
});

test('switching modes keeps unsaved input, both ways', async ({ page }) => {
	await open(page);

	await resume(page).fill('Saisie du formulaire, non enregistrée.');
	await textMode(page).click();
	await expect(textEditor(page)).toHaveValue(/Saisie du formulaire, non enregistrée\./);
	await expect(page.getByText('Modifications non enregistrées')).toBeVisible();

	await textEditor(page).fill('## Résumé\n\nSaisie du texte, non enregistrée.\n');
	await formMode(page).click();
	await expect(resume(page)).toHaveValue('Saisie du texte, non enregistrée.');
	await expect(page.getByText('Modifications non enregistrées')).toBeVisible();
});

test('a failed switch keeps the mode and the input', async ({ page }) => {
	const api = await open(page);

	await resume(page).fill('Ne pas perdre ceci.');
	api.failing = true;
	await textMode(page).click();

	await expect(page.getByRole('alert')).toContainText('Votre saisie est intacte');
	await expect(resume(page)).toHaveValue('Ne pas perdre ceci.');
});

test('personal data is flagged without blocking the save', async ({ page }) => {
	await open(page);

	await resume(page).fill('Écrivez-moi : alex.moreau@example.fr');
	await expect(
		page.getByText('Adresse e-mail détectée : « alex.moreau@example.fr »')
	).toBeVisible();

	await save(page).click();
	await expect(page.getByText(/Version 2, enregistrée/)).toBeVisible();
});

test('a save over a change made elsewhere is explained, and overwrites only on request', async ({
	page
}) => {
	const api = await open(page);

	await resume(page).fill('Ma saisie.');
	api.store(fictionalCv.replace('huit ans', 'neuf ans'));
	await save(page).click();

	const alert = page.getByRole('alert');
	await expect(alert).toContainText('modifié ailleurs');
	await expect(alert).toContainText('version 2');
	await expect(resume(page)).toHaveValue('Ma saisie.');
	expect(api.document.version).toBe(2);

	await page.getByRole('button', { name: 'Remplacer par ma saisie' }).click();
	await expect(page.getByRole('alert')).toBeHidden();
	await expect(page.getByText(/Version 3, enregistrée/)).toBeVisible();
	expect(api.document.text).toContain('Ma saisie.');
});

test('in a conflict the user can drop their input for the stored version', async ({ page }) => {
	const api = await open(page);

	await resume(page).fill('Ma saisie.');
	api.store(fictionalCv.replace('huit ans', 'neuf ans'));
	await save(page).click();

	await page.getByRole('button', { name: 'Abandonner ma saisie' }).click();
	await expect(resume(page)).toHaveValue(/neuf ans/);
	await expect(page.getByRole('alert')).toBeHidden();
});

test('every ruled field keeps its text on the rules, a kept block in monospace too', async ({
	page
}) => {
	const api = new FakeCvApi();
	api.store(fictionalCv);
	api.document.fields.others = ['## Notes pour l’oral\n\n- Une réponse à garder.'];
	await api.install(page);
	await page.goto('/cv');
	await expect(page.getByRole('textbox', { name: 'Bloc conservé 1' })).toBeVisible();

	const heights = await page
		.locator('textarea.ruled')
		.evaluateAll((areas) => areas.map((area) => getComputedStyle(area).lineHeight));
	expect(heights.length).toBeGreaterThan(3);
	expect(new Set(heights)).toEqual(new Set(['32px']));
});
