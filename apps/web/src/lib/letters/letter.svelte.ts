import { SvelteMap } from 'svelte/reactivity';
import { api } from '#lib/api/client.ts';
import type { components } from '#lib/api/schema.d.ts';

export type LetterView = components['schemas']['LetterView'];
export type SlotView = LetterView['slots'][number];
export type Preview = { url: string; pages: number; filename: string };

const SAVE_DELAY_MS = 500;

function filenameOf(response: Response) {
	const header = response.headers.get('Content-Disposition') ?? '';
	return /filename="([^"]+)"/.exec(header)?.[1] ?? 'lettre.pdf';
}

/** One letter: the user's texts over the model's proposal, saved as they type, and the
 * real PDF of them. */
export class LetterEditor {
	status = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');
	letter = $state.raw<LetterView | null>(null);
	texts = new SvelteMap<string, string>();
	recipient = $state('');
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
		return JSON.stringify({ texts: [...this.texts.entries()].sort(), recipient: this.recipient });
	}

	#adopt(letter: LetterView) {
		this.letter = letter;
		this.texts.clear();
		for (const slot of letter.slots) this.texts.set(slot.name, slot.text);
		this.recipient = letter.recipient;
		this.#savedKey = this.#key();
	}

	async load() {
		this.status = 'loading';
		try {
			const { data, response } = await api.GET('/api/letters/{letter_id}', {
				params: { path: { letter_id: this.#id } }
			});
			if (response.status === 404) {
				this.status = 'missing';
				return;
			}
			if (!data) throw new Error('no letter');
			this.#adopt(data);
			this.status = 'ready';
		} catch {
			this.status = 'unavailable';
			return;
		}
		this.refresh();
	}

	setText(name: string, text: string) {
		this.texts.set(name, text);
		this.#changed();
	}

	setRecipient(value: string) {
		this.recipient = value;
		this.#changed();
	}

	#changed() {
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.refresh(), SAVE_DELAY_MS);
	}

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
					'Le serveur ne répond pas. Vos textes sont intacts, l’aperçu reste le dernier.';
			}
		} while (this.#again);
		this.#running = false;
		this.refreshing = false;
	}

	async #store() {
		const key = this.#key();
		if (key === this.#savedKey) return true;
		const { data } = await api.PUT('/api/letters/{letter_id}/texts', {
			params: { path: { letter_id: this.#id } },
			body: { texts: Object.fromEntries(this.texts), recipient: this.recipient }
		});
		if (!data) {
			this.failure = 'Ces textes sont refusés.';
			return false;
		}
		// Keep what is typed: only the server's checks are taken from the answer.
		this.letter = data;
		this.#savedKey = key;
		return true;
	}

	async #render() {
		const { data, error, response } = await api.GET('/api/letters/{letter_id}/pdf', {
			params: { path: { letter_id: this.#id } },
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
			filename: filenameOf(response)
		};
	}

	flush() {
		if (this.#timer === undefined) return;
		clearTimeout(this.#timer);
		this.#timer = undefined;
		void this.#store().catch(() => {});
	}
}
