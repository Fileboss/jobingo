import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type MessageSummary = Schemas['MessageSummary'];
export type Message = Schemas['Message'];
export type MailboxStatus = Schemas['MailboxStatus'];
export type SyncReport = Schemas['SyncReport'];
export type MessageKind = NonNullable<MessageSummary['kind']>;

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
	if (report.offer_ids.length) {
		const scored = report.offer_ids.length - report.unscored_ids.length;
		parts.push(
			plural(report.offer_ids.length, 'offre lue', 'offres lues') +
				(scored ? `, dont ${plural(scored, 'notée', 'notées')}` : '')
		);
	}
	return parts.join(' · ') + '.';
}
