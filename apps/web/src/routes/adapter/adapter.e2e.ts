import { expect, test, type Page } from '@playwright/test';
import { FakeDraftsApi } from './drafts-api.fake.ts';

async function open(page: Page, path: string, api = new FakeDraftsApi()) {
	await api.install(page);
	await page.goto(path);
	return api;
}

test('pasting an offer asks for a proposal and opens it', async ({ page }) => {
	const api = await open(page, '/adapter');
	await expect(page.getByRole('link', { name: /Ingénieur data plateforme/ })).toBeVisible();
	const propose = page.getByRole('button', { name: 'Proposer un CV pour cette offre' });
	await expect(propose).toBeDisabled();

	await page.getByLabel('Intitulé du poste').fill('Data engineer');
	await page.getByLabel('Entreprise').fill('Lumen');
	await page.getByLabel('Annonce').fill('Airflow et PostgreSQL.');
	await propose.click();

	await expect(page).toHaveURL(/\/adapter\/7$/);
	expect(api.created).toEqual([
		{ title: 'Data engineer', company: 'Lumen', description: 'Airflow et PostgreSQL.' }
	]);
	await expect(page.getByRole('link', { name: 'Voir l’appel #42' })).toHaveAttribute(
		'href',
		'/suivi/appels/42'
	);
});

test('a refused proposal says why and keeps the offer typed', async ({ page }) => {
	const api = new FakeDraftsApi();
	api.createState = 'no-key';
	await open(page, '/adapter', api);
	await page.getByLabel('Intitulé du poste').fill('Data engineer');
	await page.getByLabel('Annonce').fill('Airflow.');
	await page.getByRole('button', { name: 'Proposer un CV pour cette offre' }).click();

	await expect(page.getByRole('alert')).toContainText('ANTHROPIC_API_KEY');
	await expect(page.getByLabel('Annonce')).toHaveValue('Airflow.');
});

test('the review shows what the model did and the user decides', async ({ page }) => {
	const api = await open(page, '/adapter/7');
	await expect(page.getByRole('heading', { name: 'Ingénieur data plateforme' })).toBeVisible();
	await expect(page.getByText('Reformulé par le modèle.')).toBeVisible();
	await expect(page.getByText('Reformulation refusée')).toBeVisible();
	await expect(page.getByText('Écarté par le modèle :')).toBeVisible();
	await expect.poll(() => api.pdfRequests).toBe(1);

	await page.getByRole('button', { name: 'Utiliser quand même' }).click();
	await expect
		.poll(() => api.choicesSent.at(-1)?.texts['nordlys-02'])
		.toBe('Réduction de 60 % du coût de l’entrepôt');
	await expect(page.getByText('adoptée par vous')).toBeVisible();

	await page.getByRole('checkbox', { name: /Colibri Conseil/ }).check();
	await expect.poll(() => api.choicesSent.at(-1)?.kept_ids).toContain('colibri');
	await expect(page.getByText('ajouté par vous')).toBeVisible();
	await expect.poll(() => api.pdfRequests).toBeGreaterThanOrEqual(3);
});

test('a line can be rewritten by hand', async ({ page }) => {
	const api = await open(page, '/adapter/7');
	await page.getByRole('button', { name: 'Modifier : Python' }).click();
	await page.getByLabel('Texte de la ligne').fill('Python 3.12');
	await page.getByRole('button', { name: 'Valider' }).click();

	await expect.poll(() => api.choicesSent.at(-1)?.texts['skill-python']).toBe('Python 3.12');
	await expect(page.getByText('Votre texte.')).toBeVisible();
});

test('an unknown draft says so', async ({ page }) => {
	await open(page, '/adapter/99');
	await expect(page.getByText('Ce CV adapté n’existe pas.')).toBeVisible();
});

for (const path of ['/adapter', '/adapter/7']) {
	test(`${path} fits a phone, with no horizontal scroll`, async ({ page }) => {
		await page.setViewportSize({ width: 390, height: 800 });
		await open(page, path);
		await expect(page.getByText('Ingénieur data plateforme').first()).toBeVisible();
		const width = await page.evaluate(() => document.documentElement.scrollWidth);
		expect(width).toBeLessThanOrEqual(390);
	});
}
