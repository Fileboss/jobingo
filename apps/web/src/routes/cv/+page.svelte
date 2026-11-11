<script lang="ts">
	import { onMount, tick } from 'svelte';
	import CvConflict from '#lib/cv/CvConflict.svelte';
	import CvDiagnostics from '#lib/cv/CvDiagnostics.svelte';
	import CvEmpty from '#lib/cv/CvEmpty.svelte';
	import CvForm from '#lib/cv/CvForm.svelte';
	import CvTextEditor from '#lib/cv/CvTextEditor.svelte';
	import { experienceIndexOf, type CvDiagnostic } from '#lib/cv/diagnostics.ts';
	import { CvEditor, type CvMode } from '#lib/cv/editor.svelte.ts';
	import { savedOn } from '#lib/cv/format.ts';
	import { cardOfSection } from '#lib/cv/sections.ts';
	import Button from '#lib/ui/Button.svelte';

	const editor = new CvEditor();
	const modes: { key: CvMode; label: string }[] = [
		{ key: 'form', label: 'Fiches' },
		{ key: 'text', label: 'Texte' }
	];
	let textEditor = $state<CvTextEditor>();

	onMount(() => {
		editor.load();
	});

	// Live diagnostics: any edit asks the server again, shortly after.
	let lastKey: string | null = null;
	$effect(() => {
		const key = editor.draftKey;
		if (editor.status !== 'ready') return;
		if (lastKey !== null && key !== lastKey) editor.checkSoon();
		lastKey = key;
	});

	let status = $derived.by(() => {
		if (editor.busy === 'save') return 'Enregistrement…';
		if (editor.dirty) return 'Modifications non enregistrées';
		if (editor.stored?.needs_save)
			return 'Une section que l’app reconnaît désormais attend un enregistrement';
		if (editor.stored?.version) {
			return `Version ${editor.stored.version}, enregistrée ${savedOn(editor.stored.updated_at)}`;
		}
		return 'Rien d’enregistré pour l’instant';
	});

	function onkeydown(event: KeyboardEvent) {
		if ((event.metaKey || event.ctrlKey) && event.key === 's') {
			event.preventDefault();
			if (editor.dirty && !editor.conflict) editor.save();
		}
	}

	function onbeforeunload(event: BeforeUnloadEvent) {
		if (editor.dirty) event.preventDefault();
	}

	function place(diagnostic: CvDiagnostic) {
		if (editor.mode === 'text') return diagnostic.line_no ? `Ligne ${diagnostic.line_no}` : null;
		const index = experienceIndexOf(diagnostic, editor.diagnosticsText);
		if (index === null) return diagnostic.section;
		const experience = editor.fields.experiences[index];
		return experience?.company || experience?.title || diagnostic.section;
	}

	async function select(diagnostic: CvDiagnostic) {
		if (editor.mode === 'text') {
			if (diagnostic.line_no) textEditor?.goToLine(diagnostic.line_no);
			return;
		}
		await tick();
		const card = document.getElementById(cardOfSection(diagnostic.section) ?? 'cv-avant');
		card?.scrollIntoView({ block: 'start' });
		card?.querySelector<HTMLElement>('input, textarea')?.focus({ preventScroll: true });
	}
</script>

<svelte:head>
	<title>Mon CV | Jobingo</title>
</svelte:head>

<svelte:window {onkeydown} {onbeforeunload} />

<div class="flex-1 px-3 pt-2 pb-12 sm:px-6">
	<div
		class={[
			'mx-auto grid max-w-232 gap-x-6',
			editor.diagnostics.length &&
				!editor.isEmpty &&
				'xl:max-w-[calc(58rem+17.5rem)] xl:grid-cols-[minmax(0,58rem)_16rem]'
		]}
	>
		<div class="mb-5 flex flex-wrap items-baseline justify-between gap-3 xl:col-span-full">
			<h1 class="text-5xl leading-tight font-extrabold text-ink">Mon CV</h1>
			{#if editor.status === 'ready' && !editor.isEmpty}
				<div role="group" aria-label="Mode de saisie" class="flex gap-1">
					{#each modes as mode (mode.key)}
						<button
							type="button"
							aria-pressed={editor.mode === mode.key}
							disabled={editor.busy === 'switch'}
							onclick={() => editor.setMode(mode.key)}
							class="cursor-pointer border-b-3 border-transparent px-2.5 font-semibold text-ink aria-pressed:border-ink aria-pressed:font-extrabold"
						>
							{mode.label}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		{#if editor.status === 'loading'}
			<p class="text-ink-soft" role="status">Ouverture du classeur…</p>
		{:else if editor.status === 'unavailable'}
			<div role="alert" class="bg-paper px-5 py-8">
				<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
				<p class="mt-1 mb-4">Votre CV n’a pas pu être chargé. Vérifiez que l’API tourne, puis :</p>
				<Button onclick={() => editor.load()}>Réessayer</Button>
			</div>
		{:else if editor.isEmpty}
			<CvEmpty onform={() => editor.start('form')} ontext={() => editor.start('text')} />
		{:else}
			{#if editor.conflict}
				<div class="xl:col-span-full">
					<CvConflict
						stored={editor.conflict}
						disabled={editor.busy !== null}
						ontake={() => editor.takeStored()}
						onoverwrite={() => editor.overwrite()}
					/>
				</div>
			{/if}
			{#if editor.rejected.length}
				<div role="alert" class="mb-6 bg-alert px-5 py-4 text-white xl:col-span-full">
					<p class="font-extrabold">Ce CV n’a pas été enregistré.</p>
					{#each editor.rejected as item, index (index)}
						<p class="mt-1">
							{#if item.line_no}Ligne {item.line_no} :
							{/if}{item.message}
							{item.suggestion}
						</p>
					{/each}
				</div>
			{/if}
			{#if editor.failure}
				<p role="alert" class="mb-6 bg-alert px-5 py-3 font-bold text-white xl:col-span-full">
					Le serveur ne répond pas. Votre saisie est intacte, réessayez dans un instant.
				</p>
			{/if}

			<main inert={editor.busy === 'switch'} class="min-w-0">
				{#if editor.mode === 'form'}
					<CvForm {editor} />
				{:else}
					<CvTextEditor bind:this={textEditor} bind:value={editor.text} label="Texte du CV" />
				{/if}
			</main>
			<div class="max-xl:order-first max-xl:mb-6">
				<CvDiagnostics diagnostics={editor.diagnostics} {place} onselect={select} />
			</div>
		{/if}
	</div>
</div>

{#if editor.status === 'ready' && !editor.isEmpty}
	<footer
		class="sticky bottom-0 z-10 flex flex-wrap items-center justify-end gap-x-5 gap-y-1 border-t-3 border-ink bg-paper px-4 py-2.5 sm:px-6"
	>
		<p role="status">{status}</p>
		<Button
			disabled={!(editor.dirty || editor.stored?.needs_save) ||
				editor.busy !== null ||
				editor.conflict !== null}
			onclick={() => editor.save()}
		>
			Enregistrer
		</Button>
	</footer>
{/if}
