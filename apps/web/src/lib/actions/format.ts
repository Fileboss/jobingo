import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type ActionSummary = Schemas['ActionSummary'];
export type ActionView = Schemas['ActionView'];
export type ActionStatus = ActionSummary['status'];
export type EmailProposal = Schemas['EmailProposal'];
export type ReplyDraft = Schemas['ReplyDraft'];
export type Intent = Schemas['ReplyRequest']['intent'];

export const intentLabels: Record<Intent, string> = {
	accepter_entretien: 'Accepter un entretien',
	demander_precisions: 'Demander des précisions',
	decliner: 'Décliner poliment',
	relancer: 'Relancer',
	remercier: 'Remercier après un entretien',
	candidater: 'Envoyer ma candidature'
};

export const statusLabels: Record<ActionStatus, string> = {
	proposed: 'À valider',
	approved: 'Validé',
	sending: 'Envoi en cours',
	sent: 'Envoyé',
	failed: 'Échec',
	rejected: 'Refusé'
};

/** A send in a dry run left nothing: say it wherever it shows as sent. */
export function statusLabel(action: Pick<ActionSummary, 'status' | 'dry_run'>): string {
	return action.status === 'sent' && action.dry_run ? 'Simulé' : statusLabels[action.status];
}

export const statusColours: Record<ActionStatus, string> = {
	proposed: 'bg-postit',
	approved: 'bg-bristol-blue',
	sending: 'bg-bristol-blue',
	sent: 'bg-bristol-green',
	failed: 'bg-bristol-salmon',
	rejected: 'bg-bristol-grey'
};

/** `Re: ` once, whatever the subject already starts with. */
export function replySubject(subject: string): string {
	return /^\s*re\s*:/i.test(subject) ? subject.trim() : `Re: ${subject.trim()}`;
}

/** `Camille Roux <camille@volteo.test>` → `camille@volteo.test`. */
export function bareAddress(from: string): string {
	const match = /<([^<>]+)>/.exec(from);
	return (match ? match[1] : from).trim();
}

/** `a@x.test, b@y.test` → two addresses. */
export function splitAddresses(text: string): string[] {
	return text
		.split(/[,;\s]+/)
		.map((address) => address.trim())
		.filter(Boolean);
}
