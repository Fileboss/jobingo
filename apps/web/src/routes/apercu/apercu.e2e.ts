import { expect, test, type Page } from '@playwright/test';
import { FakePreviewApi, fictionalIdentity } from './preview-api.fake.ts';

// Headless Chromium may not display PDFs: these tests check that the preview is requested and
// its state shown. The PDF's content is checked on the backend, its display in real Chrome.

const sheet = (page: Page) => page.getByTitle('Aperçu du CV').first();
const pageCount = (page: Page) =>
	page.getByRole('complementary', { name: 'Aperçu du PDF' }).getByRole('status');

async function open(page: Page, api = new FakePreviewApi()) {
	await api.install(page);
	await page.goto('/apercu');
	return api;
}

test('the preview screen shows the real PDF, with no CSP violation', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (message) => {
		if (message.type() === 'error') errors.push(message.text());
	});
	const api = await open(page);

	await expect(pageCount(page)).toHaveText('1 page');
	await expect(sheet(page)).toHaveAttribute('src', /^blob:/);
	await expect(page.getByRole('link', { name: 'Aperçu' })).toHaveAttribute('aria-current', 'page');
	const download = page.getByRole('link', { name: 'Télécharger le PDF' });
	await expect(download).toHaveAttribute('download', 'cv-alex-moreau.pdf');
	expect(api.pdfRequests).toBe(1);
	expect(errors).toEqual([]);
});

test('unticking an item updates the preview and survives a reload', async ({ page }) => {
	const api = await open(page);
	await expect(pageCount(page)).toHaveText('1 page');
	const python = page.getByRole('checkbox', { name: 'Python' });
	await expect(python).toBeChecked();

	await python.uncheck();

	await expect.poll(() => api.selectionsSent.at(-1)?.excluded_ids).toEqual(['c1']);
	await expect.poll(() => api.pdfRequests).toBe(2);
	await expect(page.getByText('1 sur 2')).toBeVisible();

	await page.reload();
	await expect(page.getByRole('checkbox', { name: 'Python' })).not.toBeChecked();
	await expect(page.getByRole('checkbox', { name: 'PostgreSQL' })).toBeChecked();
});

test('a bullet of an unticked experience keeps its own choice', async ({ page }) => {
	const api = await open(page);
	await page.getByRole('checkbox', { name: /Migration de 120 tâches/ }).uncheck();
	await page.getByRole('checkbox', { name: /Nordlys/ }).uncheck();
	await expect.poll(() => api.selectionsSent.at(-1)?.excluded_ids.toSorted()).toEqual(['b1', 'x1']);

	await page.getByRole('checkbox', { name: /Nordlys/ }).check();
	await expect.poll(() => api.selectionsSent.at(-1)?.excluded_ids).toEqual(['b1']);
	await expect(page.getByRole('checkbox', { name: /Migration de 120 tâches/ })).not.toBeChecked();
	await expect(page.getByRole('checkbox', { name: /Réduction de 40 %/ })).toBeChecked();
});

test('a quick series of ticks renders once, with the last state', async ({ page }) => {
	const api = await open(page);
	await expect(pageCount(page)).toHaveText('1 page');

	await page.getByRole('button', { name: 'Tout décocher : compétences' }).click();
	await page.getByRole('checkbox', { name: 'Voile' }).uncheck();

	await expect.poll(() => api.pdfRequests).toBe(2);
	expect(api.selectionsSent).toHaveLength(1);
	expect(api.selectionsSent[0].excluded_ids.toSorted()).toEqual(['c1', 'c2', 'h1']);
});

test('an option that is unavailable says why, and comes back with its reason gone', async ({
	page
}) => {
	const api = new FakePreviewApi();
	api.hobbies = [];
	await open(page, api);

	const photo = page.getByRole('checkbox', { name: 'Photo' });
	await expect(photo).toBeDisabled();
	await expect(page.getByText('Ajoutez d’abord une photo.')).toBeVisible();
	await expect(page.getByRole('checkbox', { name: 'Loisirs' })).toBeDisabled();
	await expect(page.getByText('Aucun loisir dans le CV.')).toBeVisible();

	api.identity = { ...api.identity, has_photo: true };
	await page.reload();
	await expect(page.getByRole('checkbox', { name: 'Photo' })).toBeEnabled();
	await page.getByRole('checkbox', { name: 'Photo' }).check();
	await expect.poll(() => api.selectionsSent.at(-1)?.options.photo).toBe(true);
});

