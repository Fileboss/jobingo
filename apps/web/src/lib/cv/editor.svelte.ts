import { api } from '#lib/api/client.ts';
import type { components } from '#lib/api/schema.d.ts';
import type { CvDiagnostic } from './diagnostics.ts';

type Schemas = components['schemas'];
export type CvDocument = Schemas['CvDocument'];
export type CvFields = Schemas['CvFields'];
export type ExperienceFields = Schemas['ExperienceFields'];
export type CvMode = 'form' | 'text';

const lang = 'fr';
const path = { params: { path: { lang } } } as const;
const DIAGNOSTICS_DELAY_MS = 500;

const emptyFields = (): CvFields => ({
	front: '',
	resume: '',
	experiences: [],
	formation: [],
	skills: [],
	languages: [],
	hobbies: [],
	projects: [],
	before: '',
	others: [],
	order: []
});

export const emptyExperience = (): ExperienceFields => ({
	company: '',
	role: '',
	start: '',
	end: '',
	title: '',
	structured: true,
	tags: [],
	bullets: []
});

/** The CV being edited: one draft shown in two modes, and what the server last stored. */
export class CvEditor {
	status = $state<'loading' | 'ready' | 'unavailable'>('loading');
	mode = $state<CvMode>('form');
	text = $state('');
	fields = $state<CvFields>(emptyFields());

	/** Diagnostics of the draft, and the text their `line_no` refers to. */
	diagnostics = $state<CvDiagnostic[]>([]);
	diagnosticsText = $state('');

	stored = $state.raw<CvDocument | null>(null);
	conflict = $state.raw<CvDocument | null>(null);
	/** Refused by the server: only a duplicate id. Empty otherwise. */
	rejected = $state.raw<CvDiagnostic[]>([]);
	/** The API could not be reached for the action named here; the draft is intact. */
	failure = $state<'save' | 'switch' | null>(null);
	busy = $state<'save' | 'switch' | null>(null);
	/** A new CV stays on the empty state until the user starts writing. */
	started = $state(false);

	/** What the draft looked like when it last matched the stored CV. */
	#baseline = $state('');
	/** A mode switch rewrites the draft in the other view: it stays unsaved if it was. */
	#changedBeforeSwitch = $state(false);
	#timer: ReturnType<typeof setTimeout> | undefined;
	#diagnosticsRequest = 0;

	draftKey = $derived(this.mode === 'text' ? this.text : JSON.stringify(this.fields));
	dirty = $derived(this.#changedBeforeSwitch || this.draftKey !== this.#baseline);
	isEmpty = $derived(this.stored?.version === 0 && !this.started && !this.dirty);

	#draft(): Schemas['CvDraft'] {
		return this.mode === 'text'
			? { mode: 'text', text: this.text }
			: { mode: 'form', fields: $state.snapshot(this.fields) };
	}

	/** Replaces the draft with a document from the server: the draft now matches it. */
	#adopt(document: CvDocument) {
		this.stored = document;
		this.text = document.text;
		this.fields = document.fields;
		this.diagnostics = document.diagnostics;
		this.diagnosticsText = document.text;
		this.#changedBeforeSwitch = false;
		this.#baseline = this.draftKey;
		this.rejected = [];
		this.conflict = null;
		this.failure = null;
	}

	async load() {
		this.status = 'loading';
		try {
			const { data } = await api.GET('/api/cv/{lang}', path);
			if (!data) throw new Error('no document');
			this.#adopt(data);
			this.status = 'ready';
		} catch {
			this.status = 'unavailable';
		}
	}

	start(mode: CvMode) {
		this.started = true;
		this.mode = mode;
		this.#baseline = this.draftKey;
	}

	/** The UI makes the draft inert while `busy`, so nothing typed can be lost to the response. */
	async setMode(next: CvMode) {
		if (next === this.mode || this.busy) return;
		this.busy = 'switch';
		this.failure = null;
		clearTimeout(this.#timer);
		this.#diagnosticsRequest += 1;
		try {
			const { data } = await api.POST('/api/cv/{lang}/convert', {
				...path,
				body: { draft: this.#draft() }
			});
			if (!data) throw new Error('no view');
			this.text = data.text;
			this.fields = data.fields;
			this.diagnostics = data.diagnostics;
			this.diagnosticsText = data.text;
			this.mode = next;
			// The conversion gives the stored form, so it says whether anything really changed.
			this.#changedBeforeSwitch = data.text !== this.stored?.text;
			this.#baseline = this.draftKey;
		} catch {
			this.failure = 'switch';
		} finally {
			this.busy = null;
		}
	}

	/** Refreshes the diagnostics shortly after an edit, without touching what the user typed. */
	checkSoon() {
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.#check(), DIAGNOSTICS_DELAY_MS);
	}

	async #check() {
		const request = ++this.#diagnosticsRequest;
		try {
			const { data } = await api.POST('/api/cv/{lang}/convert', {
				...path,
				body: { draft: this.#draft() }
			});
			if (data && request === this.#diagnosticsRequest) {
				this.diagnostics = data.diagnostics;
				this.diagnosticsText = data.text;
			}
		} catch {
			// The diagnostics stay as they were; a save or a mode switch will report the failure.
		}
	}

	async save(expected = this.stored?.sha256 ?? null) {
		if (this.busy) return;
		this.busy = 'save';
		this.failure = null;
		this.rejected = [];
		clearTimeout(this.#timer);
		this.#diagnosticsRequest += 1;
		const sent = this.draftKey;
		try {
			const { data, error, response } = await api.PUT('/api/cv/{lang}', {
				...path,
				body: { draft: this.#draft(), expected_sha256: expected }
			});
			if (data && this.draftKey === sent) {
				this.#adopt(data);
			} else if (data) {
				// Typed during the save: the new input stays, as unsaved, on top of this version.
				this.stored = data;
				this.conflict = null;
				this.#changedBeforeSwitch = true;
			} else if (response.status === 409 && error && 'current' in error) {
				this.conflict = error.current;
			} else if (response.status === 400 && error && 'diagnostics' in error) {
				this.rejected = error.diagnostics;
			} else {
				this.failure = 'save';
			}
		} catch {
			this.failure = 'save';
		} finally {
			this.busy = null;
		}
	}

	/** Conflict: the user keeps their draft and it replaces what was stored elsewhere. */
	overwrite() {
		if (this.conflict) return this.save(this.conflict.sha256);
	}

	/** Conflict: the user drops their draft for the version stored elsewhere. */
	takeStored() {
		if (this.conflict) this.#adopt(this.conflict);
	}
}
