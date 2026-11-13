/**
 * The README's screenshots (`make screenshots`), on the fictional persona Alex Moreau.
 *
 * The real client runs against an API answered here, in memory: no database, no model,
 * nothing personal. The CV, the adapted CV, the letter and their PDFs come from
 * `scripts/screenshot_data.py`, which renders them with the server's own code; the eval
 * results are the committed, measured ones.
 */
import { expect, test, type Locator, type Page, type Route } from '@playwright/test';
import { readFileSync } from 'node:fs';
import type { components } from '#lib/api/schema.d.ts';
import { offer, score } from '../src/routes/offres/offers-api.fake.ts';

type Schemas = components['schemas'];

const DATA = new URL('./.data/', import.meta.url);
const IMAGES = new URL('../../../docs/images/', import.meta.url);
const read = (name: string) => readFileSync(new URL(name, DATA));
const readJson = (name: string) => JSON.parse(read(name).toString('utf-8'));

const offers: Schemas['ScoredOffer'][] = [
	offer(2, 'Ingénieur data plateforme', {
		company_name: 'Plume Énergie',
		locations: ['Montpellier'],
		salary_min: 55000,
		salary_max: 62000,
		application_id: 5,
		current_score: score(2, 86, { salary_score: 70 })
	}),
	offer(3, 'Ingénieur backend Python', {
		company_name: 'Voltéo',
		locations: ['Lyon'],
		remote: 'remote',
		salary_min: 58000,
		salary_max: 68000,
		application_id: 8,
		current_score: score(3, 81, { salary_score: 80 })
	}),
	offer(9, 'Ingénieur données énergie', {
		company_name: 'Courant Vert',
		locations: ['Grenoble'],
		salary_min: 52000,
		salary_max: 60000,
		created_at: '2026-11-13T08:40:00Z',
		current_score: score(9, 77, { salary_score: 60 })
	}),
	offer(4, 'Développeur Django', {
		company_name: 'Agrimetrics',
		locations: ['Toulouse'],
		salary_min: 48000,
		salary_max: 55000,
		decision: 'shortlisted',
		current_score: score(4, 74, { salary_score: 45 })
	}),
	offer(5, 'Ingénieur fiabilité (SRE)', {
		company_name: 'Cartésia',
		locations: ['Paris', 'Lyon'],
		salary_min: 60000,
		salary_max: 70000,
		application_id: 11,
		current_score: score(5, 69, { salary_score: 85 })
	}),
	offer(6, 'Data engineer', {
		company_name: 'Ondine Analytics',
		locations: ['Nantes'],
		remote: 'sur site',
		salary_min: null,
		salary_max: null,
		current_score: score(6, 63, { salary_score: null })
	}),
	offer(7, 'Développeur full-stack', {
		company_name: 'Studio Kiosque',
		locations: ['Montpellier'],
		contract: 'freelance',
		remote: 'remote',
		salary_min: 45000,
		salary_max: 52000,
		current_score: score(7, 57, { salary_score: 35 })
	}),
	offer(8, 'Lead developer PHP', {
		company_name: 'Ferrovia',
		locations: ['Lille'],
		remote: 'sur site',
		salary_min: 50000,
		salary_max: 56000,
		decision: 'dismissed',
		current_score: score(8, 38, { salary_score: 40 })
	}),
	offer(10, 'Développeur Java', {
		company_name: 'Banque Rhône',
		contract: 'CDD',
		state: 'filtered',
		current_score: score(10, 0, {
			passed_filters: false,
			eliminated_by: ['contrat non retenu : CDD'],
			criteria: null,
			fit_score: null,
			salary_score: null,
			llm_call_id: null
		})
	})
];

const event = (
	id: number,
	type: Schemas['EventType'],
	occurred_at: string,
	note = ''
): Schemas['ApplicationEvent'] => ({
	id,
	type,
	occurred_at,
	note,
	created_at: `${occurred_at}T09:00:00Z`
});

const summary = (
	id: number,
	title: string,
	company_name: string,
	extra: Partial<Schemas['ApplicationSummary']>
): Schemas['ApplicationSummary'] => ({
	id,
	offer_id: null,
	title,
	company_name,
	rating: null,
	status: 'a_postuler',
	tone: 'todo',
	last_event: null,
	follow_up_on: null,
	created_at: '2026-11-02T09:00:00Z',
	fit_score: null,
	salary_score: null,
	salary_min: null,
	salary_max: null,
	...extra
});

