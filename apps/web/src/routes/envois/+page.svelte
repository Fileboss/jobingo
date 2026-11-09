<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { statusColours, statusLabel, type ActionSummary } from '#lib/actions/format.ts';
	import { api } from '#lib/api/client.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	let actions = $state.raw<ActionSummary[] | null>(null);
	let unavailable = $state(false);

	async function load() {
		try {
			const { data } = await api.GET('/api/actions');
			if (!data) throw new Error('no actions');
			actions = data;
			unavailable = false;
		} catch {
			unavailable = true;
		}
	}

	onMount(load);

	function describe(action: ActionSummary): string {
		const parts = [`À ${action.to.join(', ')}`];
		if (action.application_title) parts.push(action.application_title);
		if (action.attachments)
			parts.push(`${action.attachments} pièce${action.attachments > 1 ? 's jointes' : ' jointe'}`);
		return parts.join(' · ');
	}

	let waiting = $derived((actions ?? []).filter((action) => action.status === 'proposed'));
	let done = $derived((actions ?? []).filter((action) => action.status !== 'proposed'));
</script>

<svelte:head>
	<title>Envois | Jobingo</title>
</svelte:head>

{#snippet row(action: ActionSummary)}
	<li class="grid gap-x-4 px-4 py-3 sm:grid-cols-[7rem_minmax(0,1fr)_auto]">
		<span class={['w-fit self-start px-2 text-sm font-bold', statusColours[action.status]]}>
			{statusLabel(action)}
		</span>
		<div class="min-w-0">
			<a
				href={resolve('/envois/[id]', { id: String(action.id) })}
				class="block truncate font-extrabold text-ink">{action.subject}</a
			>
			<p class="truncate text-sm text-ink-soft">
				{describe(action)}
			</p>
		</div>
		<span class="text-sm whitespace-nowrap text-ink-soft sm:text-right">
			{formatDateTime(action.sent_at ?? action.created_at)}
		</span>
	</li>
{/snippet}

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Envois</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Tout ce qui part passe par ici : un envoi préparé attend votre validation, sur l’aperçu exact de
		ce qui partira. Un seul module envoie, et seulement ce que vous avez validé.
	</p>

	<div class="grid gap-x-8 gap-y-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
		<div class="grid min-w-0 content-start gap-8">
			{#if unavailable}
				<div role="alert">
					<p class="font-extrabold text-ink">Le serveur ne répond pas.</p>
					<Button onclick={load}>Réessayer</Button>
				</div>
			{:else if actions === null}
				<p class="text-ink-soft" role="status">Chargement…</p>
			{:else}
				<section aria-labelledby="waiting-title">
					<h2 id="waiting-title" class="mb-3 text-2xl font-extrabold text-ink">
						À valider<span class="ml-2 text-lg text-ink-soft">{waiting.length}</span>
					</h2>
					{#if waiting.length}
						<ul class="divide-y divide-ink/10 bg-paper">
							{#each waiting as action (action.id)}{@render row(action)}{/each}
						</ul>
					{:else}
						<p class="text-ink-soft">
							Rien à valider. Un envoi se prépare depuis un message du Courrier ou une candidature.
						</p>
					{/if}
				</section>
				{#if done.length}
					<section aria-labelledby="done-title">
						<h2 id="done-title" class="mb-3 text-2xl font-extrabold text-ink">Historique</h2>
						<ul class="divide-y divide-ink/10 bg-paper">
							{#each done as action (action.id)}{@render row(action)}{/each}
						</ul>
					</section>
				{/if}
			{/if}
		</div>

		<BristolCard title="Garde-fous" colour="green">
			<ul class="grid gap-2 text-sm">
				<li>Le modèle n’envoie rien : il n’a aucun outil.</li>
				<li>
					Le contenu est figé à la préparation. Valider, c’est valider son empreinte SHA-256 : s’il
					change, rien ne part.
				</li>
				<li>Les PDF joints sont archivés et vérifiés octet par octet à l’envoi.</li>
				<li>Un double clic n’envoie qu’une fois. Rien n’est jamais effacé.</li>
			</ul>
		</BristolCard>
	</div>
</div>
