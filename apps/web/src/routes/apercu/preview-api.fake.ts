import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type CvPage = Schemas['CvPage'];
type Identity = Schemas['IdentityDocument'];

const pdf = `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj
trailer<</Root 1 0 R>>
%%EOF`;

const onePixelPng = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/AAAMBAQAY3Y2wAAAAAElFTkSuQmCC',
	'base64'
);

export const fictionalIdentity = {
	name: 'Alex Moreau',
	email: 'alex.moreau@example.fr',
	phone: '+33 6 00 00 00 00',
	address: '12 rue des Lilas, 44000 Nantes',
	linkedin: 'linkedin.com/in/alex-moreau',
	github: 'github.com/alex-moreau'
};

const item = (id: string, text: string) => ({ id, text, selected: true });

/** The selection, identity and PDF API in memory, for Playwright. */
export class FakePreviewApi {
	identity: Identity = {
		name: '',
		email: '',
		phone: '',
		address: '',
		linkedin: '',
		github: '',
		has_photo: false
	};
	excluded: string[] = [];
	options = { photo: false, panneau_competences: true, loisirs: true };
	empty = false;
	hobbies = [item('h1', 'Voile'), item('h2', 'Échecs')];
	pages = 1;
	missingItems = 0;
	/** What the PDF route does: answer, refuse with a message, or be unreachable. */
	pdfState: 'ok' | 'refused' | 'down' = 'ok';
	pdfRequests = 0;
	selectionsSent: { excluded_ids: string[]; options: CvPage['options'] }[] = [];

	get page(): CvPage {
		const mark = <T extends { id: string; selected: boolean }>(entry: T): T => ({
			...entry,
			selected: !this.excluded.includes(entry.id)
		});
		const hobbies = this.empty ? [] : this.hobbies;
		const option_blockers = {
			photo: this.identity.has_photo ? null : 'Ajoutez d’abord une photo.',
			panneau_competences: null,
			loisirs: hobbies.length ? null : 'Aucun loisir dans le CV.'
		};
		return {
			resume: this.empty
				? null
				: mark(item('r1', 'Ingénieur backend, huit ans sur des plateformes de données.')),
			experiences: this.empty
				? []
				: [
						{
							...mark(item('x1', 'Nordlys — Ingénieur backend senior')),
							dates: '01/2022 – 08/2026',
							bullets: [
								item('b1', 'Migration de 120 tâches ETL vers Airflow'),
								item('b2', 'Réduction de 40 % du temps de traitement')
							].map(mark)
						}
					],
			formation: this.empty
				? []
				: [{ ...mark(item('f1', 'Diplôme d’ingénieur, Centrale Nantes')), heading: false }],
			competences: this.empty ? [] : [item('c1', 'Python'), item('c2', 'PostgreSQL')].map(mark),
			loisirs: hobbies.map(mark),
			excluded_ids: this.excluded,
			options: {
				photo: this.options.photo && !option_blockers.photo,
				panneau_competences: this.options.panneau_competences,
				loisirs: this.options.loisirs && !option_blockers.loisirs
			},
			option_blockers,
			max_pages: 1
		};
	}

	async install(page: Page) {
		await page.route('**/api/cv/fr/selection', async (route) => {
			if (route.request().method() === 'PUT') {
				const body = route.request().postDataJSON();
				this.selectionsSent.push(body);
				this.excluded = body.excluded_ids;
				this.options = body.options;
			}
			await route.fulfill({ json: this.page });
		});
		await page.route('**/api/cv/fr/pdf', async (route) => {
			this.pdfRequests += 1;
			if (this.pdfState === 'down') return route.abort();
			if (this.pdfState === 'refused') {
				return route.fulfill({
					status: 503,
					json: { message: 'Le PDF n’a pas pu être produit : le moteur de rendu a échoué.' }
				});
			}
			await route.fulfill({
				contentType: 'application/pdf',
				headers: {
					'X-Page-Count': String(this.pages),
					'X-Missing-Items': String(this.missingItems),
					'Content-Disposition': 'inline; filename="cv-alex-moreau.pdf"'
				},
				body: pdf
			});
		});
		await page.route('**/api/identity', async (route) => {
			if (route.request().method() === 'PUT') {
				this.identity = { ...route.request().postDataJSON(), has_photo: this.identity.has_photo };
			}
			await route.fulfill({ json: this.identity });
		});
		await page.route('**/api/identity/photo*', async (route) => {
			const method = route.request().method();
			if (method === 'GET') {
				return route.fulfill({ contentType: 'image/png', body: onePixelPng });
			}
			if (method === 'DELETE') {
				this.identity = { ...this.identity, has_photo: false };
			} else {
				const { data_base64 } = route.request().postDataJSON();
				if (!Buffer.from(data_base64, 'base64').subarray(1, 4).equals(Buffer.from('PNG'))) {
					return route.fulfill({
						status: 400,
						json: { message: 'Ce fichier n’est pas une image JPEG ou PNG lisible.' }
					});
				}
				this.identity = { ...this.identity, has_photo: true };
			}
			await route.fulfill({ json: this.identity });
		});
	}
}

export const pngFile = { name: 'photo.png', mimeType: 'image/png', buffer: onePixelPng };
export const notAnImage = {
	name: 'photo.png',
	mimeType: 'image/png',
	buffer: Buffer.from('ceci n’est pas une image')
};
