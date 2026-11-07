<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api/client.ts';
	import type { Message } from '#lib/mail/format.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import type { ScoredOffer } from '#lib/offers/format.ts';
	import ScoreBadge from '#lib/offers/ScoreBadge.svelte';
	import Button from '#lib/ui/Button.svelte';

	let id = $derived(Number(page.params.id));
	let message = $state.raw<Message | null>(null);
	let offers = $state.raw<ScoredOffer[]>([]);
	let phase = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');

	async function load() {
		try {
			const { data, response } = await api.GET('/api/mail/messages/{message_id}', {
				params: { path: { message_id: id } }
			});
			if (response.status === 404) {
				phase = 'missing';
				return;
			}
			if (!data) throw new Error('no message');
			message = data;
			if (data.offer_ids.length) {
				const listed = await api.GET('/api/offers');
				offers = (listed.data ?? []).filter((offer) => data.offer_ids.includes(offer.id));
			}
			phase = 'ready';
		} catch {
			phase = 'unavailable';
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>{message?.subject || 'Message'} | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[72rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<a href={resolve('/courrier')} class="font-bold text-ink">← Courrier</a>

	{#if phase === 'loading'}
		<p class="mt-4 text-ink-soft" role="status">Chargement…</p>
	{:else if phase === 'missing'}
		<p class="mt-4 font-extrabold text-ink">Ce message n’existe pas.</p>
	{:else if phase === 'unavailable'}
		<div class="mt-4" role="alert">
			<p class="font-extrabold text-ink">Le serveur ne répond pas.</p>
			<Button onclick={load}>Réessayer</Button>
		</div>
	{:else if message}
		<h1 class="mt-2 text-4xl leading-tight font-extrabold break-words text-ink">
			{message.subject || '(sans objet)'}
		</h1>
		<dl class="mt-3 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-[auto_minmax(0,1fr)]">
			<dt class="font-bold text-ink-soft">De</dt>
			<dd class="break-all">{message.from_addr}</dd>
			<dt class="font-bold text-ink-soft">Reçu le</dt>
			<dd>{formatDateTime(message.received_at)}, dossier {message.folder}</dd>
		</dl>

		{#if message.kind === 'alert'}
			<section aria-labelledby="offers-title" class="mt-6">
				<h2 id="offers-title" class="text-2xl font-extrabold text-ink">Offres lues</h2>
				{#if offers.length}
					<ul class="mt-2 divide-y divide-ink/10 bg-paper">
						{#each offers as offer (offer.id)}
							<li class="flex items-center gap-4 px-4 py-2">
								<ScoreBadge {offer} />
								<div class="min-w-0">
									<a
										href={resolve('/offres/[id]', { id: String(offer.id) })}
										class="font-extrabold text-ink">{offer.title}</a
									>
									<span class="block text-sm text-ink-soft"
										>{[offer.company_name, offer.location].filter(Boolean).join(' · ')}</span
									>
								</div>
							</li>
						{/each}
					</ul>
				{:else if message.processed_at}
					<p class="mt-2 text-ink-soft">Aucune offre dans cette alerte.</p>
				{:else}
					<p class="mt-2 bg-postit px-3 py-1 font-bold">
						Cette alerte attend l’IA, qui en extraira les offres à la prochaine lecture.
					</p>
				{/if}
			</section>
		{:else}
			<p class="mt-6 bg-bristol-grey px-3 py-2 text-sm">
				Message reçu, pas encore trié : refus, entretien ou prise de contact, et la candidature
				qu’il concerne.
			</p>
		{/if}

		<section aria-labelledby="body-title" class="mt-6">
			<h2 id="body-title" class="sr-only">Texte du message</h2>
			<p
				class="bg-paper px-4 py-4 leading-7 break-words whitespace-pre-wrap text-ink-deep sm:px-7"
				data-testid="message-body"
			>
				{message.body_text || '(message vide)'}
			</p>
			<p class="mt-2 text-sm text-ink-soft">
				Le texte seul est affiché : la partie HTML du message n’est jamais rendue ici.
			</p>
		</section>
	{/if}
</div>