const interview = event(
	3,
	'interview_scheduled',
	'2026-11-18',
	'Entretien technique en visio, une heure, avec l’équipe data.'
);
const plume = summary(5, 'Ingénieur data plateforme', 'Plume Énergie', {
	offer_id: 2,
	rating: 5,
	status: 'entretien',
	tone: 'active',
	last_event: interview,
	fit_score: 86,
	salary_score: 70,
	salary_min: 55000,
	salary_max: 62000
});

const applications: Schemas['ApplicationSummary'][] = [
	plume,
	summary(8, 'Ingénieur backend Python', 'Voltéo', {
		offer_id: 3,
		rating: 4,
		status: 'postule',
		tone: 'active',
		last_event: event(20, 'applied', '2026-11-03'),
		follow_up_on: '2026-11-10',
		fit_score: 81,
		salary_score: 80,
		salary_min: 58000,
		salary_max: 68000
	}),
	summary(10, 'Ingénieur logiciel', 'Nacelle', {
		rating: 4,
		status: 'en_echange',
		tone: 'active',
		last_event: event(30, 'message_received', '2026-11-12')
	}),
	summary(11, 'Ingénieur fiabilité (SRE)', 'Cartésia', {
		offer_id: 5,
		status: 'postule',
		tone: 'active',
		last_event: event(40, 'applied', '2026-11-10'),
		follow_up_on: '2026-11-17',
		fit_score: 69,
		salary_score: 85,
		salary_min: 60000,
		salary_max: 70000
	}),
	summary(9, 'Développeur Django', 'Agrimetrics', {
		offer_id: 4,
		rating: 3,
		fit_score: 74,
		salary_score: 45,
		salary_min: 48000,
		salary_max: 55000
	}),
	summary(12, 'Développeur Python', 'Transmer', {
		rating: 2,
		status: 'cloture',
		tone: 'lost',
		last_event: event(50, 'rejected', '2026-11-06')
	})
];

const plumeView: Schemas['ApplicationView'] = {
	...plume,
	contact: {
		name: 'Camille Roux',
		email: 'camille.roux@plume-energie.example',
		phone: ''
	},
	company_notes:
		'Une quarantaine de personnes, des parcs solaires en Occitanie. L’équipe data compte trois ingénieurs et migre ses traitements vers Airflow.',
	events: [
		interview,
		event(2, 'message_received', '2026-11-07', 'Camille Roux propose un entretien.'),
		event(1, 'applied', '2026-11-04', 'Envoyée avec le CV adapté et la lettre.')
	],
	messages: [
		{
			id: 21,
			from_addr: 'Camille Roux <camille.roux@plume-energie.example>',
			subject: 'Votre candidature : ingénieur data plateforme',
			received_at: '2026-11-07T08:12:00Z',
			category: 'interview'
		}
	]
};

const draft = readJson('draft.json') as Schemas['DraftView'];
const letter = readJson('letter.json') as Schemas['LetterView'];

const message = (
	id: number,
	extra: Partial<Schemas['MessageSummary']>
): Schemas['MessageSummary'] => ({
	id,
	folder: 'INBOX',
	from_addr: '',
	subject: '',
	received_at: '2026-11-12T08:00:00Z',
	kind: 'message',
	offer_count: 0,
	excerpt: '',
	category: null,
	summary: '',
	hidden_reason: null,
	application_id: null,
	application_title: null,
	suggestion: null,
	...extra
});

