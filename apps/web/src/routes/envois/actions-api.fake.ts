import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
type ActionView = Schemas['ActionView'];
type EmailProposal = Schemas['EmailProposal'];

/** The approval queue in memory, for Playwright. Nothing is sent, as in a dry run. */
export class FakeActionsApi {
	actions: ActionView[] = [];
	proposals: EmailProposal[] = [];
	approvals: string[] = [];
	/** What the next approval does: a dry run, or a send the server refuses. */
	outcome: 'dry_run' | 'failed' = 'dry_run';

	propose(
		proposal: Pick<EmailProposal, 'to' | 'subject' | 'body'> & Partial<EmailProposal>
	): ActionView {
		const id = this.actions.length + 1;
		const action: ActionView = {
			id,
			status: 'proposed',
			to: proposal.to,
			subject: proposal.subject,
			application_id: proposal.application_id ?? null,
			application_title: proposal.application_id ? 'Data engineer' : null,
			attachments: proposal.attachments?.length ?? 0,
			dry_run: null,
			created_at: '2026-11-09T10:00:00Z',
			sent_at: null,
			payload: {
				from_name: 'Alex Moreau',
				from_addr: 'alex@jobingo.test',
				to: proposal.to,
				cc: proposal.cc ?? [],
				subject: proposal.subject,
				body_text: proposal.body + '\n',
				in_reply_to: proposal.message_id ? '<r1@volteo.test>' : '',
				references: [],
				attachments: (proposal.attachments ?? []).map((wanted, index) => ({
					document_id: index + 1,
					filename: wanted.kind === 'cv' ? 'cv-alex-moreau.pdf' : 'lettre-alex-moreau.pdf',
					sha256: 'ab'.repeat(32)
				})),
				message_id: `<${id}@jobingo.local>`
			},
			payload_hash: `${id}`.padStart(64, 'c'),
			message_id: proposal.message_id ?? null,
			error: null,
			decided_at: null
		};
		this.actions.push(action);
		return action;
	}

	async install(page: Page) {
		await page.route('**/api/actions', (route) => {
			if (route.request().method() === 'POST') {
				const proposal = route.request().postDataJSON() as EmailProposal;
				this.proposals.push(proposal);
				return route.fulfill({ status: 201, json: this.propose(proposal) });
			}
			return route.fulfill({ json: [...this.actions].reverse() });
		});
		await page.route(/\/api\/actions\/\d+(\/[a-z]+)?$/, (route) => {
			const [, id, verb] = /actions\/(\d+)(?:\/([a-z]+))?$/.exec(route.request().url()) ?? [];
			const index = this.actions.findIndex((a) => a.id === Number(id));
			if (index < 0) return route.fulfill({ status: 404, json: { detail: 'Envoi introuvable' } });
			const action = this.actions[index];
			if (!verb) return route.fulfill({ json: action });
			if (verb === 'approve') {
				const { payload_hash } = route.request().postDataJSON() as { payload_hash: string };
				this.approvals.push(payload_hash);
				if (action.status !== 'proposed' || payload_hash !== action.payload_hash)
					return route.fulfill({
						status: 409,
						json: { message: 'Cet envoi n’attend plus de validation.' }
					});
			}
			const next: ActionView =
				verb === 'reject'
					? { ...action, status: 'rejected' }
					: this.outcome === 'failed' && verb === 'approve'
						? {
								...action,
								status: 'failed',
								error: 'Le serveur SMTP 127.0.0.1:1 n’a pas accepté le message.'
							}
						: { ...action, status: 'sent', dry_run: true, sent_at: '2026-11-09T10:01:00Z' };
			this.actions[index] = next;
			return route.fulfill({ json: next });
		});
	}
}
