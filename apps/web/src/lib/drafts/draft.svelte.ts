import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { api } from '#lib/api/client.ts';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type DraftView = Schemas['DraftView'];
export type DraftItem = Schemas['DraftItem'];
export type DraftOptions = DraftView['options'];
export type OptionName = keyof DraftOptions;

/** `missing`: kept items the server could not find in the PDF's text. */
export type Preview = { url: string; pages: number; missing: number; filename: string };

const SAVE_DELAY_MS = 400;

function filenameOf(response: Response) {
	const header = response.headers.get('Content-Disposition') ?? '';
	return /filename="([^"]+)"/.exec(header)?.[1] ?? 'cv.pdf';
}

/** One adapted CV: the user's choices over the model's proposal, saved as they go, and
 * the real PDF of them. */
export class DraftEditor {
	status = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');
	draft = $state.raw<DraftView | null>(null);
	kept = new SvelteSet<string>();
	texts = new SvelteMap<string, string>();
	options = $state<DraftOptions>({ photo: false, panneau_competences: true, loisirs: false });

	preview = $state.raw<Preview | null>(null);
	refreshing = $state(false);
	failure = $state<string | null>(null);

	#id: number;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#running = false;
	#again = false;
	#savedKey = '';

	constructor(id: number) {
		this.#id = id;
	}

	#key() {
		return JSON.stringify({
			kept: [...this.kept].sort(),
			texts: [...this.texts.entries()].sort(),
			options: this.options
		});
	}

	#adopt(draft: DraftView) {
		this.draft = draft;
		this.kept.clear();
		this.texts.clear();
		const visit = (item: DraftItem) => {
			if (item.kept) this.kept.add(item.id);
			if (item.text !== item.original) this.texts.set(item.id, item.text);
		};
		if (draft.resume) visit(draft.resume);
		for (const experience of draft.experiences) {
			visit(experience);
			experience.bullets.forEach(visit);
		}
		[...draft.formation, ...draft.competences, ...draft.loisirs].forEach(visit);
		this.options = { ...draft.options };
		this.#savedKey = this.#key();
	}

	async load() {
		this.status = 'loading';
		try {
			const { data, response } = await api.GET('/api/cv/drafts/{draft_id}', {
				params: { path: { draft_id: this.#id } }
			});
			if (response.status === 404) {
				this.status = 'missing';
				return;
			}
			if (!data) throw new Error('no draft');
			this.#adopt(data);
			this.status = 'ready';
		} catch {
			this.status = 'unavailable';
			return;
		}
		this.refresh();
	}

	isKept(id: string) {
		return this.kept.has(id);
	}

	textOf(item: DraftItem) {
		return this.texts.get(item.id) ?? item.original;
	}

	setKept(id: string, on: boolean) {
		if (on) this.kept.add(id);
		else this.kept.delete(id);
		this.#changed();
	}

	/** The CV's own text clears the override. */
	setText(item: DraftItem, text: string) {
		const value = text.trim();
		if (!value || value === item.original.trim()) this.texts.delete(item.id);
		else this.texts.set(item.id, value);
		this.#changed();
	}

	setOption(name: OptionName, on: boolean) {
		this.options[name] = on;
		this.#changed();
	}

	#changed() {
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.refresh(), SAVE_DELAY_MS);
	}

	/** Saves the choices if they changed, then renders. One at a time: a change waits. */
	async refresh() {
		clearTimeout(this.#timer);
		this.#timer = undefined;
		if (this.#running) {
			this.#again = true;
			return;
		}
		this.#running = true;
		this.refreshing = true;
		do {
			this.#again = false;
			try {
				if (await this.#store()) await this.#render();
			} catch {
				this.failure =
					'Le serveur ne répond pas. Vos choix sont intacts, l’aperçu reste le dernier.';
			}
		} while (this.#again);
		this.#running = false;
		this.refreshing = false;
	}

	async #store() {
		const key = this.#key();
		if (key === this.#savedKey) return true;
		const { data, error } = await api.PUT('/api/cv/drafts/{draft_id}/choices', {
			params: { path: { draft_id: this.#id } },
			body: {
				kept_ids: [...this.kept],
				texts: Object.fromEntries(this.texts),
				options: $state.snapshot(this.options)
			}
		});
		if (!data) {
			this.failure = error && 'message' in error ? error.message : 'Ces choix sont refusés.';
			return false;
		}
		this.draft = data;
		this.#savedKey = key;
		return true;
	}

	async #render() {
		const { data, error, response } = await api.GET('/api/cv/drafts/{draft_id}/pdf', {
			params: { path: { draft_id: this.#id } },
			parseAs: 'blob'
		});
		if (!data) {
			this.failure =
				error && 'message' in error ? error.message : 'Le PDF n’a pas pu être produit.';
			return;
		}
		this.failure = null;
		if (this.#again) return;
		this.preview = {
			url: URL.createObjectURL(data),
			pages: Number(response.headers.get('X-Page-Count') ?? 0),
			missing: Number(response.headers.get('X-Missing-Items') ?? 0),
			filename: filenameOf(response)
		};
	}

	/** Leaving the screen before the delay is over must not lose the last change. */
	flush() {
		if (this.#timer === undefined) return;
		clearTimeout(this.#timer);
		this.#timer = undefined;
		void this.#store().catch(() => {});
	}
}
