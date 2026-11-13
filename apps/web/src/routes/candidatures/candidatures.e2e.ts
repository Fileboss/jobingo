import { expect, test, type Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type ApplicationView = Schemas['ApplicationView'];
type ApplicationEvent = Schemas['ApplicationEvent'];

/** The applications API in memory, deriving the status the way the server does for
 * these cases: the latest significant event sets it. */
class FakeApplicationsApi {
	nextEvent = 1;
	application: ApplicationView = {
		id: 5,
		offer_id: 2,
		title: 'Développeur Python',
		company_name: 'Agrimetrics',
		status: 'a_postuler',
		tone: 'todo',
		last_event: null,
		follow_up_on: null,
		created_at: '2026-11-01T09:00:00Z',
		rating: null,
		fit_score: null,
		salary_score: null,
		salary_min: null,
		salary_max: null,
		contact: { name: '', email: '', phone: '' },
		company_notes: '',
		events: [],
		messages: []
	};
	created: Schemas['NewApplication'][] = [];
	adaptRequests = 0;

	#refresh() {
		const events = [...this.application.events].sort((a, b) =>
			b.occurred_at.localeCompare(a.occurred_at)
		);
		const latest = events.find((e) => e.type !== 'note');
		const status =
			latest?.type === 'applied'
				? 'postule'
				: latest?.type === 'interview_scheduled'
					? 'entretien'
					: 'a_postuler';
		this.application = {
			...this.application,
			events,
			status,
			tone: status === 'a_postuler' ? 'todo' : 'active',
			last_event: events[0] ?? null,
			follow_up_on: latest?.type === 'applied' ? '2026-11-08' : null
		};
	}

	async install(page: Page) {
		await page.route('**/api/applications', async (route) => {
			if (route.request().method() === 'POST') {
				this.created.push(route.request().postDataJSON());
				return route.fulfill({ status: 201, json: this.application });
			}
			return route.fulfill({ json: [this.application] });
		});
		await page.route(/\/api\/applications\/\d+\/letters$/, (route) => route.fulfill({ json: [] }));
		await page.route(/\/api\/applications\/\d+\/cv-drafts$/, (route) => {
			if (route.request().method() !== 'POST') return route.fulfill({ json: [] });
			this.adaptRequests += 1;
			return route.fulfill({
				status: 503,
				json: { message: 'L’IA n’est pas configurée : renseignez ANTHROPIC_API_KEY.' }
			});
		});
		await page.route(/\/api\/applications\/\d+$/, (route) =>
			route.fulfill({ json: this.application })
		);
		await page.route(/\/api\/applications\/\d+\/rating$/, (route) => {
			this.application = { ...this.application, rating: route.request().postDataJSON().rating };
			return route.fulfill({ json: this.application });
		});
		await page.route(/\/api\/applications\/\d+\/events$/, (route) => {
			const body = route.request().postDataJSON();
			const added: ApplicationEvent = {
				id: this.nextEvent++,
				type: body.type,
				occurred_at: body.occurred_at,
				note: body.note,
				created_at: '2026-11-07T09:00:00Z'
			};
			this.application.events = [...this.application.events, added];
			this.#refresh();
			return route.fulfill({ status: 201, json: this.application });
		});
		await page.route(/\/api\/applications\/\d+\/events\/\d+$/, (route) => {
			const id = Number(route.request().url().split('/').at(-1));
			this.application.events = this.application.events.filter((e) => e.id !== id);
			this.#refresh();
			return route.fulfill({ json: this.application });
		});
		await page.route(/\/api\/applications\/\d+\/contact$/, (route) => {
			const body = route.request().postDataJSON();
			if (body.email && !body.email.includes('@')) {
				return route.fulfill({ status: 422, json: { detail: [] } });
			}
			this.application = { ...this.application, contact: body };
			return route.fulfill({ json: this.application });
		});
	}
}

async function open(page: Page, path: string) {
	const api = new FakeApplicationsApi();
	await api.install(page);
	await page.goto(path);
	return api;
}

test('the timeline drives the status', async ({ page }) => {
	await open(page, '/candidatures/5');
	await expect(page.getByText('À postuler')).toBeVisible();

	await page.getByLabel('Date').fill('2026-11-01');
	await page.getByRole('button', { name: 'Ajouter' }).click();
	await expect(page.getByText('Postulé', { exact: true })).toBeVisible();
	// Intl may put no-break spaces in a date, and the paragraph wraps its lines.
	await expect(page.getByText(/Relance[\s\S]*8\snov\.\s2026/)).toBeVisible();

	await page.getByLabel('Événement').selectOption('interview_scheduled');
	await page.getByLabel('Date').fill('2026-11-05');
	await page.getByLabel('Commentaire', { exact: true }).fill('Visio avec l’équipe');
	await page.getByRole('button', { name: 'Ajouter' }).click();
	await expect(page.getByText('Entretien', { exact: true })).toBeVisible();
	await expect(page.getByText('Visio avec l’équipe')).toBeVisible();

	await page.getByRole('button', { name: /Retirer : Entretien planifié/ }).click();
	await expect(page.getByText('Postulé', { exact: true })).toBeVisible();
});

test('the user rates an application with stars, and clears it', async ({ page }) => {
	await open(page, '/candidatures/5');
	const stars = page.getByRole('group', { name: 'Votre note' });
	const four = stars.getByRole('button', { name: '4 étoiles' });

	await four.click();
	await expect(four).toHaveAttribute('aria-pressed', 'true');

	await four.click();
	await expect(stars.getByRole('button', { pressed: true })).toHaveCount(0);
});

