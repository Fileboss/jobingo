import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type DraftView = Schemas['DraftView'];
type DraftItem = Schemas['DraftItem'];
type DraftChoices = Schemas['DraftChoices'];

const pdf = `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj
trailer<</Root 1 0 R>>
%%EOF`;

const item = (id: string, original: string, extra: Partial<DraftItem> = {}): DraftItem => ({
	id,
	original,
	text: original,
	kept: false,
	proposed: false,
	proposed_rewrite: '',
	rejected_reason: '',
	unsourced_names: [],
	discard_reason: '',
	discarded_by_code: false,
	complement: false,
	...extra
});

/** The drafts API in memory, for Playwright, on the fictional persona's CV. */
export class FakeDraftsApi {
	choicesSent: DraftChoices[] = [];
	pdfRequests = 0;

	draft: DraftView = {
		id: 7,
		lang: 'fr',
		offer_id: null,
		application_id: 5,
		offer: {
			title: 'Ingénieur data plateforme',
			company: 'Plume Énergie',
			description: 'Pipelines Airflow sur PostgreSQL.'
		},
		llm_call_id: 42,
		created_at: '2026-11-07T09:00:00Z',
		updated_at: '2026-11-07T09:00:00Z',
		resume: item('resume-01', 'Ingénieur backend, huit ans.', { kept: true, proposed: true }),
		experiences: [
			{
				...item('nordlys', 'Nordlys — Ingénieur backend senior — 2022 – 2026', {
					kept: true,
					proposed: true
				}),
				bullets: [
					item('nordlys-01', 'Migration de 120 tâches ETL de cron vers Airflow', {
						kept: true,
						proposed: true,
						text: 'Migration de 120 tâches ETL vers Airflow',
						proposed_rewrite: 'Migration de 120 tâches ETL vers Airflow'
					}),
					item('nordlys-02', 'Réduction de 40 % du coût de l’entrepôt', {
						kept: true,
						proposed: true,
						proposed_rewrite: 'Réduction de 60 % du coût de l’entrepôt',
						rejected_reason: 'chiffre absent de la source : 60%'
					})
				]
			},
			{
				...item('colibri', 'Colibri Conseil — Développeur — 2016 – 2018', {
					discard_reason: 'Java bancaire, hors sujet'
				}),
				bullets: []
			}
		],
		projets: [],
		formation: [],
		competences: [item('skill-python', 'Python', { kept: true, proposed: true })],
		langues: [],
		loisirs: [],
		options: { photo: false, panneau_competences: true, loisirs: false },
		option_blockers: {
			photo: 'Ajoutez d’abord une photo dans votre identité.',
			panneau_competences: null,
			loisirs: 'Votre CV n’a pas de section Loisirs.'
		},
		warnings: [],
		gone: 0,
		max_pages: 1
	};

	#apply(choices: DraftChoices) {
		const kept = new Set(choices.kept_ids);
		const update = (entry: DraftItem): DraftItem => ({
			...entry,
			kept: kept.has(entry.id),
			text: choices.texts[entry.id] ?? entry.original
		});
		const draft = this.draft;
		this.draft = {
			...draft,
			resume: draft.resume ? update(draft.resume) : null,
			experiences: draft.experiences.map((e) => ({
				...update(e),
				bullets: e.bullets.map(update)
			})),
			competences: draft.competences.map(update),
			options: choices.options
		};
	}

	async install(page: Page) {
		await page.route(/\/api\/cv\/drafts\/\d+$/, (route) => {
			const id = Number(route.request().url().split('/').at(-1));
			if (id !== this.draft.id) return route.fulfill({ status: 404, json: { detail: 'x' } });
			return route.fulfill({ json: this.draft });
		});
		await page.route(/\/api\/cv\/drafts\/\d+\/choices$/, async (route) => {
			const choices = route.request().postDataJSON() as DraftChoices;
			this.choicesSent.push(choices);
			this.#apply(choices);
			await route.fulfill({ json: this.draft });
		});
		await page.route(/\/api\/cv\/drafts\/\d+\/pdf$/, async (route) => {
			this.pdfRequests += 1;
			await route.fulfill({
				contentType: 'application/pdf',
				headers: {
					'X-Page-Count': '1',
					'X-Missing-Items': '0',
					'Content-Disposition': 'inline; filename="cv-alex-moreau.pdf"'
				},
				body: pdf
			});
		});
	}
}