const messages: Schemas['MessageSummary'][] = [
	message(30, {
		from_addr: 'Léa Martin <lea@nacelle.example>',
		subject: 'Re : candidature spontanée',
		received_at: '2026-11-12T15:20:00Z',
		excerpt: 'Merci pour votre message, pourriez-vous nous dire vos disponibilités ?',
		category: 'recruiter_other',
		summary: 'Nacelle demande vos disponibilités pour un premier échange.',
		application_id: 10,
		application_title: 'Ingénieur logiciel'
	}),
	message(29, {
		from_addr: 'LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>',
		subject: 'Nouvelles offres pour « data engineer »',
		received_at: '2026-11-13T07:00:00Z',
		kind: 'alert',
		offer_count: 3,
		excerpt: 'Vos offres du jour.'
	}),
	message(25, {
		from_addr: 'Recrutement Transmer <jobs@transmer.example>',
		subject: 'Votre candidature chez Transmer',
		received_at: '2026-11-06T10:00:00Z',
		excerpt: 'Nous ne donnerons pas suite à votre candidature.',
		category: 'rejection',
		summary: 'Transmer ne donne pas suite à la candidature de développeur Python.',
		application_id: 12,
		application_title: 'Développeur Python',
		suggestion: { type: 'rejected', date: null, status: 'accepted' }
	}),
	message(21, {
		from_addr: 'Camille Roux <camille.roux@plume-energie.example>',
		subject: 'Votre candidature : ingénieur data plateforme',
		received_at: '2026-11-07T08:12:00Z',
		excerpt: 'Seriez-vous disponible le 18 novembre à 14 h pour un entretien technique ?',
		category: 'interview',
		summary: 'Plume Énergie propose un entretien technique le 18 novembre à 14 h.',
		application_id: 5,
		application_title: 'Ingénieur data plateforme',
		suggestion: {
			type: 'interview_scheduled',
			date: '2026-11-18T14:00:00+01:00',
			status: 'accepted'
		}
	})
];

const reply =
	'Bonjour Léa,\n\nMerci pour votre retour. Je suis disponible mardi 18 en fin de journée, ' +
	'ou jeudi 20 toute la matinée, pour un premier échange.\n\nBien cordialement,\nAlex Moreau';

const action: Schemas['ActionView'] = {
	id: 4,
	status: 'proposed',
	to: ['lea@nacelle.example'],
	subject: 'Re : candidature spontanée',
	application_id: 10,
	application_title: 'Ingénieur logiciel',
	attachments: 1,
	dry_run: null,
	created_at: '2026-11-13T09:05:00Z',
	sent_at: null,
	payload: {
		from_name: 'Alex Moreau',
		from_addr: 'alex.moreau@example.org',
		to: ['lea@nacelle.example'],
		cc: [],
		subject: 'Re : candidature spontanée',
		body_text: reply + '\n',
		in_reply_to: '<30@nacelle.example>',
		references: ['<30@nacelle.example>'],
		attachments: [{ document_id: 12, filename: 'cv-alex-moreau.pdf', sha256: '3f9a'.repeat(16) }],
		message_id: '<4@jobingo.local>'
	},
	payload_hash: '8c1e'.repeat(16),
	message_id: 30,
	llm_call_id: 57,
	error: null,
	decided_at: null
};

const sent: Schemas['ActionView'] = {
	...action,
	id: 3,
	status: 'sent',
	dry_run: false,
	to: ['camille.roux@plume-energie.example'],
	subject: 'Re : Votre candidature : ingénieur data plateforme',
	application_id: 5,
	application_title: 'Ingénieur data plateforme',
	attachments: 0,
	created_at: '2026-11-07T10:00:00Z',
	sent_at: '2026-11-07T10:02:00Z'
};

/** Every API path the screens ask for, answered from the data above. */
function answer(method: string, path: string): unknown {
	const routes: [RegExp, () => unknown][] = [
		[/^\/api\/cv\/fr(\/convert)?$/, () => cvDocument()],
		[/^\/api\/offers$/, () => offers],
		[/^\/api\/offers\/stale$/, () => ({ count: 0 })],
		[/^\/api\/applications$/, () => applications],
		[/^\/api\/applications\/5$/, () => plumeView],
		[
			/^\/api\/applications\/5\/cv-drafts$/,
			() => [draftSummary(7, '2026-11-04T17:50:00Z'), draftSummary(6, '2026-11-04T17:20:00Z')]
		],
		[
			/^\/api\/applications\/5\/letters$/,
			() => [
				{
					id: 3,
					application_id: 5,
					llm_call_id: 31,
					created_at: '2026-11-04T18:05:00Z',
					updated_at: '2026-11-04T18:12:00Z'
				}
			]
		],
		[/^\/api\/cv\/drafts\/7$/, () => draft],
		[/^\/api\/letters\/3$/, () => letter],
		[/^\/api\/mail\/status$/, () => mailbox],
		[/^\/api\/mail\/messages$/, () => (method === 'GET' ? messages : [])],
		[/^\/api\/actions$/, () => [action, sent]],
		[/^\/api\/actions\/4$/, () => action],
		[/^\/api\/observability\/evals$/, () => readJson('evals.json')]
	];
	return routes.find(([pattern]) => pattern.test(path))?.[1]();
}