test('a wrong contact address is refused and said', async ({ page }) => {
	await open(page, '/candidatures/5');
	await page.getByLabel('E-mail').fill('pas-une-adresse');
	await page.getByLabel('E-mail').evaluate((input: HTMLInputElement) => (input.type = 'text'));
	await page.getByRole('button', { name: 'Enregistrer le contact' }).click();
	await expect(page.getByRole('alert')).toContainText('vérifiez l’adresse');
});

test('a CV is adapted from the application', async ({ page }) => {
	const api = await open(page, '/candidatures/5');
	await expect(page.getByText('Aucun CV adapté pour l’instant.')).toBeVisible();
	await expect(page.getByText('ce qui sert l’offre')).toBeVisible();

	await page.getByRole('button', { name: 'Adapter mon CV' }).click();

	expect(api.adaptRequests).toBe(1);
	await expect(page.getByRole('alert')).toContainText('ANTHROPIC_API_KEY');
});

test('an application without offer can be added', async ({ page }) => {
	const api = await open(page, '/candidatures');
	await expect(page.getByRole('link', { name: 'Développeur Python' })).toBeVisible();
	await page.getByLabel('Poste').fill('Candidature spontanée');
	await page.getByRole('button', { name: 'Créer la candidature spontanée' }).click();
	await expect(page).toHaveURL(/\/candidatures\/5$/);
	expect(api.created).toEqual([{ title: 'Candidature spontanée', company_name: '' }]);
});

for (const path of ['/candidatures', '/candidatures/5']) {
	test(`${path} fits a phone, with no horizontal scroll`, async ({ page }) => {
		await page.setViewportSize({ width: 390, height: 800 });
		await open(page, path);
		await expect(page.getByText('Développeur Python').first()).toBeVisible();
		const width = await page.evaluate(() => document.documentElement.scrollWidth);
		expect(width).toBeLessThanOrEqual(390);
	});
}

test('a letter is written from the application, or says why not', async ({ page }) => {
	const api = new FakeApplicationsApi();
	await api.install(page);
	await page.route(/\/api\/applications\/\d+\/letters$/, (route) =>
		route.request().method() === 'POST'
			? route.fulfill({
					status: 400,
					json: { message: 'Votre CV est vide : remplissez-le avant la lettre.' }
				})
			: route.fulfill({ json: [] })
	);
	await page.goto('/candidatures/5');
	await page.getByRole('button', { name: 'Rédiger une lettre' }).click();
	await expect(page.getByRole('alert')).toContainText('Votre CV est vide');
});

test('an adapted CV and a letter are deleted after a second click', async ({ page }) => {
	const api = new FakeApplicationsApi();
	await api.install(page);
	const document = { id: 7, created_at: '2026-11-07T09:00:00Z' };
	await page.route(/\/api\/applications\/\d+\/cv-drafts$/, (route) =>
		route.fulfill({ json: [{ ...document, application_id: 5 }] })
	);
	await page.route(/\/api\/applications\/\d+\/letters$/, (route) =>
		route.fulfill({ json: [{ ...document, id: 9, application_id: 5 }] })
	);
	const deleted: string[] = [];
	await page.route(/\/api\/(cv\/drafts|letters)\/\d+$/, (route) => {
		deleted.push(new URL(route.request().url()).pathname);
		return route.fulfill({ status: 204 });
	});
	await page.goto('/candidatures/5');

	await page.getByRole('button', { name: /Supprimer : CV adapté/ }).click();
	await page.getByRole('button', { name: 'Annuler' }).click();
	expect(deleted).toEqual([]);

	await page.getByRole('button', { name: /Supprimer : CV adapté/ }).click();
	await page.getByRole('button', { name: 'Supprimer', exact: true }).click();
	await expect(page.getByText('Aucun CV adapté pour l’instant.')).toBeVisible();

	await page.getByRole('button', { name: /Supprimer : Lettre/ }).click();
	await page.getByRole('button', { name: 'Supprimer', exact: true }).click();
	await expect(page.getByText('Aucune lettre pour l’instant.')).toBeVisible();
	expect(deleted).toEqual(['/api/cv/drafts/7', '/api/letters/9']);
});

test('the applications follow the stars first, hide the closed ones, and filter', async ({
	page
}) => {
	const api = new FakeApplicationsApi();
	const base = api.application;
	const rows = [
		{ ...base, id: 1, title: 'Sans note', company_name: 'Agrimetrics', fit_score: 95 },
		{ ...base, id: 2, title: 'Quatre étoiles', company_name: 'Stratus', rating: 4, fit_score: 50 },
		{ ...base, id: 3, title: 'Deux étoiles', company_name: 'Voltéo', rating: 2, fit_score: 90 },
		{
			...base,
			id: 4,
			title: 'Refusée',
			company_name: 'Banque Rhône',
			rating: 5,
			status: 'cloture' as const,
			tone: 'lost' as const
		}
	];
	await api.install(page);
	await page.route('**/api/applications', (route) => route.fulfill({ json: rows }));
	await page.goto('/candidatures');
	const titles = page.locator('tbody tr td:nth-child(2) a');

	await expect(titles).toHaveText(['Quatre étoiles', 'Deux étoiles', 'Sans note']);
	await expect(page.getByText('3 candidatures', { exact: true })).toBeVisible();

	await page.getByLabel('Afficher les clôturées').check();
	await expect(titles).toHaveText(['Refusée', 'Quatre étoiles', 'Deux étoiles', 'Sans note']);

	await page.getByLabel('Étoiles').selectOption('3');
	await expect(titles).toHaveText(['Refusée', 'Quatre étoiles']);

	await page.getByRole('button', { name: 'Tout réinitialiser' }).click();
	await page.getByRole('columnheader', { name: 'Adéquation' }).getByRole('button').click();
	await expect(titles).toHaveText(['Quatre étoiles', 'Deux étoiles', 'Sans note']);
});
