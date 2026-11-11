import { api } from '#lib/api/client.ts';
import type { components } from '#lib/api/schema.d.ts';

type Schemas = components['schemas'];
export type IdentityDocument = Schemas['IdentityDocument'];
export type IdentityFields = Schemas['Identity'];

const unreachable =
	'Le serveur ne répond pas. Votre saisie est intacte, réessayez dans un instant.';

/** The fields of the identity form, in the order the screen shows them. */
export const identityFields: {
	key: keyof IdentityFields;
	label: string;
	missing: string;
	type?: 'email' | 'tel' | 'url';
	autocomplete: 'name' | 'email' | 'tel' | 'street-address' | 'off';
	placeholder?: string;
}[] = [
	{ key: 'name', label: 'Nom complet', missing: 'le nom', autocomplete: 'name' },
	{ key: 'email', label: 'E-mail', missing: 'l’e-mail', type: 'email', autocomplete: 'email' },
	{ key: 'phone', label: 'Téléphone', missing: 'le téléphone', type: 'tel', autocomplete: 'tel' },
	{ key: 'address', label: 'Adresse', missing: 'l’adresse', autocomplete: 'street-address' },
	{
		key: 'website',
		label: 'Site web',
		missing: 'le site web',
		autocomplete: 'off',
		placeholder: 'monsite.fr'
	},
	{
		key: 'linkedin',
		label: 'LinkedIn',
		missing: 'LinkedIn',
		autocomplete: 'off',
		placeholder: 'linkedin.com/in/… ou votre nom d’utilisateur'
	},
	{
		key: 'github',
		label: 'GitHub',
		missing: 'GitHub',
		autocomplete: 'off',
		placeholder: 'github.com/… ou votre nom d’utilisateur'
	}
];

/** What the PDF will leave out, in words: `null` when nothing is missing. */
export function missingFields(identity: IdentityFields): string | null {
	const missing = identityFields.filter((field) => !identity[field.key].trim());
	if (!missing.length) return null;
	const words = missing.map((field) => field.missing);
	const last = words.pop();
	return words.length ? `${words.join(', ')} et ${last}` : (last as string);
}

function toFields({ name, email, phone, address, website, linkedin, github }: IdentityDocument) {
	return { name, email, phone, address, website, linkedin, github };
}

function readBase64(file: File): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => resolve((reader.result as string).split(',')[1] ?? '');
		reader.onerror = () => reject(reader.error);
		reader.readAsDataURL(file);
	});
}

/** The identity being edited. A photo is stored as soon as it is chosen, the fields on a save. */
export class IdentityEditor {
	status = $state<'loading' | 'ready' | 'unavailable'>('loading');
	fields = $state<IdentityFields>({
		name: '',
		email: '',
		phone: '',
		address: '',
		website: '',
		linkedin: '',
		github: ''
	});
	hasPhoto = $state(false);
	/** Changes after each upload, to refresh the thumbnail. */
	photoVersion = $state(0);
	busy = $state<'save' | 'photo' | null>(null);
	saved = $state(false);
	failure = $state<string | null>(null);
	photoFailure = $state<string | null>(null);

	#baseline = $state('');
	draftKey = $derived(JSON.stringify(this.fields));
	dirty = $derived(this.draftKey !== this.#baseline);

	#adopt(document: IdentityDocument) {
		this.fields = toFields(document);
		this.#baseline = this.draftKey;
		this.hasPhoto = document.has_photo;
	}

	async load() {
		this.status = 'loading';
		try {
			const { data } = await api.GET('/api/identity');
			if (!data) throw new Error('no identity');
			this.#adopt(data);
			this.status = 'ready';
		} catch {
			this.status = 'unavailable';
		}
	}

	async save() {
		if (this.busy) return;
		this.busy = 'save';
		this.failure = null;
		this.saved = false;
		const sent = this.draftKey;
		try {
			const { data } = await api.PUT('/api/identity', { body: $state.snapshot(this.fields) });
			if (!data) throw new Error('not saved');
			// Typed during the save: the new input stays, as unsaved.
			if (this.draftKey === sent) this.#adopt(data);
			else this.#baseline = sent;
			this.saved = true;
		} catch {
			this.failure = unreachable;
		} finally {
			this.busy = null;
		}
	}

	async uploadPhoto(file: File) {
		if (this.busy) return;
		this.busy = 'photo';
		this.photoFailure = null;
		try {
			const { data, error } = await api.PUT('/api/identity/photo', {
				body: { data_base64: await readBase64(file) }
			});
			if (data) {
				this.hasPhoto = data.has_photo;
				this.photoVersion += 1;
			} else {
				this.photoFailure =
					error && 'message' in error ? error.message : 'Cette photo n’a pas pu être enregistrée.';
			}
		} catch {
			this.photoFailure = 'Le serveur ne répond pas. La photo n’a pas été enregistrée.';
		} finally {
			this.busy = null;
		}
	}

	async removePhoto() {
		if (this.busy) return;
		this.busy = 'photo';
		this.photoFailure = null;
		try {
			const { data } = await api.DELETE('/api/identity/photo');
			if (!data) throw new Error('not removed');
			this.hasPhoto = data.has_photo;
		} catch {
			this.photoFailure = 'Le serveur ne répond pas. La photo n’a pas été retirée.';
		} finally {
			this.busy = null;
		}
	}
}
