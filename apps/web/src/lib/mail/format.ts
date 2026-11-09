import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type MessageSummary = Schemas['MessageSummary'];
export type Message = Schemas['Message'];
export type MailboxStatus = Schemas['MailboxStatus'];
export type SyncReport = Schemas['SyncReport'];
export type MessageKind = NonNullable<MessageSummary['kind']>;
export type Category = NonNullable<MessageSummary['category']>;
export type HiddenReason = NonNullable<MessageSummary['hidden_reason']>;

/** What the model read in a message, as the list shows it. */
export const categoryLabels: Record<Category, string> = {
	offer: 'Offre',
	rejection: 'Refus',
	interview: 'Entretien',
	recruiter_other: 'Recruteur',
	other: 'Autre'
};

export const hiddenReasons: Record<HiddenReason, string> = {
	newsletter: 'Lettre d’information : masquée sans passer par l’IA.',
	blocked_sender: 'Expéditeur bloqué : masqué sans passer par l’IA.',
	other: 'Classé « autre » par l’IA : sans rapport avec la recherche.',
	user: 'Masqué par vous.'
};

export const suggestionLabels: Record<NonNullable<MessageSummary['suggestion']>['type'], string> = {
	rejected: 'Refus',
	interview_scheduled: 'Entretien prévu'
};

/** Waiting for the user: a suggestion to decide, or news of an application to tie. */
export function needsAttention(message: MessageSummary): boolean {
	if (message.hidden_reason) return false;
	if (message.suggestion?.status === 'pending') return true;
	if (message.category === 'offer') return message.offer_count === 0;
	return (
		message.application_id === null &&
		(message.category === 'rejection' ||
			message.category === 'interview' ||
			message.category === 'recruiter_other')
	);
}

/** `Camille Roux <camille@volteo.test>` → `Camille Roux`; a bare address stays. */
export function senderName(from: string): string {
	const match = /^\s*"?([^"<]*?)"?\s*<[^>]+>\s*$/.exec(from);
	return match && match[1] ? match[1] : from;
}

const plural = (count: number, one: string, many: string) => `${count} ${count > 1 ? many : one}`;

/** What a sync did, in one sentence. */
export function syncSummary(report: SyncReport): string {
	const parts = [
		report.fetched === 0
			? 'Aucun nouveau message'
			: plural(report.fetched, 'nouveau message', 'nouveaux messages')
	];
	if (report.classified) parts.push(plural(report.classified, 'classé', 'classés'));
	if (report.linked) parts.push(plural(report.linked, 'rattaché', 'rattachés'));
	if (report.hidden) parts.push(plural(report.hidden, 'masqué', 'masqués'));
	if (report.offer_ids.length) {
		const scored = report.offer_ids.length - report.unscored_ids.length;
		parts.push(
			plural(report.offer_ids.length, 'offre lue', 'offres lues') +
				(scored ? `, dont ${plural(scored, 'notée', 'notées')}` : '')
		);
	}
	return parts.join(' · ') + '.';
}
