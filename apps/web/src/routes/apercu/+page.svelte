<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import { missingFields } from '#lib/identity/editor.svelte.ts';
	import ChipChoices from '#lib/preview/ChipChoices.svelte';
	import ExperienceChoice from '#lib/preview/ExperienceChoice.svelte';
	import PageOptions from '#lib/preview/PageOptions.svelte';
	import { CvPageEditor } from '#lib/preview/page.svelte.ts';
	import PdfSheet from '#lib/preview/PdfSheet.svelte';
	import { sectionId } from '#lib/cv/sections.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';
	import Tick from '#lib/ui/Tick.svelte';

	/** The most recent experiences start unfolded; a long career stays short to scan. */
	const OPEN_EXPERIENCES = 3;

	const editor = new CvPageEditor();
	let missing = $state<string | null>(null);

	onMount(async () => {
		editor.load();
		try {
			const { data } = await api.GET('/api/identity');
			if (data) missing = missingFields(data);
		} catch {
			// The note is only a help: the preview reports an API that is down.
		}
	});

	onDestroy(() => editor.flush());

	let page = $derived(editor.page);
	let previewPages = $derived(editor.preview?.pages ?? 0);
	let missingItems = $derived(editor.preview?.missing ?? 0);
	let overflow = $derived(page !== null && previewPages > page.max_pages);
	// Only a PDF that fits, and that matches the choices on screen, can leave.
	let canDownload = $derived(
		editor.preview !== null && !overflow && !editor.refreshing && !editor.failure
	);

	const tally = (ids: string[]) =>
		`${ids.filter((id) => editor.isOn(id)).length} sur ${ids.length}`;
	const idsOf = (items: { id: string }[]) => items.map((item) => item.id);
</script>

<svelte:head>
	<title>Aperçu | Jobingo</title>
</svelte:head>

