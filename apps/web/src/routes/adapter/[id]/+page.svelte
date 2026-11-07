<script lang="ts">
	import { onDestroy } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import DraftLine from '#lib/drafts/DraftLine.svelte';
	import { DraftEditor, type DraftItem, type OptionName } from '#lib/drafts/draft.svelte.ts';
	import PdfSheet from '#lib/preview/PdfSheet.svelte';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';
	import Tick from '#lib/ui/Tick.svelte';

	const editor = new DraftEditor(Number(page.params.id));
	editor.load();
	onDestroy(() => editor.flush());

	let draft = $derived(editor.draft);
	let pages = $derived(editor.preview?.pages ?? 0);
	let missing = $derived(editor.preview?.missing ?? 0);
	let overflow = $derived(draft !== null && pages > draft.max_pages);
	let canDownload = $derived(
		editor.preview !== null && !overflow && !editor.refreshing && !editor.failure
	);

	let all = $derived.by((): DraftItem[] => {
		if (!draft) return [];
		return [
			...(draft.resume ? [draft.resume] : []),
			...draft.experiences.flatMap((e) => [e, ...e.bullets]),
			...draft.formation,
			...draft.competences,
			...draft.loisirs
		];
	});
	let proposed = $derived(all.filter((item) => item.proposed).length);
	let accepted = $derived(
		all.filter((item) => item.proposed_rewrite && !item.rejected_reason).length
	);
	let refused = $derived(all.filter((item) => item.rejected_reason).length);

	const optionLabels: Record<OptionName, string> = {
		photo: 'Photo',
		panneau_competences: 'Compétences en panneau latéral',
		loisirs: 'Loisirs'
	};
	const OPTIONS = Object.keys(optionLabels) as OptionName[];
</script>

<svelte:head>
	<title>{draft ? `${draft.offer.title} | ` : ''}Adapter mon CV | Jobingo</title>
</svelte:head>

