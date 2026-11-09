import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';
import { offer } from '../offres/offers-api.fake.ts';

type Schemas = components['schemas'];
type Message = Schemas['Message'];
type MailboxStatus = Schemas['MailboxStatus'];
type SyncReport = Schemas['SyncReport'];

const message = (id: number, extra: Partial<Message> = {}): Message => ({
	id,
	folder: 'INBOX',
	from_addr: 'Camille Roux <camille@volteo.test>',
	to_addrs: 'alex@jobingo.test',
	subject: 'Votre profil nous intéresse',
	received_at: '2026-11-07T08:30:00Z',
	kind: 'message',
	offer_count: 0,
	excerpt: 'Bonjour Alex, seriez-vous disponible pour un échange ?',
	body_text: 'Bonjour Alex,\n\nseriez-vous disponible pour un échange ?\n\nCamille',
	offer_ids: [],
	processed_at: null,
	category: null,
	summary: '',
	hidden_reason: null,
	application_id: null,
	application_title: null,
	suggestion: null,
	company_hint: '',
	linked_by: null,
	llm_call_id: null,
	...extra
});

/** A refusal the model read, not tied to an application yet. */
const refusal = message(1, {
	subject: 'Votre candidature chez Voltéo',
	excerpt: 'Nous ne donnerons pas suite à votre candidature.',
	body_text: 'Bonjour Alex,\n\nnous ne donnerons pas suite à votre candidature.\n\nCamille',
	processed_at: '2026-11-07T09:00:00Z',
	category: 'rejection',
	summary: 'Voltéo ne donne pas suite à la candidature de data engineer.',
	company_hint: 'Voltéo',
	suggestion: { type: 'rejected', date: null, status: 'pending' },
	llm_call_id: 41
});

const newsletter = message(3, {
	from_addr: 'Lettre <news@reseau.test>',
	subject: 'Les nouvelles de la semaine',
	excerpt: 'Cinq conseils pour votre profil.',
	body_text: 'Cinq conseils pour votre profil.',
	processed_at: '2026-11-07T09:00:00Z',
	hidden_reason: 'newsletter'
});

const alert = message(2, {
	from_addr: 'LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>',
	subject: 'Nouvelles offres pour « python »',
	received_at: '2026-11-07T07:00:00Z',
	kind: 'alert',
	offer_count: 2,
	excerpt: 'Vos offres du jour.',
	body_text: 'Vos offres du jour.',
	offer_ids: [5, 6],
	processed_at: '2026-11-07T09:00:00Z'
});

/** A message as the list gives it, without its text. */
const summary = (m: Message): Schemas['MessageSummary'] => ({
	id: m.id,
	folder: m.folder,
	from_addr: m.from_addr,
	subject: m.subject,
	received_at: m.received_at,
	kind: m.kind,
	offer_count: m.offer_count,
	excerpt: m.excerpt,
	category: m.category,
	summary: m.summary,
	hidden_reason: m.hidden_reason,
	application_id: m.application_id,
	application_title: m.application_title,
	suggestion: m.suggestion
});

const application: Schemas['ApplicationSummary'] = {
	id: 7,
	offer_id: 6,
	title: 'Data engineer',
	company_name: 'Voltéo',
	status: 'postule',
	tone: 'active',
	last_event: null,
	follow_up_on: null,
	created_at: '2026-11-01T09:00:00Z'
};

/** The mail API in memory, for Playwright, with a fictional mailbox. */
export class FakeMailApi {
	messages: Message[] = [];
	syncRequests = 0;
	/** What the next sync answers: new mail, or an unreachable mailbox. */
	syncAnswer: 'mail' | 'unreachable' = 'mail';
	status: MailboxStatus = {
		address: 'alex@jobingo.test',
		host: '127.0.0.1',
		local: true,
		dry_run: true,
		folders: [{ folder: 'INBOX', synced_at: null }],
		waiting: 0,
		suggestions: 0
	};
	/** Decisions sent, as `verb path`. */
	decisions: string[] = [];
	offers = [
		offer(5, 'Ingénieur logiciel Python', {
			company_name: 'Plume Énergie',
			message_id: 2,
			llm_call_id: null
		}),
		offer(6, 'Data engineer', {
			company_name: 'Voltéo',
			message_id: 2,
			llm_call_id: null,
			state: 'new',
			current_score: null
		})
	];

	async install(page: Page) {
		await page.route('**/api/mail/status', (route) => route.fulfill({ json: this.status }));
		await page.route(/\/api\/mail\/messages(\?.*)?$/, (route) => {
			const hidden = new URL(route.request().url()).searchParams.get('hidden') === 'true';
			return route.fulfill({
				json: this.messages.filter((m) => (m.hidden_reason !== null) === hidden).map(summary)
			});
		});
		await page.route('**/api/applications', (route) => route.fulfill({ json: [application] }));
		await page.route(/\/api\/mail\/messages\/\d+\/.+$/, (route) => {
			const request = route.request();
			const [, id, action] = /messages\/(\d+)\/(.+)$/.exec(request.url()) ?? [];
			const index = this.messages.findIndex((m) => m.id === Number(id));
			if (index < 0) return route.fulfill({ status: 404, json: { detail: 'Introuvable' } });
			this.decisions.push(`${request.method()} ${action}`);
			const current = this.messages[index];
			let next: Message = current;
			if (action === 'application') {
				const chosen = (request.postDataJSON() as { application_id: number | null }).application_id;
				next = {
					...current,
					application_id: chosen,
					application_title: chosen ? application.title : null,
					linked_by: chosen ? 'user' : null
				};
			} else if (action.startsWith('suggestion/') && current.suggestion) {
				const status = action.endsWith('accept') ? 'accepted' : 'dismissed';
				next = { ...current, suggestion: { ...current.suggestion, status } };
			} else if (action === 'hidden') {
				const { hidden } = request.postDataJSON() as { hidden: boolean };
				next = { ...current, hidden_reason: hidden ? 'user' : null };
			} else if (action === 'block-sender') {
				next = { ...current, hidden_reason: 'blocked_sender' };
			}
			this.messages[index] = next;
			return route.fulfill({ json: next });
		});
		await page.route(/\/api\/mail\/messages\/\d+$/, (route) => {
			const id = Number(route.request().url().split('/').at(-1));
			const found = this.messages.find((m) => m.id === id);
			return found
				? route.fulfill({ json: found })
				: route.fulfill({ status: 404, json: { detail: 'Message introuvable' } });
		});
		await page.route('**/api/offers', (route) => route.fulfill({ json: this.offers }));
		await page.route('**/api/mail/sync', (route) => {
			this.syncRequests += 1;
			if (this.syncAnswer === 'unreachable') {
				return route.fulfill({
					status: 502,
					json: { message: 'Le serveur IMAP 127.0.0.1:3143 est injoignable ([Errno 61]).' }
				});
			}
			this.messages = [refusal, alert, newsletter];
			this.status = {
				...this.status,
				folders: [{ folder: 'INBOX', synced_at: '2026-11-07T09:00:00Z' }]
			};
			const report: SyncReport = {
				fetched: 3,
				duplicates: 0,
				alerts: 1,
				classified: 1,
				hidden: 1,
				linked: 0,
				offer_ids: [5, 6],
				unscored_ids: [6],
				waiting: 0,
				has_more: false,
				error: null
			};
			return route.fulfill({ json: report });
		});
	}
}