{#snippet allOrNone(ids: string[], name: string)}
	<div class="-mt-2 mb-2 -ml-2 flex text-sm">
		<Button
			variant="quiet"
			aria-label="Tout cocher : {name}"
			disabled={ids.every((id) => editor.isOn(id))}
			class="disabled:text-ink-soft disabled:no-underline"
			onclick={() => editor.setItems(ids, true)}>Tout cocher</Button
		>
		<Button
			variant="quiet"
			aria-label="Tout décocher : {name}"
			disabled={ids.every((id) => !editor.isOn(id))}
			class="disabled:text-ink-soft disabled:no-underline"
			onclick={() => editor.setItems(ids, false)}>Tout décocher</Button
		>
	</div>
{/snippet}

<div class="flex-1 px-3 pt-2 pb-12 sm:px-6">
	{#if editor.status === 'loading'}
		<h1 class="mb-5 text-5xl leading-tight font-extrabold text-ink">Aperçu</h1>
		<p class="text-ink-soft" role="status">Préparation de la page…</p>
	{:else if editor.status === 'unavailable'}
		<h1 class="mb-5 text-5xl leading-tight font-extrabold text-ink">Aperçu</h1>
		<div role="alert" class="bg-paper px-5 py-8">
			<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
			<p class="mt-1 mb-4">
				La sélection n’a pas pu être chargée. Vérifiez que l’API tourne, puis :
			</p>
			<Button onclick={() => editor.load()}>Réessayer</Button>
		</div>
	{:else if page && !editor.hasContent}
		<h1 class="mb-5 text-5xl leading-tight font-extrabold text-ink">Aperçu</h1>
		<div class="bg-paper px-5 py-10 sm:px-10">
			<h2 class="text-3xl font-extrabold text-ink">Rien à mettre en page</h2>
			<p class="mt-3 mb-6 max-w-xl text-xl leading-normal">
				Le classeur est vide. Notez votre parcours dans « Mon CV » : vous choisirez ici ce qui va
				sur la page.
			</p>
			<a
				href={resolve('/cv')}
				class="rounded-sm bg-ink px-5 py-1.5 font-extrabold text-white no-underline hover:bg-ink-deep"
			>
				Remplir mon CV
			</a>
		</div>
	{:else if page}
		<div class="mx-auto grid max-w-[96rem] gap-x-8 gap-y-6 xl:grid-cols-[minmax(0,1fr)_auto]">
			<div class="min-w-0">
				<h1 class="mb-5 text-5xl leading-tight font-extrabold text-ink">Aperçu</h1>

				{#if missing}
					<p
						class="mb-6 max-w-xl bg-postit px-4 py-3 leading-snug shadow-[0_6px_12px_-8px_var(--color-ink-deep)] xl:-rotate-1"
					>
						<span class="font-bold">Absents du PDF : {missing}.</span>
						<a href={resolve('/identite')} class="whitespace-nowrap underline underline-offset-4">
							Compléter l’identité
						</a>
					</p>
				{/if}

				<div class="grid gap-6">
					<PageOptions {editor} />

					{#if page.resume}
						{@const resume = page.resume}
						{@const on = editor.isOn(resume.id)}
						<BristolCard
							title="Résumé"
							colour="yellow"
							tab={0}
							id={sectionId.resume}
							note={on ? 'sur la page' : 'retiré de la page'}
						>
							<Tick checked={on} onchange={(value) => editor.setItem(resume.id, value)}>
								<span class={['max-w-prose font-medium', !on && 'text-ink-soft line-through']}
									>{resume.text}</span
								>
							</Tick>
						</BristolCard>
					{/if}

					{#if page.experiences.length}
						{@const ids = idsOf(page.experiences)}
						<BristolCard
							title="Expériences"
							colour="blue"
							tab={1}
							id={sectionId.experiences}
							note={tally(ids)}
						>
							{@render allOrNone(ids, 'expériences')}
							<div class="divide-y divide-ink/40">
								{#each page.experiences as experience, index (experience.id)}
									<ExperienceChoice {editor} {experience} open={index < OPEN_EXPERIENCES} />
								{/each}
							</div>
						</BristolCard>
					{/if}

					{#if page.formation.length}
						{@const ids = idsOf(page.formation)}
						<BristolCard
							title="Formation"
							colour="green"
							tab={2}
							id={sectionId.formation}
							note={tally(ids)}
						>
							{@render allOrNone(ids, 'formation')}
							<ul class="grid gap-1.5">
								{#each page.formation as item (item.id)}
									{@const on = editor.isOn(item.id)}
									<li>
										<Tick checked={on} onchange={(value) => editor.setItem(item.id, value)}>
											<span
												class={[
													item.heading ? 'font-extrabold' : 'font-medium',
													!on && 'text-ink-soft line-through'
												]}>{item.text}</span
											>
										</Tick>
									</li>
								{/each}
							</ul>
						</BristolCard>
					{/if}

					{#if page.competences.length}
						{@const ids = idsOf(page.competences)}
						<BristolCard
							title="Compétences"
							colour="salmon"
							tab={3}
							id={sectionId.competences}
							note={tally(ids)}
						>
							{@render allOrNone(ids, 'compétences')}
							<ChipChoices {editor} items={page.competences} label="Compétences" />
						</BristolCard>
					{/if}

					{#if page.loisirs.length}
						{@const ids = idsOf(page.loisirs)}
						<BristolCard
							title="Loisirs"
							colour="lilac"
							tab={4}
							id={sectionId.loisirs}
							note={tally(ids)}
						>
							{#if editor.options.loisirs}
								{@render allOrNone(ids, 'loisirs')}
							{:else}
								<p class="-mt-2 mb-2 text-sm font-bold">
									L’option Loisirs est décochée : cette section n’est pas sur la page.
								</p>
							{/if}
							<ChipChoices {editor} items={page.loisirs} label="Loisirs" />
						</BristolCard>
					{/if}
				</div>
			</div>

			<aside
				aria-label="Aperçu du PDF"
				class="self-start max-xl:row-start-auto xl:sticky xl:top-3 xl:w-[calc((100dvh-7.5rem)*210/297)]"
			>
				<div class="mb-2 flex min-h-10 flex-wrap items-center justify-between gap-x-4 gap-y-1">
					<p role="status" class="font-bold text-ink">
						{#if editor.refreshing}
							Mise à jour…
						{:else if editor.preview}
							{previewPages} page{previewPages > 1 ? 's' : ''}
						{/if}
					</p>
					{#if editor.preview && canDownload}
						<!-- eslint-disable svelte/no-navigation-without-resolve -- a blob, not a route -->
						<a
							href={editor.preview.url}
							download={editor.preview.filename}
							class="rounded-sm bg-ink px-4 py-1.5 font-extrabold text-white no-underline hover:bg-ink-deep"
						>
							Télécharger le PDF
						</a>
						<!-- eslint-enable svelte/no-navigation-without-resolve -->
					{:else if editor.preview}
						<span class="px-4 py-1.5 font-bold text-ink-soft" data-testid="no-download">
							Téléchargement indisponible
						</span>
					{/if}
				</div>

				{#if overflow}
					<p class="mb-2 bg-postit px-4 py-2 leading-snug" data-testid="overflow">
						<span class="font-bold"
							>Le CV fait {previewPages} pages : il doit tenir sur une seule.</span
						>
						Décochez quelques lignes pour pouvoir le télécharger.
					</p>
				{/if}

				{#if missingItems > 0}
					<p class="mb-2 bg-postit px-4 py-2 leading-snug" data-testid="missing-items">
						<span class="font-bold">
							{missingItems === 1
								? '1 élément sélectionné ne tient pas'
								: `${missingItems} éléments sélectionnés ne tiennent pas`} dans le panneau latéral et
							{missingItems === 1 ? 'n’apparaît pas' : 'n’apparaissent pas'} dans le PDF.
						</span>
						Décochez-en ou désactivez le panneau.
					</p>
				{/if}

				{#if editor.failure}
					<div
						role="alert"
						class="mb-2 flex flex-wrap items-center gap-x-3 bg-alert px-4 py-2 text-white"
					>
						<p class="min-w-0 flex-1 basis-48 font-bold">{editor.failure}</p>
						<Button variant="inverse" onclick={() => editor.refresh()}>Réessayer</Button>
					</div>
				{/if}

				<PdfSheet
					url={editor.preview?.url ?? null}
					placeholder={editor.refreshing ? 'Production du PDF…' : 'Pas encore d’aperçu.'}
				/>
			</aside>
		</div>
	{/if}
</div>
