<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import {
		categoryLabels,
		needsAttention,
		senderName,
		syncSummary,
		type MailboxStatus,
		type MessageSummary,
		type SyncReport
	} from '#lib/mail/format.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	let messages = $state.raw<MessageSummary[] | null>(null);
	let hidden = $state.raw<MessageSummary[]>([]);
	let mailbox = $state.raw<MailboxStatus | null>(null);
	let unavailable = $state(false);
	type Filter = 'all' | 'todo' | 'alert' | 'hidden';
	let filter = $state<Filter>('all');
	let syncing = $state(false);
	let report = $state.raw<SyncReport | null>(null);
	let failure = $state<string | null>(null);

	async function load() {
		try {
			const [list, put, current] = await Promise.all([
				api.GET('/api/mail/messages'),
				api.GET('/api/mail/messages', { params: { query: { hidden: true } } }),
				api.GET('/api/mail/status')
			]);
			if (!list.data || !current.data) throw new Error('no mail');
			messages = list.data;
			hidden = put.data ?? [];
			mailbox = current.data;
			unavailable = false;
		} catch {
			unavailable = true;
		}
	}

	onMount(load);

	async function sync() {
		syncing = true;
		failure = null;
		report = null;
		try {
			const { data, error } = await api.POST('/api/mail/sync');
			if (error) failure = error.message;
			else if (data) report = data;
			await load();
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			syncing = false;
		}
	}

	let todo = $derived((messages ?? []).filter(needsAttention));
	let filters = $derived<{ value: Filter; label: string; count?: number }[]>([
		{ value: 'all', label: 'Tout' },
		{ value: 'todo', label: 'À traiter', count: todo.length },
		{ value: 'alert', label: 'Alertes' },
		{ value: 'hidden', label: 'Masqués', count: hidden.length }
	]);
	let shown = $derived(
		filter === 'hidden'
			? hidden
			: filter === 'todo'
				? todo
				: (messages ?? []).filter((message) => filter === 'all' || message.kind === filter)
	);

	const categoryColours = {
		offer: 'bg-bristol-green',
		rejection: 'bg-bristol-salmon',
		interview: 'bg-bristol-blue',
		recruiter_other: 'bg-bristol-lilac',
		other: 'bg-bristol-grey'
	} as const;

	function badge(message: MessageSummary): { label: string; colour: string } {
		if (message.kind === 'alert') return { label: 'Alerte', colour: 'bg-bristol-yellow' };
		if (message.category)
			return {
				label: categoryLabels[message.category],
				colour: categoryColours[message.category]
			};
		return { label: message.hidden_reason ? 'Masqué' : 'À classer', colour: 'bg-bristol-grey' };
	}
	let lastSync = $derived(
		(mailbox?.folders ?? [])
			.map((folder) => folder.synced_at)
			.filter((at): at is string => at !== null)
			.sort()
			.at(-1)
	);
</script>

