import { SvelteSet } from 'svelte/reactivity';
import { api } from '#lib/api/client.ts';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type CvPage = Schemas['CvPage'];
export type CvOptions = CvPage['options'];
export type OptionName = keyof CvOptions;

/** `missing`: selected items the server could not find in the PDF's text. */
export type Preview = { url: string; pages: number; missing: number; filename: string };

const path = { params: { path: { lang: 'fr' } } } as const;
const PREVIEW_DELAY_MS = 400;

function filenameOf(response: Response) {
	const header = response.headers.get('Content-Disposition') ?? '';
	return /filename="([^"]+)"/.exec(header)?.[1] ?? 'cv.pdf';
}

/** What goes on the page, and the real PDF of it. The choices live here until the server has them. */
export class CvPageEditor {
	status = $state<'loading' | 'ready' | 'unavailable'>('loading');
	page = $state.raw<CvPage | null>(null);
	excluded = new SvelteSet<string>();
	options = $state<CvOptions>({ photo: false, panneau_competences: true, loisirs: true });

	/** The last PDF produced. A failure leaves it in place. */
	preview = $state.raw<Preview | null>(null);
	refreshing = $state(false);
	failure = $state<string | null>(null);

	hasContent = $derived.by(() => {
		const page = this.page;
		if (!page) return false;
		return Boolean(
			page.resume ||
			page.experiences.length ||
			page.formation.length ||
			page.competences.length ||
			page.loisirs.length
		);
	});

	#timer: ReturnType<typeof setTimeout> | undefined;
	#running = false;
	#again = false;
	#savedKey = '';

	#key() {
		return JSON.stringify({ excluded: [...this.excluded].sort(), options: this.options });
	}

	async load() {
		this.status = 'loading';
		try {
			const { data } = await api.GET('/api/cv/{lang}/selection', path);
			if (!data) throw new Error('no selection');
			this.page = data;
			this.excluded.clear();
			for (const id of data.excluded_ids) this.excluded.add(id);
			this.options = data.options;
			this.#savedKey = this.#key();
			this.status = 'ready';
		} catch {
			this.status = 'unavailable';
			return;
		}
		if (this.hasContent) this.refresh();
	}

	isOn(id: string) {
		return !this.excluded.has(id);
	}

	setItem(id: string, on: boolean) {
		if (on) this.excluded.delete(id);
		else this.excluded.add(id);
		this.#changed();
	}

	setItems(ids: string[], on: boolean) {
		for (const id of ids) {
			if (on) this.excluded.delete(id);
			else this.excluded.add(id);
		}
		this.#changed();
	}

	setOption(name: OptionName, on: boolean) {
		this.options[name] = on;
		this.#changed();
	}

	#changed() {
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.refresh(), PREVIEW_DELAY_MS);
	}

	/** Stores the choices if they changed, then renders. One at a time: a change waits its turn. */
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
			await this.#sync();
		} while (this.#again);
		this.#running = false;
		this.refreshing = false;
	}

	async #sync() {
		try {
			if (!(await this.#store())) return;
			if (this.hasContent) await this.#render();
			else this.failure = null;
		} catch {
			this.failure = 'Le serveur ne répond pas. Vos choix sont intacts, l’aperçu reste le dernier.';
		}
	}

	async #store() {
		const key = this.#key();
		if (key === this.#savedKey) return true;
		const { data, error } = await api.PUT('/api/cv/{lang}/selection', {
			...path,
			body: {
				excluded_ids: [...this.excluded],
				options: $state.snapshot(this.options)
			}
		});
		if (!data) {
			this.failure = error && 'message' in error ? error.message : 'Ces choix sont refusés.';
			return false;
		}
		this.page = data;
		this.#savedKey = key;
		return true;
	}

	async #render() {
		const { data, error, response } = await api.GET('/api/cv/{lang}/pdf', {
			...path,
			parseAs: 'blob'
		});
		if (!data) {
			this.failure =
				error && 'message' in error ? error.message : 'Le PDF n’a pas pu être produit.';
			return;
		}
		this.failure = null;
		// Already out of date: the next round shows the newer one.
		if (this.#again) return;
		this.preview = {
			url: URL.createObjectURL(data),
			pages: Number(response.headers.get('X-Page-Count') ?? 0),
			missing: Number(response.headers.get('X-Missing-Items') ?? 0),
			filename: filenameOf(response)
		};
	}

	/** Leaving the screen before the delay is over must not lose the last tick. */
	flush() {
		if (this.#timer === undefined) return;
		clearTimeout(this.#timer);
		this.#timer = undefined;
		void this.#store().catch(() => {});
	}
}