const draftSummary = (id: number, at: string): Schemas['DraftSummary'] => ({
	id,
	offer_id: 2,
	application_id: 5,
	offer_title: 'Ingénieur data plateforme',
	offer_company: 'Plume Énergie',
	llm_call_id: id === 7 ? 42 : 40,
	created_at: at,
	updated_at: at
});

const mailbox: Schemas['MailboxStatus'] = {
	address: 'alex.moreau@example.org',
	host: '127.0.0.1',
	local: true,
	dry_run: true,
	folders: [{ folder: 'INBOX', synced_at: '2026-11-13T09:00:00Z' }],
	waiting: 0,
	suggestions: 0
};

function cvDocument() {
	return readJson('cv.json');
}

async function serve(route: Route) {
	const request = route.request();
	const { pathname, searchParams } = new URL(request.url());
	if (pathname.endsWith('/pdf')) {
		const file = pathname.startsWith('/api/letters') ? 'letter.pdf' : 'cv.pdf';
		return route.fulfill({
			contentType: 'application/pdf',
			headers: { 'X-Page-Count': '1', 'X-Missing-Items': '0' },
			body: read(file)
		});
	}
	// Hidden mail is asked apart: none here.
	if (pathname === '/api/mail/messages' && searchParams.get('hidden') === 'true') {
		return route.fulfill({ json: [] });
	}
	const json = answer(request.method(), pathname);
	if (json === undefined)
		throw new Error(`no fictional answer for ${request.method()} ${pathname}`);
	return route.fulfill({ json });
}

async function open(page: Page, path: string) {
	await page.route('**/api/**', serve);
	await page.goto(path);
}

/** The window, or a window's height of the page from `top` down. */
async function shoot(page: Page, name: string, top?: Locator) {
	// The PDF viewer and the fonts settle after the data.
	await page.waitForTimeout(1500);
	const path = new URL(`${name}.png`, IMAGES).pathname;
	const box = top && (await top.boundingBox());
	if (!box) return page.screenshot({ path });
	const y = box.y + (await page.evaluate(() => window.scrollY)) - 24;
	await page.screenshot({ path, fullPage: true, clip: { x: 0, y, width: 1440, height: 900 } });
}

test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale: 'fr-FR' });

test('cv-form', async ({ page }) => {
	await open(page, '/cv');
	await expect(page.getByRole('textbox', { name: 'Résumé' })).toBeVisible();
	await shoot(page, 'cv-form');
});

test('cv-text', async ({ page }) => {
	await open(page, '/cv');
	await page.getByRole('button', { name: 'Texte', exact: true }).click();
	await expect(page.getByRole('textbox', { name: 'Texte du CV' })).toBeVisible();
	await shoot(page, 'cv-text');
});

test('offers', async ({ page }) => {
	await open(page, '/offres');
	await expect(page.getByRole('link', { name: 'Ingénieur data plateforme' })).toBeVisible();
	// The table, not the paste box above it.
	await shoot(page, 'offers', page.getByRole('heading', { name: /Offres reçues/ }));
});

test('applications', async ({ page }) => {
	await open(page, '/candidatures');
	await expect(page.getByRole('link', { name: 'Ingénieur data plateforme' })).toBeVisible();
	await shoot(page, 'applications');
});

test('application', async ({ page }) => {
	await open(page, '/candidatures/5');
	await expect(page.getByRole('heading', { name: 'Ingénieur data plateforme' })).toBeVisible();
	await shoot(page, 'application');
});

test('adapted-cv', async ({ page }) => {
	await open(page, '/adapter/7');
	await expect(page.getByTitle('Aperçu du CV')).toBeVisible();
	await shoot(page, 'adapted-cv');
});

test('letter', async ({ page }) => {
	await open(page, '/lettres/3');
	await expect(page.locator('iframe')).toBeVisible();
	await shoot(page, 'letter');
});

test('exchanges', async ({ page }) => {
	await open(page, '/echanges');
	await expect(page.getByText('Re : candidature spontanée').first()).toBeVisible();
	await shoot(page, 'exchanges');
});

test('approval', async ({ page }) => {
	await open(page, '/echanges/envois/4');
	await expect(page.getByText('Bonjour Léa').first()).toBeVisible();
	await shoot(page, 'approval');
});

test('evals', async ({ page }) => {
	await open(page, '/suivi/evals');
	const task = page.getByRole('heading', { name: /select_cv_content/ });
	await expect(task).toBeVisible();
	await shoot(page, 'evals', task);
});
