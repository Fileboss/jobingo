<script lang="ts">
	import Button from '#lib/ui/Button.svelte';
	import RuledArea from '#lib/ui/RuledArea.svelte';
	import TextField from '#lib/ui/TextField.svelte';
	import type { ExperienceFields } from './editor.svelte.ts';

	type Props = {
		experience: ExperienceFields;
		flagged: boolean;
		first: boolean;
		last: boolean;
		onmove: (delta: number) => void;
		onremove: () => void;
		autofocus?: boolean;
	};
	let { experience, flagged, first, last, onmove, onremove, autofocus = false }: Props = $props();

	let name = $derived(experience.structured ? experience.company : experience.title);
	let heading = $derived(name.trim() || 'nouvelle expérience');
	let titleField = $state<HTMLInputElement>();

	$effect(() => {
		if (autofocus) titleField?.focus();
	});

	// A free title that the server could not split: the user can turn it into a company.
	function detail() {
		experience.company = experience.title;
		experience.title = '';
		experience.structured = true;
	}
</script>

<article class="grid gap-x-6 gap-y-2 py-4 sm:grid-cols-[13rem_minmax(0,1fr)]">
	<div class="grid content-start gap-1">
		{#if experience.structured}
			<TextField
				bind:value={experience.company}
				bind:element={titleField}
				label="Entreprise"
				placeholder="Entreprise"
				class="text-[1.375rem] font-extrabold"
			/>
			<TextField bind:value={experience.role} label="Poste de {heading}" placeholder="Poste" />
			<div class="grid grid-cols-2 gap-2">
				<TextField bind:value={experience.start} label="Début de {heading}" placeholder="Début" />
				<TextField bind:value={experience.end} label="Fin de {heading}" placeholder="Fin" />
			</div>
		{:else}
			<TextField
				bind:value={experience.title}
				bind:element={titleField}
				label="Intitulé"
				placeholder="Intitulé"
				class="text-[1.375rem] font-extrabold"
			/>
			<Button variant="quiet" class="w-fit !px-0 text-sm" onclick={detail}>
				Détailler l’intitulé
			</Button>
		{/if}
		<TextField
			bind:value={
				() => experience.tags.join(' '), (value) => (experience.tags = value.split(/\s+/))
			}
			label="Mots-clés de {heading}"
			placeholder="Mots-clés"
			class="text-[0.9375rem] opacity-80"
		/>
		{#if flagged}
			<p class="w-fit bg-postit px-2 text-sm font-bold">À vérifier</p>
		{/if}
		<div class="-ml-2 flex flex-wrap text-sm">
			<Button
				variant="quiet"
				disabled={first}
				aria-label="Monter {heading}"
				class="disabled:invisible"
				onclick={() => onmove(-1)}>Monter</Button
			>
			<Button
				variant="quiet"
				disabled={last}
				aria-label="Descendre {heading}"
				class="disabled:invisible"
				onclick={() => onmove(1)}>Descendre</Button
			>
			<Button variant="quiet" aria-label="Retirer {heading}" onclick={onremove}>Retirer</Button>
		</div>
	</div>
	<RuledArea
		bind:value={
			() => experience.bullets.join('\n'), (value) => (experience.bullets = value.split('\n'))
		}
		label="Réalisations de {heading}, une par ligne"
		placeholder="Une réalisation par ligne, avec #mot-clé à la fin si besoin"
		rows={3}
	/>
</article>
