import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type UsageReport = Schemas['UsageReport'];
export type UsageFigures = Schemas['UsageFigures'];
export type CallSummary = Schemas['CallSummary'];
export type CallDetail = Schemas['CallDetail'];
export type AppEvent = Schemas['AppEvent'];
export type CallStatus = CallSummary['status'];
export type EventLevel = AppEvent['level'];

const integer = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat('fr-FR', { style: 'percent', maximumFractionDigits: 1 });

/** Costs travel as decimal strings, so that no figure is rounded on the way. */
export const usd = (value: string | number) => Number(value);

/** Small costs keep their significant digits: 0,0012 $ is not 0,00 $. */
export function formatUsd(value: string | number): string {
	const amount = usd(value);
	const digits = amount === 0 ? 0 : amount >= 1 ? 2 : amount >= 0.01 ? 3 : 4;
	const text = new Intl.NumberFormat('fr-FR', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	}).format(amount);
	return `${text} $`;
}

export const formatCount = (value: number) =>
	value >= 10_000 ? compact.format(value) : integer.format(value);

export const formatInteger = (value: number) => integer.format(value);

/** A share of a total, or nothing when there is no total to divide. */
export function formatShare(part: number, whole: number): string {
	return whole > 0 ? percent.format(part / whole) : '—';
}

export function formatMs(value: number | null | undefined): string {
	if (value === null || value === undefined) return '—';
	return value >= 10_000
		? `${(value / 1000).toFixed(0)} s`
		: value >= 1000
			? `${(value / 1000).toFixed(1).replace('.', ',')} s`
			: `${integer.format(value)} ms`;
}

const dateTime = new Intl.DateTimeFormat('fr-FR', {
	day: 'numeric',
	month: 'short',
	hour: '2-digit',
	minute: '2-digit'
});
const seconds = new Intl.DateTimeFormat('fr-FR', {
	day: 'numeric',
	month: 'short',
	hour: '2-digit',
	minute: '2-digit',
	second: '2-digit'
});
const day = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' });
const longDay = new Intl.DateTimeFormat('fr-FR', {
	weekday: 'long',
	day: 'numeric',
	month: 'long'
});

export const formatDateTime = (iso: string) => dateTime.format(new Date(iso));
export const formatTimestamp = (iso: string) => seconds.format(new Date(iso));
/** `day` is a calendar date (`2026-11-07`), read as a local date, not as UTC midnight. */
const localDate = (iso: string) => {
	const [y, m, d] = iso.split('-').map(Number);
	return new Date(y, m - 1, d);
};
export const formatDay = (iso: string) => day.format(localDate(iso));
export const formatLongDay = (iso: string) => longDay.format(localDate(iso));

/** Share of the prompt read from the cache, at a fraction of the input price. */
export function cacheHitRate(figures: UsageFigures): string {
	const prompt = figures.input_tokens + figures.cache_read_tokens + figures.cache_write_tokens;
	return formatShare(figures.cache_read_tokens, prompt);
}

export const statusLabels: Record<CallStatus, string> = {
	ok: 'Réussi',
	failed: 'Invalide',
	error: 'API indisponible'
};

export const levelLabels: Record<EventLevel, string> = {
	DEBUG: 'Détail',
	INFO: 'Info',
	WARNING: 'Alerte',
	ERROR: 'Erreur',
	CRITICAL: 'Critique'
};

export const tierLabels = { fast: 'Rapide', writing: 'Rédaction' } as const;
