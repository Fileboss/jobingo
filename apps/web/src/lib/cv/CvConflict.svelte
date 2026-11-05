<script lang="ts">
	import Button from '#lib/ui/Button.svelte';
	import type { CvDocument } from './editor.svelte.ts';
	import { savedOn } from './format.ts';

	type Props = {
		stored: CvDocument;
		disabled: boolean;
		ontake: () => void;
		onoverwrite: () => void;
	};
	let { stored, disabled, ontake, onoverwrite }: Props = $props();
</script>

<div role="alert" class="mb-6 bg-ink px-5 py-4 text-white">
	<p class="font-extrabold">Ce CV a été modifié ailleurs pendant que vous écriviez.</p>
	<p class="mt-1">
		La version {stored.version}, enregistrée {savedOn(stored.updated_at)}, est plus récente que
		celle que vous avez ouverte. Rien n’a été enregistré et votre saisie est intacte : choisissez
		laquelle garder.
	</p>
	<div class="mt-3 flex flex-wrap gap-3">
		<Button variant="inverse" {disabled} onclick={onoverwrite}>Remplacer par ma saisie</Button>
		<Button variant="inverse" {disabled} onclick={ontake}>Abandonner ma saisie</Button>
	</div>
	<details class="mt-3">
		<summary class="cursor-pointer font-bold">Voir la version enregistrée</summary>
		<pre
			class="mt-2 max-h-80 overflow-auto bg-paper p-3 font-mono text-sm text-ink">{stored.text}</pre>
	</details>
</div>
