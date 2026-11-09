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
		contact: { name: '', email: '', phone: '' },
		company_notes: '',
		events: [],
		messages: []
	};
	created: Schemas['NewApplication'][] = [];

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
		await page.route(/\/api\/applications\/\d+$/, (route) =>
			route.fulfill({ json: this.application })
		);
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
	await page.getByLabel('Note', { exact: true }).fill('Visio avec l’équipe');
	await page.getByRole('button', { name: 'Ajouter' }).click();
	await expect(page.getByText('Entretien', { exact: true })).toBeVisible();
	await expect(page.getByText('Visio avec l’équipe')).toBeVisible();

	await page.getByRole('button', { name: /Retirer : Entretien planifié/ }).click();
	await expect(page.getByText('Postulé', { exact: true })).toBeVisible();
});

test('a wrong contact address is refused and said', async ({ page }) => {
	await open(page, '/candidatures/5');
	await page.getByLabel('E-mail').fill('pas-une-adresse');
	await page.getByLabel('E-mail').evaluate((input: HTMLInputElement) => (input.type = 'text'));
	await page.getByRole('button', { name: 'Enregistrer le contact' }).click();
	await expect(page.getByRole('alert')).toContainText('vérifiez l’adresse');
});

test('an application without offer can be added', async ({ page }) => {
	const api = await open(page, '/candidatures');
	await expect(page.getByRole('link', { name: 'Développeur Python' })).toBeVisible();
	await page.getByLabel('Poste').fill('Candidature spontanée');
	await page.getByRole('button', { name: 'Ajouter' }).click();
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
