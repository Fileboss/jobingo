<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api/client.ts';
	import type { components } from '#lib/api/schema.d.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import { remoteLabels, salaryLabel } from '#lib/offers/format.ts';
	import ScoreCard from '#lib/offers/ScoreCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	type OfferPage = components['schemas']['OfferPage'];

	let id = $derived(Number(page.params.id));
	let offer = $state.raw<OfferPage | null>(null);
	let phase = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');
	let adapting = $state(false);
	let failure = $state<string | null>(null);

	async function load() {
		try {
			const { data, response } = await api.GET('/api/offers/{offer_id}', {
				params: { path: { offer_id: id } }
			});
			if (response.status === 404) {
				phase = 'missing';
				return;
			}
			if (!data) throw new Error('no offer');
			offer = data;
			phase = 'ready';
		} catch {
			phase = 'unavailable';
		}
	}

	onMount(load);

	let scoring = $state(false);
	let scoreFailure = $state<string | null>(null);

	async function rescore() {
		scoring = true;
		scoreFailure = null;
		try {
			const { data, error } = await api.POST('/api/offers/{offer_id}/score', {
				params: { path: { offer_id: id } }
			});
			if (!data) {
				scoreFailure = error && 'message' in error ? error.message : 'La notation a échoué.';
				return;
			}
			offer = offer ? { ...offer, ...data } : offer;
		} catch {
			scoreFailure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			scoring = false;
		}
	}

	async function decide(decision: 'shortlisted' | 'dismissed' | null) {
		scoreFailure = null;
		try {
			const { data } = await api.PUT('/api/offers/{offer_id}/decision', {
				params: { path: { offer_id: id } },
				body: { decision }
			});
			if (data && offer) offer = { ...offer, ...data };
		} catch {
			scoreFailure = 'Le serveur ne répond pas. Réessayez.';
		}
	}

	let applying = $state(false);

	async function apply() {
		applying = true;
		try {
			const { data } = await api.POST('/api/offers/{offer_id}/application', {
				params: { path: { offer_id: id } }
			});
			if (data) await goto(resolve('/candidatures/[id]', { id: String(data.id) }));
		} finally {
			applying = false;
		}
	}

	async function adapt() {
		adapting = true;
		failure = null;
		try {
			const { data, error } = await api.POST('/api/offers/{offer_id}/cv-drafts/{lang}', {
				params: { path: { offer_id: id, lang: 'fr' } }
			});
			if (!data) {
				failure = error && 'message' in error ? error.message : 'La proposition a échoué.';
				return;
			}
			await goto(resolve('/adapter/[id]', { id: String(data.id) }));
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			adapting = false;
		}
	}
</script>

