<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api/client.ts';
	import {
		eventLabels,
		formatDate,
		today,
		type ApplicationView,
		type EventType
	} from '#lib/applications/format.ts';
	import StatusPill from '#lib/applications/StatusPill.svelte';
	import Composer from '#lib/actions/Composer.svelte';
	import { categoryLabels, senderName } from '#lib/mail/format.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	const EVENT_TYPES = Object.keys(eventLabels) as EventType[];

	let id = $derived(Number(page.params.id));
	let application = $state.raw<ApplicationView | null>(null);
	let phase = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');
	let failure = $state<string | null>(null);

	let kind = $state<EventType>('applied');
	let day = $state(today());
	let note = $state('');
	let contactName = $state('');
	let contactEmail = $state('');
	let contactPhone = $state('');
	let contactSaved = $state(false);
	let notes = $state('');
	let notesSaved = $state(false);
	let letters = $state.raw<{ id: number; created_at: string }[]>([]);
	let writing_to = $state(false);
	let writing = $state(false);
	let letterFailure = $state<string | null>(null);

	function adopt(data: ApplicationView) {
		application = data;
		contactName = data.contact.name ?? '';
		contactEmail = data.contact.email ?? '';
		contactPhone = data.contact.phone ?? '';
		notes = data.company_notes;
	}

	async function load() {
		try {
			const { data, response } = await api.GET('/api/applications/{application_id}', {
				params: { path: { application_id: id } }
			});
			if (response.status === 404) {
				phase = 'missing';
				return;
			}
			if (!data) throw new Error('no application');
			adopt(data);
			phase = 'ready';
		} catch {
			phase = 'unavailable';
			return;
		}
		// The letters are a side list: failing to read them leaves the page usable.
		try {
			const { data: listed } = await api.GET('/api/applications/{application_id}/letters', {
				params: { path: { application_id: id } }
			});
			letters = listed ?? [];
		} catch {
			letters = [];
		}
	}

	onMount(load);

	async function addEvent(event: SubmitEvent) {
		event.preventDefault();
		failure = null;
		try {
			const { data } = await api.POST('/api/applications/{application_id}/events', {
				params: { path: { application_id: id } },
				body: { type: kind, occurred_at: day, note: note.trim() }
			});
			if (!data) {
				failure = 'Cet événement est refusé.';
				return;
			}
			adopt(data);
			note = '';
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		}
	}

	async function removeEvent(eventId: number) {
		const { data } = await api.DELETE('/api/applications/{application_id}/events/{event_id}', {
			params: { path: { application_id: id, event_id: eventId } }
		});
		if (data) adopt(data);
	}

	async function saveContact(event: SubmitEvent) {
		event.preventDefault();
		failure = null;
		contactSaved = false;
		const { data } = await api.PUT('/api/applications/{application_id}/contact', {
			params: { path: { application_id: id } },
			body: { name: contactName, email: contactEmail.trim(), phone: contactPhone }
		});
		if (!data) {
			failure = 'Ce contact est refusé : vérifiez l’adresse e-mail.';
			return;
		}
		adopt(data);
		contactSaved = true;
	}

	async function saveNotes(event: SubmitEvent) {
		event.preventDefault();
		notesSaved = false;
		const { response } = await api.PUT('/api/applications/{application_id}/company-notes', {
			params: { path: { application_id: id } },
			body: { notes }
		});
		notesSaved = response.ok;
	}

	async function writeLetter() {
		writing = true;
		letterFailure = null;
		try {
			const { data, error } = await api.POST('/api/applications/{application_id}/letters', {
				params: { path: { application_id: id } }
			});
			if (!data) {
				letterFailure =
					error && 'message' in error ? error.message : 'La lettre n’a pas pu être rédigée.';
				return;
			}
			await goto(resolve('/lettres/[id]', { id: String(data.id) }));
		} catch {
			letterFailure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			writing = false;
		}
	}

	async function remove() {
		await api.DELETE('/api/applications/{application_id}', {
			params: { path: { application_id: id } }
		});
		await goto(resolve('/candidatures'));
	}

	let confirming = $state(false);
	let late = $derived(application?.follow_up_on != null && application.follow_up_on <= today());
</script>

