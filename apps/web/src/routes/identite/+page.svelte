<script lang="ts">
	import { onMount } from 'svelte';
	import { IdentityEditor, identityFields } from '#lib/identity/editor.svelte.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	const editor = new IdentityEditor();
	let picker = $state<HTMLInputElement>();

	onMount(() => {
		editor.load();
	});

	let status = $derived.by(() => {
		if (editor.busy === 'save') return 'Enregistrement…';
		if (editor.dirty) return 'Modifications non enregistrées';
		if (editor.saved) return 'Identité enregistrée';
		return '';
	});

	function onkeydown(event: KeyboardEvent) {
		if ((event.metaKey || event.ctrlKey) && event.key === 's') {
			event.preventDefault();
			if (editor.dirty) editor.save();
		}
	}

	function onbeforeunload(event: BeforeUnloadEvent) {
		if (editor.dirty) event.preventDefault();
	}

	async function onpick(event: Event & { currentTarget: HTMLInputElement }) {
		const input = event.currentTarget;
		const file = input.files?.[0];
		if (file) await editor.uploadPhoto(file);
		// The same file can then be chosen again.
		input.value = '';
	}
</script>

<svelte:head>
	<title>Identité | Jobingo</title>
</svelte:head>

<svelte:window {onkeydown} {onbeforeunload} />

<div class="flex-1 px-3 pt-2 pb-12 sm:px-6">
	<div class="mx-auto max-w-232">
		<h1 class="mb-5 text-5xl leading-tight font-extrabold text-ink">Identité</h1>

		{#if editor.status === 'loading'}
			<p class="text-ink-soft" role="status">Ouverture de la fiche…</p>
		{:else if editor.status === 'unavailable'}
			<div role="alert" class="bg-paper px-5 py-8">
				<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
				<p class="mt-1 mb-4">
					Votre identité n’a pas pu être chargée. Vérifiez que l’API tourne, puis :
				</p>
				<Button onclick={() => editor.load()}>Réessayer</Button>
			</div>
		{:else}
			{#if editor.failure}
				<p role="alert" class="mb-6 bg-alert px-5 py-3 font-bold text-white">{editor.failure}</p>
			{/if}

			<BristolCard title="Coordonnées" colour="grey">
				<p class="mb-5 max-w-2xl">
					Rangées à part du CV. Le code les ajoute au moment de produire le PDF, et elles ne font
					pas partie de ce que le modèle reçoit. Un champ vide est simplement absent du PDF.
				</p>
				<div class="grid gap-x-10 gap-y-6 md:grid-cols-[minmax(0,1fr)_11rem]">
					<div class="grid content-start gap-4 sm:grid-cols-2 sm:gap-x-8">
						{#each identityFields as field (field.key)}
							<label
								class={[
									'block',
									(field.key === 'name' || field.key === 'address') && 'sm:col-span-2'
								]}
							>
								<span class="text-sm font-bold">{field.label}</span>
								<input
									bind:value={editor.fields[field.key]}
									type={field.type ?? 'text'}
									autocomplete={field.autocomplete}
									placeholder={field.placeholder}
									maxlength={300}
									class="block w-full border-0 border-b border-ink/40 bg-transparent px-0 py-1 font-medium text-ink placeholder:text-ink-soft focus:border-ink focus:ring-0"
								/>
							</label>
						{/each}
					</div>

					<div>
						<p class="mb-1 text-sm font-bold">Photo</p>
						<div class="grid aspect-[4/5] place-items-center overflow-hidden bg-paper shadow-sm">
							{#if editor.hasPhoto}
								<img
									src="/api/identity/photo?v={editor.photoVersion}"
									alt="Votre portrait"
									class="size-full object-cover"
								/>
							{:else}
								<p class="px-4 text-center text-sm text-ink-soft">Pas de photo</p>
							{/if}
						</div>
						<input
							bind:this={picker}
							type="file"
							accept="image/jpeg,image/png"
							aria-label="Choisir une photo"
							class="sr-only"
							onchange={onpick}
						/>
						<div class="mt-2 -ml-2 flex flex-wrap text-sm">
							<Button
								variant="quiet"
								disabled={editor.busy === 'photo'}
								onclick={() => picker?.click()}
							>
								{editor.hasPhoto ? 'Remplacer' : 'Ajouter une photo'}
							</Button>
							{#if editor.hasPhoto}
								<Button
									variant="quiet"
									disabled={editor.busy === 'photo'}
									onclick={() => editor.removePhoto()}>Retirer</Button
								>
							{/if}
						</div>
						{#if editor.busy === 'photo'}
							<p role="status" class="mt-1 text-sm">Envoi de la photo…</p>
						{/if}
						{#if editor.photoFailure}
							<p role="alert" class="mt-2 bg-alert px-3 py-2 text-sm font-bold text-white">
								{editor.photoFailure}
							</p>
						{:else}
							<p class="mt-1 text-sm text-ink-soft">
								JPEG ou PNG, 8 Mo au plus. Les métadonnées sont retirées à l’enregistrement.
							</p>
						{/if}
					</div>
				</div>
			</BristolCard>
		{/if}
	</div>
</div>

{#if editor.status === 'ready'}
	<footer
		class="sticky bottom-0 z-10 flex flex-wrap items-center justify-end gap-x-5 gap-y-1 border-t-3 border-ink bg-paper px-4 py-2.5 sm:px-6"
	>
		<p role="status">{status}</p>
		<Button disabled={!editor.dirty || editor.busy !== null} onclick={() => editor.save()}>
			Enregistrer
		</Button>
	</footer>
{/if}