<svelte:head>
	<title>{offer ? `${offer.title} | ` : ''}Offres | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[72rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<p class="mb-2"><a href={resolve('/offres')} class="font-bold text-ink">← Offres</a></p>

	{#if phase === 'loading'}
		<p class="text-ink-soft" role="status">Chargement…</p>
	{:else if phase === 'missing'}
		<p class="text-xl font-extrabold text-ink">Cette offre n’existe pas.</p>
	{:else if phase === 'unavailable'}
		<div role="alert">
			<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
			<Button onclick={load}>Réessayer</Button>
		</div>
	{:else if offer}
		<h1 class="text-4xl leading-tight font-extrabold text-ink sm:text-5xl">{offer.title}</h1>
		<p class="text-xl font-bold text-ink-soft">{offer.company_name || 'Entreprise non nommée'}</p>

		<dl class="mt-5 grid grid-cols-2 gap-x-8 gap-y-3 bg-paper px-5 py-4 sm:grid-cols-4">
			{#each [['Lieu', offer.location || '—'], ['Contrat', offer.contract || '—'], ['Télétravail', remoteLabels[offer.remote]], ['Salaire', salaryLabel(offer)]] as [label, value] (label)}
				<div>
					<dt class="text-sm font-bold text-ink-soft">{label}</dt>
					<dd class="font-extrabold text-ink">{value}</dd>
				</div>
			{/each}
		</dl>
		<p class="mt-2 text-sm text-ink-soft">
			Reçue le {formatDateTime(offer.created_at)}{#if offer.llm_call_id}, extraite par
				<a
					href={resolve('/suivi/appels/[id]', { id: String(offer.llm_call_id) })}
					class="font-bold text-ink">l’appel #{offer.llm_call_id}</a
				>{/if}.
			{#if offer.url}
				<!-- eslint-disable svelte/no-navigation-without-resolve -- an external page -->
				<a
					href={offer.url}
					rel="noopener noreferrer"
					target="_blank"
					class="ml-2 font-bold text-ink">Voir l’annonce d’origine</a
				>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			{/if}
		</p>

		<section aria-labelledby="score-title" class="mt-8 bg-paper px-5 py-5">
			<div class="mb-3 flex flex-wrap items-baseline justify-between gap-3">
				<h2 id="score-title" class="text-2xl font-extrabold text-ink">Note</h2>
				<div class="flex flex-wrap items-center gap-2">
					{#if offer.decision}
						<span class="font-bold text-ink">
							{offer.decision === 'shortlisted' ? 'Retenue par vous.' : 'Écartée par vous.'}
						</span>
						<Button variant="quiet" onclick={() => decide(null)}>Annuler</Button>
					{:else}
						<Button onclick={() => decide('shortlisted')}>Retenir</Button>
						<Button variant="quiet" onclick={() => decide('dismissed')}>Écarter</Button>
					{/if}
				</div>
			</div>
			{#if offer.current_score}
				{#if offer.current_score.stale}
					<p class="mb-3 bg-postit px-3 py-2">
						<span class="font-bold">Note périmée :</span> vos objectifs ou votre CV ont changé depuis.
					</p>
				{/if}
				<ScoreCard score={offer.current_score} />
			{:else}
				<p class="text-ink-soft">Pas encore notée.</p>
			{/if}
			{#if scoreFailure}
				<p role="alert" class="mt-3 bg-alert px-3 py-2 font-bold text-white">{scoreFailure}</p>
			{/if}
			<div class="mt-4">
				<Button variant="quiet" disabled={scoring} onclick={rescore}>
					{scoring ? 'Notation…' : offer.current_score ? 'Noter à nouveau' : 'Noter'}
				</Button>
			</div>
		</section>

		<div class="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
			<section aria-labelledby="description-title">
				<h2 id="description-title" class="mb-2 text-2xl font-extrabold text-ink">Annonce</h2>
				{#if offer.description_md}
					<p class="bg-paper px-5 py-4 leading-relaxed whitespace-pre-line">
						{offer.description_md}
					</p>
				{:else}
					<p class="text-ink-soft">
						Seul l’intitulé est connu. Collez le texte complet de l’annonce dans « Offres » : il
						complétera cette fiche.
					</p>
				{/if}
			</section>

			<aside class="grid content-start gap-4">
				<div class="bg-bristol-yellow px-4 py-4">
					<h2 class="mb-2 font-extrabold text-ink">Candidature</h2>
					{#if offer.application_id}
						<a
							href={resolve('/candidatures/[id]', { id: String(offer.application_id) })}
							class="font-bold text-ink">Voir la candidature</a
						>
					{:else}
						<Button onclick={apply} disabled={applying}>Candidater</Button>
						<p class="mt-2 text-sm">Crée son suivi ; l’offre est marquée retenue.</p>
					{/if}
				</div>
				<div class="bg-bristol-blue px-4 py-4">
					<h2 class="mb-2 font-extrabold text-ink">Mon CV pour cette offre</h2>
					<Button onclick={adapt} disabled={adapting}>Adapter mon CV</Button>
					{#if adapting}
						<p role="status" class="mt-2 text-sm text-ink-soft">
							Le modèle lit votre CV et l’offre, une dizaine de secondes…
						</p>
					{/if}
					{#if failure}
						<p role="alert" class="mt-2 bg-alert px-3 py-2 text-sm font-bold text-white">
							{failure}
						</p>
					{/if}
					{#if offer.drafts.length}
						<ul class="mt-3 grid gap-1 text-sm">
							{#each offer.drafts as draft (draft.id)}
								<li>
									<a
										href={resolve('/adapter/[id]', { id: String(draft.id) })}
										class="font-bold text-ink"
									>
										CV du {formatDateTime(draft.created_at)}
									</a>
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			</aside>
		</div>
	{/if}
</div>