<svelte:head>
	<title>{application ? `${application.title} | ` : ''}Candidatures | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[72rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<p class="mb-2">
		<a href={resolve('/candidatures')} class="font-bold text-ink">← Candidatures</a>
	</p>

	{#if phase === 'loading'}
		<p class="text-ink-soft" role="status">Chargement…</p>
	{:else if phase === 'missing'}
		<p class="text-xl font-extrabold text-ink">Cette candidature n’existe pas.</p>
	{:else if phase === 'unavailable'}
		<div role="alert">
			<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
			<Button onclick={load}>Réessayer</Button>
		</div>
	{:else if application}
		<div class="flex flex-wrap items-center gap-x-4 gap-y-1">
			<h1 class="text-4xl leading-tight font-extrabold text-ink sm:text-5xl">
				{application.title}
			</h1>
			<StatusPill status={application.status} tone={application.tone} />
		</div>
		<p class="text-xl font-bold text-ink-soft">
			{application.company_name || 'Entreprise non nommée'}
			{#if application.offer_id}
				· <a
					href={resolve('/offres/[id]', { id: String(application.offer_id) })}
					class="text-base text-ink">Voir l’offre et ses CV adaptés</a
				>
			{/if}
		</p>
		{#if application.follow_up_on}
			<p class={['mt-3 inline-block px-3 py-1.5', late ? 'bg-postit font-bold' : 'bg-paper']}>
				{late ? 'Relance à faire depuis le' : 'Relance prévue le'}
				{formatDate(application.follow_up_on)} : une semaine après l’envoi, sans réponse.
			</p>
		{/if}

		{#if failure}<p role="alert" class="mt-4 bg-alert px-4 py-2 font-bold text-white">
				{failure}
			</p>{/if}

		<div class="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
			<section aria-labelledby="timeline-title">
				{#if writing_to}
					<div class="mb-8">
						<h2 class="mb-2 text-2xl font-extrabold text-ink">Message au contact</h2>
						<Composer
							applicationId={application.id}
							to={application.contact.email}
							subject={application.title}
							{letters}
							oncancel={() => (writing_to = false)}
						/>
					</div>
				{/if}
				<h2 id="timeline-title" class="mb-3 text-2xl font-extrabold text-ink">Chronologie</h2>
				<form
					class="mb-5 grid gap-3 bg-paper px-4 py-4 sm:grid-cols-[minmax(0,1fr)_10rem]"
					onsubmit={addEvent}
				>
					<label class="grid gap-1">
						<span class="text-sm font-bold">Événement</span>
						<select
							bind:value={kind}
							class="rounded-sm border-ink/40 focus:border-ink focus:ring-ink"
						>
							{#each EVENT_TYPES as value (value)}<option {value}>{eventLabels[value]}</option
								>{/each}
						</select>
					</label>
					<label class="grid gap-1">
						<span class="text-sm font-bold">Date</span>
						<input
							type="date"
							bind:value={day}
							required
							class="rounded-sm border-ink/40 tabular-nums focus:border-ink focus:ring-ink"
						/>
					</label>
					<label class="grid gap-1 sm:col-span-2">
						<span class="text-sm font-bold">Note</span>
						<input
							bind:value={note}
							maxlength="2000"
							placeholder="Facultatif"
							class="rounded-sm border-ink/40 focus:border-ink focus:ring-ink"
						/>
					</label>
					<div><Button type="submit" disabled={!day}>Ajouter</Button></div>
				</form>

				{#if application.events.length === 0}
					<p class="text-ink-soft">Rien encore. Le premier événement est souvent l’envoi.</p>
				{:else}
					<ol class="relative grid gap-3 border-l-2 border-ink/30 pl-5">
						{#each application.events as entry (entry.id)}
							<li class="relative">
								<span
									class="absolute top-1.5 -left-[1.6rem] size-2.5 rounded-full bg-ink ring-4 ring-desk"
									aria-hidden="true"
								></span>
								<div class="flex flex-wrap items-baseline gap-x-3">
									<span class="font-extrabold text-ink">{eventLabels[entry.type]}</span>
									<span class="text-sm text-ink-soft tabular-nums"
										>{formatDate(entry.occurred_at)}</span
									>
									<button
										type="button"
										onclick={() => removeEvent(entry.id)}
										aria-label="Retirer : {eventLabels[entry.type]} du {formatDate(
											entry.occurred_at
										)}"
										class="cursor-pointer text-sm text-ink-soft underline underline-offset-4"
									>
										Retirer
									</button>
								</div>
								{#if entry.note}<p class="mt-0.5">{entry.note}</p>{/if}
								{#if entry.message_id}
									<a
										href={resolve('/courrier/[id]', { id: String(entry.message_id) })}
										class="text-sm font-bold text-ink">Voir le message</a
									>
								{/if}
							</li>
						{/each}
					</ol>
				{/if}
			</section>

			<aside class="grid content-start gap-6">
				<BristolCard title="Lettre de motivation" colour="green">
					{#if letters.length}
						<ul class="mb-3 grid gap-1">
							{#each letters as letter (letter.id)}
								<li>
									<a
										href={resolve('/lettres/[id]', { id: String(letter.id) })}
										class="font-bold text-ink">Lettre du {formatDateTime(letter.created_at)}</a
									>
								</li>
							{/each}
						</ul>
					{/if}
					<Button onclick={writeLetter} disabled={writing}>
						{letters.length ? 'Rédiger une autre lettre' : 'Rédiger une lettre'}
					</Button>
					{#if writing}
						<p role="status" class="mt-2 text-sm">
							Le modèle rédige les trois passages, une dizaine de secondes…
						</p>
					{/if}
					{#if letterFailure}
						<p role="alert" class="mt-2 bg-alert px-3 py-2 text-sm font-bold text-white">
							{letterFailure}
						</p>
					{/if}
					<p class="mt-3 text-sm">
						Appuyée sur le CV adapté à l’offre s’il existe, sinon sur tout votre CV, et sur vos
						notes ci-dessous.
					</p>
				</BristolCard>

				<BristolCard title="Courrier" colour="yellow">
					<div class="mb-3">
						<Button onclick={() => (writing_to = true)} disabled={writing_to}>
							Écrire au contact
						</Button>
					</div>
					{#if application.messages.length}
						<ul class="grid gap-2">
							{#each application.messages as message (message.id)}
								<li>
									<a
										href={resolve('/courrier/[id]', { id: String(message.id) })}
										class="block font-bold break-words text-ink"
										>{message.subject || '(sans objet)'}</a
									>
									<span class="text-sm"
										>{senderName(message.from_addr)} · {formatDateTime(
											message.received_at
										)}{#if message.category}
											· {categoryLabels[message.category]}{/if}</span
									>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="text-sm">
							Aucun message rattaché. Le Courrier les rattache par le fil, l’adresse du contact ou
							le nom de l’entreprise.
						</p>
					{/if}
				</BristolCard>

				<BristolCard title="Notes sur l’entreprise" colour="lilac">
					<form class="grid gap-2" onsubmit={saveNotes}>
						<label class="grid gap-1">
							<span class="sr-only">Notes sur l’entreprise</span>
							<textarea
								bind:value={notes}
								rows="4"
								maxlength="10000"
								placeholder="Ce que vous savez de l’équipe, du produit, d’une rencontre…"
								class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
							></textarea>
						</label>
						<p class="text-sm">Seule source, avec l’offre, des faits du passage « motivation ».</p>
						<div class="flex items-center gap-3">
							<Button type="submit">Enregistrer les notes</Button>
							{#if notesSaved}<span role="status" class="text-sm font-bold">Enregistrées.</span
								>{/if}
						</div>
					</form>
				</BristolCard>

				<BristolCard title="Contact" colour="blue">
					<form class="grid gap-3" onsubmit={saveContact}>
						<label class="grid gap-1">
							<span class="text-sm font-bold">Nom</span>
							<input
								bind:value={contactName}
								maxlength="200"
								class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
							/>
						</label>
						<label class="grid gap-1">
							<span class="text-sm font-bold">E-mail</span>
							<input
								bind:value={contactEmail}
								type="email"
								maxlength="254"
								class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
							/>
						</label>
						<label class="grid gap-1">
							<span class="text-sm font-bold">Téléphone</span>
							<input
								bind:value={contactPhone}
								maxlength="50"
								class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
							/>
						</label>
						<p class="text-sm">Sert à adresser un message ; jamais envoyé seul au modèle.</p>
						<div class="flex items-center gap-3">
							<Button type="submit">Enregistrer le contact</Button>
							{#if contactSaved}<span role="status" class="text-sm font-bold">Enregistré.</span
								>{/if}
						</div>
					</form>
				</BristolCard>

				<div>
					{#if confirming}
						<p class="mb-2">La candidature sera masquée ; son historique est gardé.</p>
						<div class="flex gap-2">
							<Button onclick={remove}>Supprimer</Button>
							<Button variant="quiet" onclick={() => (confirming = false)}>Annuler</Button>
						</div>
					{:else}
						<Button variant="quiet" onclick={() => (confirming = true)}
							>Supprimer la candidature</Button
						>
					{/if}
				</div>
			</aside>
		</div>
	{/if}
</div>