test('switching off the panel is sent and the preview follows', async ({ page }) => {
	const api = await open(page);
	await expect(pageCount(page)).toHaveText('1 page');

	await page.getByRole('checkbox', { name: 'Panneau latéral' }).uncheck();

	await expect.poll(() => api.selectionsSent.at(-1)?.options.panneau_competences).toBe(false);
	await expect.poll(() => api.pdfRequests).toBe(2);
});

test('a CV over one page can be previewed but not downloaded', async ({ page }) => {
	const api = new FakePreviewApi();
	api.pages = 2;
	await open(page, api);

	await expect(pageCount(page)).toHaveText('2 pages');
	await expect(page.getByTestId('overflow')).toContainText('Le CV fait 2 pages');
	await expect(sheet(page)).toHaveAttribute('src', /^blob:/);
	await expect(page.getByRole('link', { name: 'Télécharger le PDF' })).toBeHidden();
	await expect(page.getByTestId('no-download')).toBeVisible();

	api.pages = 1;
	await page.getByRole('checkbox', { name: 'Python' }).click();
	await expect(pageCount(page)).toHaveText('1 page');
	await expect(page.getByRole('link', { name: 'Télécharger le PDF' })).toBeVisible();
});

test('the summary can be left out of the page', async ({ page }) => {
	const api = await open(page);
	await expect(pageCount(page)).toHaveText('1 page');

	await page.getByRole('checkbox', { name: /Ingénieur backend, huit ans/ }).click();
	await expect.poll(() => api.excluded).toContain('r1');

	await page.reload();
	await expect(
		page.getByRole('checkbox', { name: /Ingénieur backend, huit ans/ })
	).not.toBeChecked();
});

test('selected items cut from the side panel get a warning, even on one page', async ({ page }) => {
	const api = new FakePreviewApi();
	api.missingItems = 37;
	await open(page, api);

	await expect(pageCount(page)).toHaveText('1 page');
	await expect(page.getByTestId('missing-items')).toContainText(
		'37 éléments sélectionnés ne tiennent pas dans le panneau latéral'
	);
	await expect(page.getByTestId('overflow')).toBeHidden();
	await expect(page.getByRole('link', { name: 'Télécharger le PDF' })).toBeVisible();
});

test('a failed preview keeps the last one and the choices, and says so', async ({ page }) => {
	const api = await open(page);
	await expect(sheet(page)).toHaveAttribute('src', /^blob:/);
	const before = await sheet(page).getAttribute('src');

	api.pdfState = 'refused';
	await page.getByRole('checkbox', { name: 'Python' }).uncheck();

	const alert = page.getByRole('alert');
	await expect(alert).toContainText('le moteur de rendu a échoué');
	await expect(sheet(page)).toHaveAttribute('src', before as string);
	await expect(page.getByRole('checkbox', { name: 'Python' })).not.toBeChecked();
	await expect(page.getByRole('link', { name: 'Télécharger le PDF' })).toBeHidden();

	api.pdfState = 'down';
	await alert.getByRole('button', { name: 'Réessayer' }).click();
	await expect(alert).toContainText('Vos choix sont intacts');
	await expect(sheet(page)).toHaveAttribute('src', before as string);

	api.pdfState = 'ok';
	await alert.getByRole('button', { name: 'Réessayer' }).click();
	await expect(page.getByRole('alert')).toBeHidden();
	await expect(pageCount(page)).toHaveText('1 page');
});

test('a missing identity is named, and the preview still works', async ({ page }) => {
	const api = new FakePreviewApi();
	api.identity = { ...api.identity, name: fictionalIdentity.name, email: fictionalIdentity.email };
	await open(page, api);

	await expect(
		page.getByText('Absents du PDF : le téléphone, l’adresse, LinkedIn et GitHub.')
	).toBeVisible();
	await expect(pageCount(page)).toHaveText('1 page');
});

test('a full identity leaves no note', async ({ page }) => {
	const api = new FakePreviewApi();
	api.identity = { ...fictionalIdentity, has_photo: false };
	await open(page, api);

	await expect(pageCount(page)).toHaveText('1 page');
	await expect(page.getByText(/Absents du PDF/)).toBeHidden();
});

test('the screen fits a phone, with no horizontal scroll', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 800 });
	await open(page);
	await expect(pageCount(page)).toHaveText('1 page');

	const width = await page.evaluate(() => document.documentElement.scrollWidth);
	expect(width).toBeLessThanOrEqual(390);
});

test('an empty CV leads to the CV screen and asks for no PDF', async ({ page }) => {
	const api = new FakePreviewApi();
	api.empty = true;
	await open(page, api);

	await expect(page.getByRole('heading', { name: 'Rien à mettre en page' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Remplir mon CV' })).toBeVisible();
	expect(api.pdfRequests).toBe(0);
});
