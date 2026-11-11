<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import {
		eventLabels,
		formatDate,
		today,
		type ApplicationSummary
	} from '#lib/applications/format.ts';
	import StatusPill from '#lib/applications/StatusPill.svelte';
	import Stars from '#lib/ui/Stars.svelte';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	let applications = $state.raw<ApplicationSummary[] | null>(null);
	let unavailable = $state(false);
	let title = $state('');
	let company = $state('');
	let failure = $state<string | null>(null);

	async function load() {
		try {
			const { data } = await api.GET('/api/applications');
			if (!data) throw new Error('no applications');
			applications = data;
			unavailable = false;
		} catch {
			unavailable = true;
		}
	}

	onMount(load);

	async function create(event: SubmitEvent) {
		event.preventDefault();
		failure = null;
		try {
			const { data } = await api.POST('/api/applications', {
				body: { title: title.trim(), company_name: company.trim() }
			});
			if (!data) {
				failure = 'Cette candidature est refusée.';
				return;
			}
			await goto(resolve('/candidatures/[id]', { id: String(data.id) }));
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		}
	}

	const now = today();
	let due = $derived(
		(applications ?? []).filter((a) => a.follow_up_on !== null && a.follow_up_on <= now).length
	);
</script>

<svelte:head>
	<title>Candidatures | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Candidatures</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Le statut de chaque candidature découle de ce qui s’est passé : notez les événements, il suit.
		Une relance est proposée une semaine après l’envoi, si rien n’a bougé.
	</p>

	<div class="grid gap-x-8 gap-y-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
		<section aria-labelledby="list-title" class="min-w-0">
			<div class="mb-3 flex flex-wrap items-baseline gap-x-4">
				<h2 id="list-title" class="text-2xl font-extrabold text-ink">
					Suivies{#if applications}<span class="ml-2 text-lg text-ink-soft"
							>{applications.length}</span
						>{/if}
				</h2>
				{#if due}
					<p class="bg-postit px-3 py-1 font-bold">
						{due} relance{due > 1 ? 's' : ''} à faire
					</p>
				{/if}
			</div>
			{#if unavailable}
				<div role="alert">
					<p class="font-extrabold text-ink">Le serveur ne répond pas.</p>
					<Button onclick={load}>Réessayer</Button>
				</div>
			{:else if applications === null}
				<p class="text-ink-soft" role="status">Chargement…</p>
			{:else if applications.length === 0}
				<p class="text-ink-soft">
					Aucune candidature. Candidatez depuis une
					<a href={resolve('/offres')} class="font-bold text-ink">offre</a>, ou ajoutez-en une à la
					main.
				</p>
			{:else}
				<div class="overflow-x-auto bg-paper">
					<table class="w-full min-w-[44rem] text-left">
						<thead>
							<tr class="border-b-2 border-ink text-sm text-ink-soft">
								<th class="px-4 py-2 font-bold">Statut</th>
								<th class="py-2 pr-4 font-bold">Poste</th>
								<th class="py-2 pr-4 font-bold">Dernier événement</th>
								<th class="py-2 pr-4 font-bold">Relance</th>
							</tr>
						</thead>
						<tbody>
							{#each applications as application (application.id)}
								{@const late = application.follow_up_on !== null && application.follow_up_on <= now}
								<tr class="border-b border-ink/10">
									<td class="px-4 py-2">
										<StatusPill status={application.status} tone={application.tone} />
									</td>
									<td class="py-2 pr-4">
										<a
											href={resolve('/candidatures/[id]', { id: String(application.id) })}
											class="font-extrabold text-ink">{application.title}</a
										>
										<span class="block text-sm text-ink-soft"
											>{application.company_name || 'Entreprise non nommée'}</span
										>
										<Stars value={application.rating} label="Votre note" size="sm" />
									</td>
									<td class="py-2 pr-4 text-sm">
										{#if application.last_event}
											{eventLabels[application.last_event.type]}
											<span class="block text-ink-soft"
												>{formatDate(application.last_event.occurred_at)}</span
											>
										{:else}
											<span class="text-ink-soft">—</span>
										{/if}
									</td>
									<td class="py-2 pr-4 text-sm whitespace-nowrap">
										{#if application.follow_up_on}
											<span class={late ? 'font-bold text-alert' : ''}>
												{#if late}<span aria-hidden="true">▲ </span>{/if}{late
													? 'Due depuis le'
													: 'Le'}
												{formatDate(application.follow_up_on)}
											</span>
										{:else}
											<span class="text-ink-soft">—</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>

		<BristolCard title="Candidature spontanée" colour="yellow">
			<form class="grid gap-3" onsubmit={create}>
				<p class="text-sm">
					Sans offre : une candidature spontanée, ou une recommandation. Les autres naissent d’une
					<a href={resolve('/offres')} class="font-bold text-ink">offre</a>.
				</p>
				<label class="grid gap-1">
					<span class="font-bold">Poste</span>
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
				{#if failure}<p role="alert" class="bg-alert px-3 py-2 font-bold text-white">
						{failure}
					</p>{/if}
				<div>
					<Button type="submit" disabled={!title.trim()}>Créer la candidature spontanée</Button>
				</div>
			</form>
		</BristolCard>
	</div>
</div>
