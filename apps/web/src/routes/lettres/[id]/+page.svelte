<script lang="ts">
	import { onDestroy } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { LetterEditor } from '#lib/letters/letter.svelte.ts';
	import PdfSheet from '#lib/preview/PdfSheet.svelte';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	const LABELS: Record<
		string,
		{ title: string; colour: 'yellow' | 'blue' | 'green'; hint: string }
	> = {
		accroche: { title: 'Accroche', colour: 'yellow', hint: 'pourquoi cette offre' },
		adequation: {
			title: 'Adéquation',
			colour: 'blue',
			hint: 'tirée de vos réalisations seulement'
		},
		motivation: { title: 'Motivation', colour: 'green', hint: 'tirée de l’offre et de vos notes' }
	};

	const editor = new LetterEditor(Number(page.params.id));
	editor.load();
	onDestroy(() => editor.flush());

	let letter = $derived(editor.letter);
	let pages = $derived(editor.preview?.pages ?? 0);
	let overflow = $derived(letter !== null && pages > letter.max_pages);
	let canDownload = $derived(
		editor.preview !== null &&
			!overflow &&
			!editor.refreshing &&
			!editor.failure &&
			letter !== null &&
			letter.problems.length === 0
	);
	const words = (text: string) => (text.match(/[\p{L}\p{N}'’-]+/gu) ?? []).length;
</script>

<svelte:head>
	<title>Lettre | Jobingo</title>
</svelte:head>

<div class="flex-1 px-3 pt-2 pb-12 sm:px-6">
	{#if editor.status === 'loading'}
		<p class="text-ink-soft" role="status">Chargement…</p>
	{:else if editor.status === 'missing'}
		<p class="text-xl font-extrabold text-ink">Cette lettre n’existe pas.</p>
	{:else if editor.status === 'unavailable'}
		<div role="alert">
			<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
			<Button onclick={() => editor.load()}>Réessayer</Button>
		</div>
	{:else if letter}
		<p class="mb-2">
			<a
				href={resolve('/candidatures/[id]', { id: String(letter.application_id) })}
				class="font-bold text-ink">← {letter.application_title}</a
			>
		</p>
		<div class="mx-auto grid max-w-[96rem] gap-x-8 gap-y-6 xl:grid-cols-[minmax(0,1fr)_auto]">
			<div class="min-w-0">
				<h1 class="text-4xl leading-tight font-extrabold text-ink sm:text-5xl">
					Lettre de motivation
				</h1>
				<p class="mt-1 mb-5 max-w-3xl text-ink-soft">
					Le cadre (date, objet, formule, signature) vient du modèle de lettre ; le modèle de
					langage n’a écrit que les trois passages. Un passage refusé par le code reste vide :
					écrivez-le, ou reprenez la proposition en connaissance de cause.
					{#if letter.llm_call_id}
						<a
							href={resolve('/suivi/appels/[id]', { id: String(letter.llm_call_id) })}
							class="font-bold text-ink">Voir l’appel #{letter.llm_call_id}</a
						>
					{/if}
				</p>

				{#if letter.warnings.length}
					<ul class="mb-5 max-w-3xl list-disc bg-postit py-2 pr-4 pl-8">
						{#each letter.warnings as warning (warning)}<li>{warning}</li>{/each}
					</ul>
				{/if}

				<div class="grid gap-6">
					<label class="grid max-w-md gap-1">
						<span class="font-bold">Destinataire</span>
						<input
							value={editor.recipient}
							oninput={(e) => editor.setRecipient(e.currentTarget.value)}
							maxlength="300"
							class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
						/>
					</label>

					{#each letter.slots as slot, index (slot.name)}
						{@const label = LABELS[slot.name] ?? { title: slot.name, colour: 'yellow', hint: '' }}
						{@const text = editor.texts.get(slot.name) ?? ''}
						{@const count = words(text)}
						<BristolCard title={label.title} colour={label.colour} tab={index} note={label.hint}>
							<label class="grid gap-1">
								<span class="sr-only">{label.title}</span>
								<textarea
									value={text}
									oninput={(e) => editor.setText(slot.name, e.currentTarget.value)}
									rows="5"
									class="rounded-sm border-ink/40 bg-paper leading-relaxed focus:border-ink focus:ring-ink"
								></textarea>
							</label>
							<p
								class={[
									'mt-1 text-sm tabular-nums',
									count > slot.max_words ? 'font-bold text-alert' : 'text-ink-soft'
								]}
							>
								{count} mot{count > 1 ? 's' : ''} sur {slot.max_words}
							</p>
							{#if slot.rejected_reason && text !== slot.proposed}
								<p class="mt-2 border-l-2 border-alert pl-2 text-sm">
									<span class="font-bold text-alert">Proposition refusée</span>
									<span class="text-ink-soft">({slot.rejected_reason}) :</span>
									« {slot.proposed} »
									<button
										type="button"
										onclick={() => editor.setText(slot.name, slot.proposed)}
										class="ml-1 cursor-pointer font-bold text-ink underline underline-offset-4"
									>
										Utiliser quand même
									</button>
								</p>
							{/if}
							{#if slot.unsourced_names.length && text === slot.proposed}
								<p class="mt-1 text-sm font-bold text-alert">
									À vérifier : {slot.unsourced_names.join(', ')}, absent{slot.unsourced_names
										.length > 1
										? 's'
										: ''} des sources.
								</p>
							{/if}
						</BristolCard>
					{/each}
				</div>
			</div>

			<aside
				aria-label="Aperçu du PDF"
				class="self-start xl:sticky xl:top-3 xl:w-[calc((100dvh-7.5rem)*210/297)]"
			>
				<div class="mb-2 flex min-h-10 flex-wrap items-center justify-between gap-x-4 gap-y-1">
					<p role="status" class="font-bold text-ink">
						{#if editor.refreshing}Mise à jour…{:else if editor.preview}{pages} page{pages > 1
								? 's'
								: ''}{/if}
					</p>
					{#if editor.preview && canDownload}
						<!-- eslint-disable svelte/no-navigation-without-resolve -- a blob, not a route -->
						<a
							href={editor.preview.url}
							download={editor.preview.filename}
							class="rounded-sm bg-ink px-4 py-1.5 font-extrabold text-white no-underline hover:bg-ink-deep"
							>Télécharger le PDF</a
						>
						<!-- eslint-enable svelte/no-navigation-without-resolve -->
					{/if}
				</div>
				{#if letter.problems.length}
					<p class="mb-2 bg-postit px-4 py-2 leading-snug">
						<span class="font-bold">À régler avant de télécharger :</span>
						{letter.problems.join(' ; ')}.
					</p>
				{/if}
				{#if overflow}
					<p class="mb-2 bg-postit px-4 py-2 font-bold">
						La lettre fait {pages} pages : raccourcissez-la.
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