<svelte:head>
	<title>Courrier | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Courrier</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Les alertes d’emploi deviennent des offres, notées selon vos objectifs. Les autres messages sont
		classés par l’IA et rattachés à leur candidature par le code ; un refus ou un entretien ne
		change la candidature que sur votre clic.
	</p>

	<div class="grid gap-x-8 gap-y-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
		<section aria-labelledby="list-title" class="min-w-0">
			<div class="mb-3 flex flex-wrap items-baseline gap-x-6 gap-y-2">
				<h2 id="list-title" class="text-2xl font-extrabold text-ink">
					Reçus{#if messages}<span class="ml-2 text-lg text-ink-soft">{messages.length}</span>{/if}
				</h2>
				<div role="group" aria-label="Filtrer" class="flex gap-1">
					{#each filters as option (option.value)}
						<button
							type="button"
							aria-pressed={filter === option.value}
							onclick={() => (filter = option.value)}
							class="cursor-pointer rounded-sm px-3 py-0.5 font-bold text-ink aria-pressed:bg-ink aria-pressed:text-white"
						>
							{option.label}{#if option.count}<span class="ml-1.5 tabular-nums">{option.count}</span
								>{/if}
						</button>
					{/each}
				</div>
			</div>

			{#if unavailable}
				<div role="alert">
					<p class="font-extrabold text-ink">Le serveur ne répond pas.</p>
					<Button onclick={load}>Réessayer</Button>
				</div>
			{:else if messages === null}
				<p class="text-ink-soft" role="status">Chargement…</p>
			{:else if shown.length === 0}
				<p class="text-ink-soft">
					{messages.length === 0 && filter === 'all'
						? 'Aucun message pour l’instant : synchronisez la boîte.'
						: filter === 'todo'
							? 'Rien à traiter.'
							: 'Aucun message de ce type.'}
				</p>
			{:else}
				<ul class="divide-y divide-ink/10 bg-paper">
					{#each shown as message (message.id)}
						<li class="grid gap-x-4 px-4 py-3 sm:grid-cols-[6.5rem_minmax(0,1fr)_auto]">
							<span class={['w-fit self-start px-2 text-sm font-bold', badge(message).colour]}>
								{badge(message).label}
							</span>
							<div class="min-w-0">
								<a
									href={resolve('/courrier/[id]', { id: String(message.id) })}
									class="block truncate font-extrabold text-ink"
									>{message.subject || '(sans objet)'}</a
								>
								<p class="truncate text-sm text-ink-soft">
									<span class="font-bold">{senderName(message.from_addr)}</span> — {message.summary ||
										message.excerpt}
								</p>
							</div>
							<div class="text-sm whitespace-nowrap sm:text-right">
								<span class="text-ink-soft">{formatDateTime(message.received_at)}</span>
								{#if message.offer_count}
									<span class="block font-bold text-ink"
										>{message.offer_count} offre{message.offer_count > 1 ? 's' : ''}</span
									>
								{/if}
								{#if message.application_title}
									<span class="block max-w-[16rem] truncate font-bold text-ink"
										>→ {message.application_title}</span
									>
								{/if}
								{#if message.suggestion?.status === 'pending'}
									<span class="mt-0.5 inline-block bg-postit px-2 font-bold">À confirmer</span>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<BristolCard title="Boîte lue" colour="blue">
			{#if mailbox}
				<p class="font-extrabold break-all text-ink">{mailbox.address}</p>
				<p class="text-sm">
					{mailbox.local
						? 'Serveur local de démonstration : rien ne quitte cette machine.'
						: `Serveur ${mailbox.host}.`}
				</p>
				<p class="mt-3 text-sm">
					Lecture seule : rien n’est marqué lu, déplacé ni supprimé dans la boîte.
				</p>
				<p class="mt-3 text-sm">
					{lastSync ? `Dernière lecture le ${formatDateTime(lastSync)}.` : 'Jamais lue.'}
				</p>
				{#if mailbox.waiting}
					<p class="mt-3 bg-postit px-3 py-1 text-sm font-bold">
						{mailbox.waiting} message{mailbox.waiting > 1 ? 's attendent' : ' attend'} l’IA
					</p>
				{/if}
				{#if mailbox.suggestions}
					<button
						type="button"
						onclick={() => (filter = 'todo')}
						class="mt-3 block cursor-pointer bg-postit px-3 py-1 text-left text-sm font-bold"
					>
						{mailbox.suggestions} changement{mailbox.suggestions > 1 ? 's' : ''} de statut à confirmer
					</button>
				{/if}
				<p class="mt-3 text-sm">
					Les lettres d’information et les expéditeurs bloqués sont masqués sans passer par l’IA.
				</p>
			{/if}
			<div class="mt-4">
				<Button onclick={sync} disabled={syncing || mailbox === null}>
					{syncing ? 'Lecture…' : 'Synchroniser'}
				</Button>
			</div>
			{#if report}
				<p role="status" class="mt-3 font-bold">{syncSummary(report)}</p>
				{#if report.unscored_ids.length && !report.error}
					<p class="mt-1 text-sm">
						Offres gardées sans note : l’IA n’est pas configurée. Elles se notent depuis la page
						Offres.
					</p>
				{/if}
				{#if report.error}
					<p class="mt-1 text-sm">
						Arrêté en route : {report.error}. Le reste attend la prochaine lecture.
					</p>
				{/if}
				{#if report.has_more}
					<p class="mt-1 text-sm">D’autres messages attendent : synchronisez encore.</p>
				{/if}
				{#if report.offer_ids.length}
					<a href={resolve('/offres')} class="mt-1 block font-bold text-ink">Voir les offres</a>
				{/if}
			{/if}
			{#if failure}
				<p role="alert" class="mt-3 bg-alert px-3 py-2 font-bold text-white">{failure}</p>
			{/if}
		</BristolCard>
	</div>
</div>
