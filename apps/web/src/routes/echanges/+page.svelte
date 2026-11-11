<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { statusColours, statusLabel, type ActionSummary } from '#lib/actions/format.ts';
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
	let actions = $state.raw<ActionSummary[] | null>(null);
	let mailbox = $state.raw<MailboxStatus | null>(null);
	let unavailable = $state(false);
	type Filter = 'all' | 'waiting' | 'todo' | 'received' | 'sent' | 'alert' | 'hidden';
	let filter = $state<Filter>('all');
	let syncing = $state(false);
	let report = $state.raw<SyncReport | null>(null);
	let failure = $state<string | null>(null);

	async function load() {
		try {
			const [list, put, current, queue] = await Promise.all([
				api.GET('/api/mail/messages'),
				api.GET('/api/mail/messages', { params: { query: { hidden: true } } }),
				api.GET('/api/mail/status'),
				api.GET('/api/actions')
			]);
			if (!list.data || !current.data || !queue.data) throw new Error('no exchanges');
			messages = list.data;
			hidden = put.data ?? [];
			mailbox = current.data;
			actions = queue.data;
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

	/** One line of the list: a message received, or a send through the queue. */
	type Entry =
		| { type: 'received'; at: string; message: MessageSummary }
		| { type: 'sent'; at: string; action: ActionSummary };

	const received = (list: MessageSummary[]): Entry[] =>
		list.map((message) => ({ type: 'received', at: message.received_at, message }));
	const sent = (list: ActionSummary[]): Entry[] =>
		list.map((action) => ({ type: 'sent', at: action.sent_at ?? action.created_at, action }));
	const isWaiting = (entry: Entry) => entry.type === 'sent' && entry.action.status === 'proposed';

	/** What waits for a click comes first, then everything by date, newest first. */
	const ordered = (entries: Entry[]) =>
		entries.toSorted(
			(a, b) => Number(isWaiting(b)) - Number(isWaiting(a)) || b.at.localeCompare(a.at)
		);

	let waiting = $derived((actions ?? []).filter((action) => action.status === 'proposed'));
	let todo = $derived((messages ?? []).filter(needsAttention));
	let filters = $derived<{ value: Filter; label: string; count?: number }[]>([
		{ value: 'all', label: 'Tout' },
		{ value: 'waiting', label: 'À valider', count: waiting.length },
		{ value: 'todo', label: 'À traiter', count: todo.length },
		{ value: 'received', label: 'Reçus' },
		{ value: 'sent', label: 'Envois' },
		{ value: 'alert', label: 'Alertes' },
		{ value: 'hidden', label: 'Masqués', count: hidden.length }
	]);
	let shown = $derived.by((): Entry[] => {
		const inbox = messages ?? [];
		const queue = actions ?? [];
		switch (filter) {
			case 'waiting':
				return ordered(sent(waiting));
			case 'todo':
				return ordered(received(todo));
			case 'received':
				return ordered(received(inbox));
			case 'sent':
				return ordered(sent(queue));
			case 'alert':
				return ordered(received(inbox.filter((message) => message.kind === 'alert')));
			case 'hidden':
				return ordered(received(hidden));
			default:
				return ordered([...received(inbox), ...sent(queue)]);
		}
	});

	const emptyLabels: Record<Filter, string> = {
		all: 'Rien pour l’instant : synchronisez la boîte.',
		waiting: 'Rien à valider. Un envoi se prépare depuis un message reçu ou une candidature.',
		todo: 'Rien à traiter.',
		received: 'Aucun message reçu : synchronisez la boîte.',
		sent: 'Aucun envoi. Un envoi se prépare depuis un message reçu ou une candidature.',
		alert: 'Aucune alerte d’emploi.',
		hidden: 'Aucun message masqué.'
	};

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

	function describe(action: ActionSummary): string {
		const parts = [`À ${action.to.join(', ')}`];
		if (action.application_title) parts.push(action.application_title);
		if (action.attachments)
			parts.push(`${action.attachments} pièce${action.attachments > 1 ? 's jointes' : ' jointe'}`);
		return parts.join(' · ');
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
	<title>Échanges | Jobingo</title>
</svelte:head>

{#snippet receivedRow(message: MessageSummary)}
	<li class="grid gap-x-4 px-4 py-3 sm:grid-cols-[7rem_minmax(0,1fr)_auto]">
		<span class="flex items-center gap-1.5 self-start">
			<span aria-hidden="true" class="w-3 font-extrabold text-ink-soft">↓</span>
			<span class={['w-fit px-2 text-sm font-bold', badge(message).colour]}>
				{badge(message).label}
			</span>
		</span>
		<div class="min-w-0">
			<a
				href={resolve('/echanges/recus/[id]', { id: String(message.id) })}
				class="block truncate font-extrabold text-ink">{message.subject || '(sans objet)'}</a
			>
			<p class="truncate text-sm text-ink-soft">
				De <span class="font-bold">{senderName(message.from_addr)}</span> — {message.summary ||
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
{/snippet}

{#snippet sentRow(action: ActionSummary)}
	<li class="grid gap-x-4 px-4 py-3 sm:grid-cols-[7rem_minmax(0,1fr)_auto]">
		<span class="flex items-center gap-1.5 self-start">
			<span aria-hidden="true" class="w-3 font-extrabold text-ink-soft">↑</span>
			<span class={['w-fit px-2 text-sm font-bold', statusColours[action.status]]}>
				{statusLabel(action)}
			</span>
		</span>
		<div class="min-w-0">
			<a
				href={resolve('/echanges/envois/[id]', { id: String(action.id) })}
				class="block truncate font-extrabold text-ink">{action.subject}</a
			>
			<p class="truncate text-sm text-ink-soft">{describe(action)}</p>
		</div>
		<span class="text-sm whitespace-nowrap text-ink-soft sm:text-right">
			{formatDateTime(action.sent_at ?? action.created_at)}
		</span>
	</li>
{/snippet}

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Échanges</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Ce que vous recevez et ce qui part, au même endroit. Les alertes d’emploi deviennent des offres
		; les autres messages sont classés par l’IA et rattachés à leur candidature par le code. Rien ne
		part sans votre validation, sur l’aperçu exact de ce qui partira.
	</p>

	<div class="grid gap-x-8 gap-y-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
		<section aria-labelledby="list-title" class="min-w-0">
			<h2 id="list-title" class="sr-only">Messages et envois</h2>
			<div role="group" aria-label="Filtrer" class="mb-3 flex flex-wrap gap-1">
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

			{#if unavailable}
				<div role="alert">
					<p class="font-extrabold text-ink">Le serveur ne répond pas.</p>
					<Button onclick={load}>Réessayer</Button>
				</div>
			{:else if messages === null || actions === null}
				<p class="text-ink-soft" role="status">Chargement…</p>
			{:else if shown.length === 0}
				<p class="text-ink-soft">{emptyLabels[filter]}</p>
			{:else}
				<ul class="divide-y divide-ink/10 bg-paper">
					{#each shown as entry (`${entry.type}-${entry.type === 'sent' ? entry.action.id : entry.message.id}`)}
						{#if entry.type === 'sent'}
							{@render sentRow(entry.action)}
						{:else}
							{@render receivedRow(entry.message)}
						{/if}
					{/each}
				</ul>
			{/if}
		</section>

		<div class="grid content-start gap-8">
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

			<BristolCard title="Garde-fous" colour="green">
				<ul class="grid gap-2 text-sm">
					<li>Le modèle n’envoie rien : il n’a aucun outil.</li>
					<li>
						Le contenu est figé à la préparation. Valider, c’est valider son empreinte SHA-256 :
						s’il change, rien ne part.
					</li>
					<li>Les PDF joints sont archivés et vérifiés octet par octet à l’envoi.</li>
					<li>Un double clic n’envoie qu’une fois. Rien n’est jamais effacé.</li>
				</ul>
			</BristolCard>
		</div>
	</div>
</div>
