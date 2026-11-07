import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type ApplicationSummary = Schemas['ApplicationSummary'];
export type ApplicationView = Schemas['ApplicationView'];
export type ApplicationEvent = Schemas['ApplicationEvent'];
export type Status = ApplicationSummary['status'];
export type EventType = ApplicationEvent['type'];
export type Tone = ApplicationSummary['tone'];

export const statusLabels: Record<Status, string> = {
	a_postuler: 'À postuler',
	postule: 'Postulé',
	en_echange: 'En échange',
	entretien: 'Entretien',
	offre: 'Offre',
	cloture: 'Clôturé'
};

export const eventLabels: Record<EventType, string> = {
	applied: 'Candidature envoyée',
	message_received: 'Message reçu',
	message_sent: 'Message envoyé',
	interview_scheduled: 'Entretien planifié',
	interview_done: 'Entretien passé',
	offer_received: 'Offre reçue',
	rejected: 'Refus',
	withdrawn: 'Candidature retirée',
	note: 'Note'
};

/** The bristol colour of a status: yellow to do, blue running, green at the end, red lost. */
export const toneClasses: Record<Tone, string> = {
	todo: 'bg-bristol-yellow',
	active: 'bg-bristol-blue',
	final: 'bg-bristol-green',
	lost: 'bg-bristol-salmon'
};

const day = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });

/** A calendar date (`2026-11-07`), read as a local date. */
export function formatDate(iso: string): string {
	const [y, m, d] = iso.split('-').map(Number);
	return day.format(new Date(y, m - 1, d));
}

export function today(): string {
	const now = new Date();
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
