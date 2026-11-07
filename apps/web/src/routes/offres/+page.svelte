<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import { remoteLabels, salaryLabel, type Offer } from '#lib/offers/format.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	let offers = $state.raw<Offer[] | null>(null);
	let unavailable = $state(false);
	let text = $state('');
	let sending = $state(false);
	let failure = $state<string | null>(null);
	let notice = $state<string | null>(null);
	let fresh = $state<Set<number>>(new Set());

	async function load() {
		try {
			const { data } = await api.GET('/api/offers');
			if (!data) throw new Error('no offers');
			offers = data;
			unavailable = false;
		} catch {
			unavailable = true;
		}
	}

	onMount(load);

	async function intake(event: SubmitEvent) {
		event.preventDefault();
		sending = true;
		failure = null;
		notice = null;
		try {
			const { data, error } = await api.POST('/api/offers/intake', {
				body: { text: text.trim() }
			});
			if (!data) {
				failure = error && 'message' in error ? error.message : 'L’extraction a échoué.';
				return;
			}
			const created = data.offers.length - data.merged_ids.length;
			notice = [
				created ? `${created} offre${created > 1 ? 's' : ''} ajoutée${created > 1 ? 's' : ''}` : '',
				data.merged_ids.length
					? `${data.merged_ids.length} déjà connue${data.merged_ids.length > 1 ? 's' : ''}, complétée${data.merged_ids.length > 1 ? 's' : ''}`
					: ''
			]
				.filter(Boolean)
				.join(', ');
			fresh = new Set(data.offers.map((offer) => offer.id));
			text = '';
			await load();
		} catch {
			failure = 'Le serveur ne répond pas. Le texte est gardé : réessayez.';
		} finally {
			sending = false;
		}
	}
</script>

<svelte:head>
	<title>Offres | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Offres</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Collez une offre, une alerte ou un récapitulatif : le modèle en tire chaque poste, et le code
		range. Une offre déjà connue est complétée, jamais dupliquée.
	</p>

	<BristolCard title="Coller des offres" colour="green">
		<form class="grid gap-3" onsubmit={intake}>
			<label class="grid gap-1">
				<span class="sr-only">Texte des offres</span>
				<textarea
					bind:value={text}
					rows="6"
					maxlength="50000"
					placeholder="Le texte de l’annonce, d’une alerte ou d’un e-mail, tel quel."
					class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"></textarea>
			</label>
			{#if failure}
				<p role="alert" class="bg-alert px-4 py-2 font-bold text-white">{failure}</p>
			{/if}
			<div class="flex flex-wrap items-center gap-4">
				<Button type="submit" disabled={!text.trim() || sending}>Extraire les offres</Button>
				{#if sending}
					<p role="status" class="text-ink-soft">Lecture du texte, quelques secondes…</p>
				{:else if notice}
					<p role="status" class="font-bold text-ink">{notice}.</p>
				{/if}
			</div>
		</form>
	</BristolCard>

	<section aria-labelledby="offers-title" class="mt-10">
		<h2 id="offers-title" class="mb-3 text-2xl font-extrabold text-ink">
			Offres reçues{#if offers}<span class="ml-2 text-lg text-ink-soft">{offers.length}</span>{/if}
		</h2>
		{#if unavailable}
			<div role="alert">
				<p class="font-extrabold text-ink">Le serveur ne répond pas.</p>
				<Button onclick={load}>Réessayer</Button>
			</div>
		{:else if offers === null}
			<p class="text-ink-soft" role="status">Chargement…</p>
		{:else if offers.length === 0}
			<p class="text-ink-soft">Aucune offre pour l’instant.</p>
		{:else}
			<div class="overflow-x-auto bg-paper">
				<table class="w-full min-w-[48rem] text-left">
					<thead>
						<tr class="border-b-2 border-ink text-sm text-ink-soft">
							<th class="px-4 py-2 font-bold">Poste</th>
							<th class="py-2 pr-4 font-bold">Lieu</th>
							<th class="py-2 pr-4 font-bold">Contrat</th>
							<th class="py-2 pr-4 font-bold">Télétravail</th>
							<th class="py-2 pr-4 font-bold">Salaire</th>
							<th class="py-2 pr-4 font-bold">Reçue</th>
						</tr>
					</thead>
					<tbody>
						{#each offers as offer (offer.id)}
							<tr class={['border-b border-ink/10', fresh.has(offer.id) && 'bg-bristol-green/40']}>
								<td class="px-4 py-2">
									<a
										href={resolve('/offres/[id]', { id: String(offer.id) })}
										class="font-extrabold text-ink">{offer.title}</a
									>
									<span class="block text-sm text-ink-soft"
										>{offer.company_name || 'Entreprise non nommée'}</span
									>
								</td>
								<td class="py-2 pr-4">{offer.location || '—'}</td>
								<td class="py-2 pr-4">{offer.contract || '—'}</td>
								<td class="py-2 pr-4">{remoteLabels[offer.remote]}</td>
								<td class="py-2 pr-4 whitespace-nowrap tabular-nums">{salaryLabel(offer)}</td>
								<td class="py-2 pr-4 text-sm whitespace-nowrap text-ink-soft">
									{formatDateTime(offer.created_at)}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
</div>