<div class="flex-1 px-3 pt-2 pb-12 sm:px-6">
	<p class="mb-2"><a href={resolve('/adapter')} class="font-bold text-ink">← CV adaptés</a></p>

	{#if editor.status === 'loading'}
		<p class="text-ink-soft" role="status">Chargement…</p>
	{:else if editor.status === 'missing'}
		<p class="text-xl font-extrabold text-ink">Ce CV adapté n’existe pas.</p>
	{:else if editor.status === 'unavailable'}
		<div role="alert" class="bg-paper px-5 py-8">
			<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
			<p class="mt-1 mb-4">Vérifiez que l’API tourne, puis :</p>
			<Button onclick={() => editor.load()}>Réessayer</Button>
		</div>
	{:else if draft}
		<div class="mx-auto grid max-w-[96rem] gap-x-8 gap-y-6 xl:grid-cols-[minmax(0,1fr)_auto]">
			<div class="min-w-0">
				<h1 class="text-4xl leading-tight font-extrabold text-ink sm:text-5xl">
					{draft.offer.title}
				</h1>
				{#if draft.offer.company}<p class="text-xl font-bold text-ink-soft">
						{draft.offer.company}
					</p>{/if}

				<div class="mt-4 mb-6 flex flex-wrap items-baseline gap-x-6 gap-y-1">
					<p>
						Le modèle a retenu <span class="font-extrabold">{proposed}</span> éléments, proposé
						<span class="font-extrabold">{accepted + refused}</span>
						reformulation{accepted + refused > 1 ? 's' : ''} ;
						<span class="font-extrabold">{refused}</span> refusée{refused > 1 ? 's' : ''} par le code.
					</p>
					{#if draft.llm_call_id}
						<a
							href={resolve('/suivi/appels/[id]', { id: String(draft.llm_call_id) })}
							class="text-sm font-bold text-ink">Voir l’appel #{draft.llm_call_id}</a
						>
					{/if}
				</div>

				<details class="mb-6 max-w-3xl">
					<summary class="cursor-pointer font-bold text-ink">Voir l’annonce</summary>
					<p class="mt-2 bg-paper px-4 py-3 whitespace-pre-line">{draft.offer.description}</p>
				</details>

				{#if draft.warnings.length || draft.gone}
					<div
						class="mb-6 max-w-3xl bg-postit px-4 py-3 leading-snug shadow-[0_6px_12px_-8px_var(--color-ink-deep)]"
					>
						{#if draft.gone}
							<p class="font-bold">
								Votre CV a changé depuis : {draft.gone} élément{draft.gone > 1 ? 's' : ''} proposé{draft.gone >
								1
									? 's'
									: ''} n’y {draft.gone > 1 ? 'sont' : 'est'} plus.
							</p>
						{/if}
						{#if draft.warnings.length}
							<p class="font-bold">Le code a ignoré une partie de la réponse :</p>
							<ul class="list-disc pl-5">
								{#each draft.warnings as warning (warning)}<li>{warning}</li>{/each}
							</ul>
						{/if}
					</div>
				{/if}

				<div class="grid gap-6">
					<BristolCard title="Options" colour="grey">
						<div class="grid gap-2">
							{#each OPTIONS as name (name)}
								{@const blocker = draft.option_blockers[name]}
								<Tick
									checked={editor.options[name]}
									disabled={blocker !== null}
									onchange={(value) => editor.setOption(name, value)}
								>
									<span class="font-bold">{optionLabels[name]}</span>
									{#if blocker}<span class="block text-sm text-ink-soft">{blocker}</span>{/if}
								</Tick>
							{/each}
						</div>
					</BristolCard>

					{#if draft.resume}
						<BristolCard title="Résumé" colour="yellow" tab={0}>
							<DraftLine {editor} item={draft.resume} />
						</BristolCard>
					{/if}

					{#if draft.experiences.length}
						<BristolCard title="Expériences" colour="blue" tab={1}>
							<div class="divide-y divide-ink/30">
								{#each draft.experiences as experience (experience.id)}
									<article class="grid gap-2 py-3">
										<DraftLine {editor} item={experience} strong />
										{#if experience.bullets.length}
											<ul class="ml-7 grid gap-2">
												{#each experience.bullets as bullet (bullet.id)}
													<li><DraftLine {editor} item={bullet} /></li>
												{/each}
											</ul>
										{/if}
									</article>
								{/each}
							</div>
						</BristolCard>
					{/if}

					{#each [['Formation', 'green', 2, draft.formation], ['Compétences', 'salmon', 3, draft.competences], ['Loisirs', 'lilac', 4, draft.loisirs]] as const as [title, colour, tab, items] (title)}
						{#if items.length}
							<BristolCard {title} {colour} {tab}>
								<ul class="grid gap-2">
									{#each items as item (item.id)}<li><DraftLine {editor} {item} /></li>{/each}
								</ul>
							</BristolCard>
						{/if}
					{/each}
				</div>
			</div>

			<aside
				aria-label="Aperçu du PDF"
				class="self-start xl:sticky xl:top-3 xl:w-[calc((100dvh-7.5rem)*210/297)]"
			>
				<div class="mb-2 flex min-h-10 flex-wrap items-center justify-between gap-x-4 gap-y-1">
					<p role="status" class="font-bold text-ink">
						{#if editor.refreshing}
							Mise à jour…
						{:else if editor.preview}
							{pages} page{pages > 1 ? 's' : ''}
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
					{/if}
				</div>
				{#if overflow}
					<p class="mb-2 bg-postit px-4 py-2 leading-snug">
						<span class="font-bold">Le CV fait {pages} pages : il doit tenir sur une seule.</span>
						Décochez quelques lignes pour pouvoir le télécharger.
					</p>
				{/if}
				{#if missing > 0}
					<p class="mb-2 bg-postit px-4 py-2 leading-snug">
						<span class="font-bold"
							>{missing} élément{missing > 1 ? 's' : ''} ne tien{missing > 1 ? 'nent' : 't'} pas dans
							le panneau latéral.</span
						>
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
