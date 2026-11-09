<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api/client.ts';
	import { bareAddress, replySubject } from '#lib/actions/format.ts';
	import Composer from '#lib/actions/Composer.svelte';
	import { formatDate, type ApplicationSummary } from '#lib/applications/format.ts';
	import {
		categoryLabels,
		hiddenReasons,
		suggestionLabels,
		type Message
	} from '#lib/mail/format.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import type { ScoredOffer } from '#lib/offers/format.ts';
	import ScoreBadge from '#lib/offers/ScoreBadge.svelte';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	let id = $derived(Number(page.params.id));
	let message = $state.raw<Message | null>(null);
	let offers = $state.raw<ScoredOffer[]>([]);
	let phase = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');
	let applications = $state.raw<ApplicationSummary[]>([]);
	let chosen = $state<number | null>(null);
	let busy = $state(false);
	let failure = $state<string | null>(null);
	let replying = $state(false);
	let letters = $state.raw<{ id: number; created_at: string }[]>([]);

	async function startReply() {
		letters = [];
		if (message?.application_id) {
			const { data } = await api.GET('/api/applications/{application_id}/letters', {
				params: { path: { application_id: message.application_id } }
			});
			letters = data ?? [];
		}
		replying = true;
	}

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
			chosen = data.application_id;
			if (data.kind === 'message') {
				const listed = await api.GET('/api/applications');
				applications = listed.data ?? [];
			}
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

	const path = () => ({ params: { path: { message_id: id } } });

	/** One decision on the message; the answer is the message as it now stands. */
	async function decide(
		call: () => Promise<{ data?: Message; error?: unknown; response: Response }>
	) {
		busy = true;
		failure = null;
		try {
			const { data, error, response } = await call();
			if (data) {
				message = data;
				chosen = data.application_id;
			} else if (error && typeof error === 'object' && 'message' in error) {
				failure = String(error.message);
			} else {
				failure = response.status === 404 ? 'Introuvable : rechargez la page.' : 'Échec.';
			}
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			busy = false;
		}
	}

	const link = (applicationId: number | null) =>
		decide(() =>
			api.PUT('/api/mail/messages/{message_id}/application', {
				...path(),
				body: { application_id: applicationId }
			})
		);
	const accept = () =>
		decide(() => api.POST('/api/mail/messages/{message_id}/suggestion/accept', path()));
	const dismiss = () =>
		decide(() => api.POST('/api/mail/messages/{message_id}/suggestion/dismiss', path()));
	const setHidden = (hidden: boolean) =>
		decide(() =>
			api.PUT('/api/mail/messages/{message_id}/hidden', { ...path(), body: { hidden } })
		);
	const block = () =>
		decide(() => api.POST('/api/mail/messages/{message_id}/block-sender', path()));

	let suggestion = $derived(message?.suggestion ?? null);
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

		{#if failure}
			<p role="alert" class="mt-4 bg-alert px-4 py-2 font-bold text-white">{failure}</p>
		{/if}

		{#if message.kind === 'message'}
			<div class="mt-6 grid gap-6 md:grid-cols-2">
				<BristolCard title="Lu par l’IA" colour="lilac">
					{#if message.category}
						<p class="text-2xl font-extrabold text-ink">{categoryLabels[message.category]}</p>
						{#if message.summary}<p class="mt-1">{message.summary}</p>{/if}
						{#if message.company_hint}
							<p class="mt-1 text-sm">Entreprise lue : {message.company_hint}</p>
						{/if}
						{#if message.llm_call_id}
							<a
								href={resolve('/suivi/appels/[id]', { id: String(message.llm_call_id) })}
								class="mt-2 inline-block text-sm font-bold text-ink">Voir l’appel au modèle</a
							>
						{/if}
					{:else if message.hidden_reason}
						<p>Pas lu par l’IA.</p>
					{:else}
						<p>Pas encore classé : l’IA le lira à la prochaine synchronisation.</p>
					{/if}
				</BristolCard>

				<BristolCard title="Candidature" colour="blue">
					{#if message.application_id}
						<a
							href={resolve('/candidatures/[id]', { id: String(message.application_id) })}
							class="text-xl font-extrabold break-words text-ink">{message.application_title}</a
						>
						<p class="mt-1 text-sm">
							{message.linked_by === 'match'
								? 'Rattaché par le code : même fil, adresse du contact ou nom de l’entreprise.'
								: 'Rattaché par vous.'}
						</p>
					{:else}
						<p>Rattaché à aucune candidature.</p>
					{/if}
					{#if applications.length}
						<form
							class="mt-3 flex flex-wrap items-end gap-2"
							onsubmit={(event) => {
								event.preventDefault();
								link(chosen);
							}}
						>
							<label class="grid min-w-0 flex-1 gap-1">
								<span class="text-sm font-bold">
									{message.application_id ? 'Changer pour' : 'Rattacher à'}
								</span>
								<select
									bind:value={chosen}
									class="w-full min-w-0 rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
								>
									<option value={null}>Aucune</option>
									{#each applications as application (application.id)}
										<option value={application.id}>
											{[application.title, application.company_name].filter(Boolean).join(' · ')}
										</option>
									{/each}
								</select>
							</label>
							<Button type="submit" disabled={busy || chosen === message.application_id}>
								Enregistrer
							</Button>
						</form>
						<p class="mt-2 text-sm">Ses événements suivent le message.</p>
					{/if}
				</BristolCard>
			</div>

			{#if suggestion}
				<section
					aria-labelledby="suggestion-title"
					class={[
						'mt-6 px-4 py-4 sm:px-6',
						suggestion.status === 'pending' ? 'bg-postit' : 'bg-bristol-grey'
					]}
				>
					<h2 id="suggestion-title" class="text-xl font-extrabold text-ink">
						Suggestion : {suggestionLabels[suggestion.type]}{#if suggestion.date}
							le {formatDate(suggestion.date)}{/if}
					</h2>
					{#if suggestion.status === 'pending'}
						<p class="mt-1">
							Rien ne change sans vous : confirmez pour l’ajouter à la chronologie de la
							candidature.
						</p>
						{#if !message.application_id}
							<p class="mt-1 font-bold">Rattachez d’abord ce message à une candidature.</p>
						{/if}
						<div class="mt-3 flex flex-wrap gap-3">
							<Button onclick={accept} disabled={busy || !message.application_id}>Confirmer</Button>
							<Button variant="quiet" onclick={dismiss} disabled={busy}>Écarter</Button>
						</div>
					{:else}
						<p class="mt-1">
							{suggestion.status === 'accepted'
								? 'Confirmée : ajoutée à la chronologie.'
								: 'Écartée : la candidature n’a pas changé.'}
						</p>
					{/if}
				</section>
			{/if}

			<div class="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2">
				{#if message.hidden_reason}
					<p class="bg-bristol-grey px-3 py-1 text-sm">{hiddenReasons[message.hidden_reason]}</p>
					<Button variant="quiet" onclick={() => setHidden(false)} disabled={busy}>
						{message.hidden_reason === 'blocked_sender'
							? 'Débloquer l’expéditeur et restaurer'
							: 'Restaurer'}
					</Button>
				{:else}
					{#if !replying}
						<Button onclick={startReply}>Répondre</Button>
					{/if}
					<Button variant="quiet" onclick={() => setHidden(true)} disabled={busy}>Masquer</Button>
					<Button variant="quiet" onclick={block} disabled={busy}>Bloquer l’expéditeur</Button>
				{/if}
			</div>
		{/if}

		{#if replying}
			<section aria-labelledby="reply-title" class="mt-6">
				<h2 id="reply-title" class="mb-2 text-2xl font-extrabold text-ink">Réponse</h2>
				{#key message.application_id}
					<Composer
						applicationId={message.application_id}
						messageId={message.id}
						to={bareAddress(message.from_addr)}
						subject={replySubject(message.subject)}
						{letters}
						oncancel={() => (replying = false)}
					/>
				{/key}
			</section>
		{/if}

		{#if message.kind === 'alert' || message.offer_ids.length}
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
