<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import type { components } from '#lib/api/schema.d.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	type DraftSummary = components['schemas']['DraftSummary'];

	let title = $state('');
	let company = $state('');
	let description = $state('');
	let sending = $state(false);
	let failure = $state<string | null>(null);
	let drafts = $state.raw<DraftSummary[] | null>(null);

	onMount(async () => {
		try {
			const { data } = await api.GET('/api/cv/drafts');
			drafts = data ?? [];
		} catch {
			drafts = [];
		}
	});

	async function propose(event: SubmitEvent) {
		event.preventDefault();
		sending = true;
		failure = null;
		try {
			const { data, error } = await api.POST('/api/cv/{lang}/drafts', {
				params: { path: { lang: 'fr' } },
				body: { title: title.trim(), company: company.trim(), description: description.trim() }
			});
			if (!data) {
				failure =
					error && 'message' in error ? error.message : 'La proposition n’a pas pu être faite.';
				return;
			}
			await goto(resolve('/adapter/[id]', { id: String(data.id) }));
		} catch {
			failure = 'Le serveur ne répond pas. Vérifiez que l’API tourne, puis réessayez.';
		} finally {
			sending = false;
		}
	}

	let ready = $derived(title.trim() !== '' && description.trim() !== '');
</script>

<svelte:head>
	<title>Adapter mon CV | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Adapter mon CV</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Collez une offre : le modèle choisit dans votre CV ce qui la sert, et peut reformuler
		légèrement. Rien n’est inventé, le code vérifie chaque reformulation, et vous décidez de tout
		avant de télécharger.
	</p>

	<div class="grid gap-x-8 gap-y-10 xl:grid-cols-[minmax(0,1fr)_26rem]">
		<BristolCard title="Nouvelle offre" colour="blue">
			<form class="grid gap-4" onsubmit={propose}>
				<div class="grid gap-4 sm:grid-cols-2">
					<label class="grid gap-1">
						<span class="font-bold">Intitulé du poste</span>
						<input
							bind:value={title}
							required
							maxlength="300"
							class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
						/>
					</label>
					<label class="grid gap-1">
						<span class="font-bold">Entreprise</span>
						<input
							bind:value={company}
							maxlength="300"
							class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
						/>
					</label>
				</div>
				<label class="grid gap-1">
					<span class="font-bold">Annonce</span>
					<textarea
						bind:value={description}
						required
						rows="10"
						maxlength="20000"
						placeholder="Le texte de l’offre, tel quel."
						class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"></textarea>
				</label>
				<p class="text-sm text-ink-soft">
					Votre nom, votre e-mail et votre téléphone sont remplacés par « [CANDIDAT] » avant
					l’envoi, et l’appel apparaît dans le suivi de l’IA.
				</p>
				{#if failure}
					<p role="alert" class="bg-alert px-4 py-2 font-bold text-white">{failure}</p>
				{/if}
				<div class="flex flex-wrap items-center gap-4">
					<Button type="submit" disabled={!ready || sending}>Proposer un CV pour cette offre</Button
					>
					{#if sending}
						<p role="status" class="text-ink-soft">
							Le modèle lit votre CV et l’offre, une dizaine de secondes…
						</p>
					{/if}
				</div>
			</form>
		</BristolCard>

		<section aria-labelledby="drafts-title">
			<h2 id="drafts-title" class="mb-3 text-2xl font-extrabold text-ink">CV adaptés</h2>
			{#if drafts === null}
				<p class="text-ink-soft">Chargement…</p>
			{:else if drafts.length === 0}
				<p class="text-ink-soft">Aucun pour l’instant.</p>
			{:else}
				<ul class="grid gap-2">
					{#each drafts as draft (draft.id)}
						<li>
							<a
								href={resolve('/adapter/[id]', { id: String(draft.id) })}
								class="block bg-paper px-4 py-2.5 no-underline hover:bg-bristol-grey"
							>
								<span class="block font-extrabold text-ink">{draft.offer_title}</span>
								<span class="text-sm text-ink-soft">
									{draft.offer_company ? `${draft.offer_company} · ` : ''}{formatDateTime(
										draft.created_at
									)}
								</span>
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	</div>
</div>
