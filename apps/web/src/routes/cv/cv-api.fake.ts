import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type Fields = Schemas['CvFields'];
type Document = Schemas['CvDocument'];

const emptyFields = (): Fields => ({
	front: '',
	resume: '',
	experiences: [],
	formation: [],
	skills: [],
	hobbies: [],
	before: '',
	others: [],
	order: []
});

function fieldsToText(fields: Fields): string {
	const out: string[] = [];
	if (fields.resume.trim()) out.push('## Résumé', '', fields.resume.trim(), '');
	const experiences = fields.experiences.filter((item) => item.company || item.bullets.length);
	if (experiences.length) {
		out.push('## Expériences', '');
		for (const item of experiences) {
			const dates = [item.start, item.end].filter(Boolean).join(' – ');
			out.push(`### ${[item.company, item.role, dates].filter(Boolean).join(' — ')}`, '');
			out.push(...item.bullets.filter(Boolean).map((bullet) => `- ${bullet}`), '');
		}
	}
	const skills = fields.skills.filter(Boolean);
	if (skills.length) out.push('## Compétences', '', ...skills.map((skill) => `- ${skill}`), '');
	return out.join('\n');
}

function textToFields(text: string): Fields {
	const fields = emptyFields();
	let section = '';
	for (const raw of text.split('\n')) {
		const line = raw.trim();
		if (line.startsWith('### ')) {
			const [company = '', role = '', dates = ''] = line.slice(4).split(' — ');
			const [start = '', end = ''] = dates.split(' – ');
			fields.experiences.push({
				company,
				role,
				start,
				end,
				title: '',
				structured: true,
				tags: [],
				bullets: []
			});
		} else if (line.startsWith('## ')) {
			section = line.slice(3);
		} else if (line.startsWith('- ')) {
			if (section === 'Expériences') fields.experiences.at(-1)?.bullets.push(line.slice(2));
			if (section === 'Compétences') fields.skills.push(line.slice(2));
		} else if (line && section === 'Résumé') {
			fields.resume += line;
		}
	}
	return fields;
}

function diagnose(text: string): Schemas['CvDiagnostic'][] {
	const found: Schemas['CvDiagnostic'][] = [];
	let section: string | null = null;
	text.split('\n').forEach((line, index) => {
		if (line.startsWith('## ')) section = line.slice(3);
		const email = line.match(/[\w.+-]+@[\w-]+\.[\w.]+/);
		if (email) {
			found.push({
				code: 'personal_email',
				level: 'warning',
				line_no: index + 1,
				section,
				message: `Adresse e-mail détectée : « ${email[0]} »`,
				suggestion: 'Vos coordonnées sont ajoutées au moment du rendu.'
			});
		}
	});
	return found;
}

function view(draft: Schemas['CvDraft']) {
	const fields = draft.mode === 'form' ? draft.fields : textToFields(draft.text);
	const text = fieldsToText(fields);
	return { lang: 'fr' as const, text, fields: textToFields(text), diagnostics: diagnose(text) };
}

/** A fictional stored CV, as the server would send it. */
export const fictionalCv = [
	'## Résumé',
	'',
	'Ingénieur backend, huit ans sur des plateformes de données.',
	'',
	'## Expériences',
	'',
	'### Nordlys — Ingénieur backend senior — 01/2022 – 08/2026',
	'',
	'- Migration de 120 tâches ETL vers Airflow',
	'',
	'## Compétences',
	'',
	'- Python',
	''
].join('\n');

/** The CV API in memory, for Playwright. The real one is covered by the backend tests. */
export class FakeCvApi {
	document: Document = {
		...view({ mode: 'text', text: '' }),
		sha256: null,
		version: 0,
		updated_at: null
	};
	failing = false;

	store(text: string) {
		const version = this.document.version + 1;
		this.document = {
			...view({ mode: 'text', text }),
			sha256: `sha-${version}`,
			version,
			updated_at: '2026-11-05T18:42:00Z'
		};
	}

	async install(page: Page) {
		await page.route('**/api/cv/fr/convert', async (route) => {
			if (this.failing) return route.abort();
			const { draft } = route.request().postDataJSON();
			await route.fulfill({ json: view(draft) });
		});
		await page.route('**/api/cv/fr', async (route) => {
			if (this.failing) return route.abort();
			if (route.request().method() === 'GET') return route.fulfill({ json: this.document });
			const { draft, expected_sha256 } = route.request().postDataJSON();
			if (expected_sha256 !== this.document.sha256) {
				return route.fulfill({ status: 409, json: { current: this.document } });
			}
			this.store(view(draft).text);
			await route.fulfill({ json: this.document });
		});
	}
}
