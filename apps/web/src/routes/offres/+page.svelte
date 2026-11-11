<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import { remoteLabels, salaryLabel, standing, type ScoredOffer } from '#lib/offers/format.ts';
	import ScoreBadge from '#lib/offers/ScoreBadge.svelte';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	type Standing = ReturnType<typeof standing>;
	const STATUS: Record<Standing, { label: string; colour: string }> = {
		applied: { label: 'Candidature', colour: 'bg-bristol-blue' },
		open: { label: 'À examiner', colour: 'bg-postit' },
		shortlisted: { label: 'Retenue', colour: 'bg-bristol-green' },
		dismissed: { label: 'Écartée', colour: 'bg-bristol-grey' },
		filtered: { label: 'Filtrée', colour: 'bg-bristol-salmon' }
	};

	let offers = $state.raw<ScoredOffer[] | null>(null);
	let byScore = $state(true);
	let stale = $state(0);
	let rescoring = $state(false);
	let unavailable = $state(false);
	let text = $state('');
	let sending = $state(false);
	let failure = $state<string | null>(null);
	let notice = $state<string | null>(null);
	let fresh = $state<Set<number>>(new Set());

	async function load() {
		try {
			const [{ data }, { data: count }] = await Promise.all([
				api.GET('/api/offers'),
				api.GET('/api/offers/stale')
			]);
			if (!data) throw new Error('no offers');
			offers = data;
			stale = count?.count ?? 0;
			unavailable = false;
		} catch {
			unavailable = true;
		}
	}

	async function rescore() {
		rescoring = true;
		failure = null;
		try {
			const { data, error } = await api.POST('/api/offers/rescore');
			if (!data) {
				failure = error && 'message' in error ? error.message : 'La notation a échoué.';
				return;
			}
			if (data.error) failure = `Notation interrompue : ${data.error}.`;
			await load();
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			rescoring = false;
		}
	}

	let shown = $derived.by(() => {
		const all = offers ?? [];
		if (!byScore) return all;
		const value = (offer: ScoredOffer) => offer.current_score?.fit_score ?? -1;
		return [...all].sort((a, b) => value(b) - value(a));
	});

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
			const parts = [
				created ? `${created} offre${created > 1 ? 's' : ''} ajoutée${created > 1 ? 's' : ''}` : '',
				data.merged_ids.length
					? `${data.merged_ids.length} déjà connue${data.merged_ids.length > 1 ? 's' : ''}, complétée${data.merged_ids.length > 1 ? 's' : ''}`
					: ''
			].filter(Boolean);
			notice = parts.join(', ');
			if (data.scoring_error)
				failure = `Offres gardées, mais ${data.unscored_ids.length} non notée${data.unscored_ids.length > 1 ? 's' : ''} : ${data.scoring_error}. Réessayez depuis la liste.`;
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
					<p role="status" class="text-ink-soft">
						Lecture du texte, puis notation de chaque offre, quelques secondes…
					</p>
				{:else if notice}
					<p role="status" class="font-bold text-ink">{notice}.</p>
				{/if}
			</div>
		</form>
	</BristolCard>

	<section aria-labelledby="offers-title" class="mt-10">
		<div class="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
			<h2 id="offers-title" class="text-2xl font-extrabold text-ink">
				Offres reçues{#if offers}<span class="ml-2 text-lg text-ink-soft">{offers.length}</span
					>{/if}
			</h2>
			{#if stale > 0}
				<p class="flex flex-wrap items-center gap-3 bg-postit px-3 py-1.5">
					<span>
						<span class="font-bold">{stale} offre{stale > 1 ? 's' : ''} à noter</span>
						: jamais notée{stale > 1 ? 's' : ''}, ou objectifs et CV changés depuis.
					</span>
					<Button variant="quiet" disabled={rescoring} onclick={rescore}>
						{rescoring ? 'Notation…' : 'Noter maintenant'}
					</Button>
				</p>
			{/if}
		</div>

		{#if offers && offers.length}
			<div class="mb-3 flex flex-wrap items-center justify-end gap-3">
				<label class="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						bind:checked={byScore}
						class="rounded-sm border-ink text-ink focus:ring-ink"
					/>
					Trier par score
				</label>
			</div>
		{/if}

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
				<table class="w-full min-w-[52rem] text-left">
					<thead>
						<tr class="border-b-2 border-ink text-sm text-ink-soft">
							<th class="py-2 pr-2 pl-4 font-bold">Adéquation</th>
							<th class="py-2 pr-4 font-bold">Statut</th>
							<th class="py-2 pr-4 font-bold">Poste</th>
							<th class="py-2 pr-4 font-bold">Lieu</th>
							<th class="py-2 pr-4 font-bold">Contrat</th>
							<th class="py-2 pr-4 font-bold">Télétravail</th>
							<th class="py-2 pr-4 font-bold">Salaire</th>
							<th class="py-2 pr-4 font-bold">Reçue</th>
						</tr>
					</thead>
					<tbody>
						{#each shown as offer (offer.id)}
							{@const status = STATUS[standing(offer)]}
							{@const aside = standing(offer) === 'dismissed' || standing(offer) === 'filtered'}
							<tr
								class={[
									'border-b border-ink/10',
									fresh.has(offer.id) && 'bg-bristol-green/40',
									aside && 'text-ink-soft'
								]}
							>
								<td class="py-2 pr-2 pl-4"><ScoreBadge {offer} /></td>
								<td class="py-2 pr-4">
									{#if offer.application_id}
										<a
											href={resolve('/candidatures/[id]', { id: String(offer.application_id) })}
											title="Voir la candidature"
											class={[
												'px-2 py-0.5 text-sm font-bold whitespace-nowrap text-ink underline-offset-4 hover:underline',
												status.colour
											]}>{status.label} →</a
										>
									{:else}
										<span class={['px-2 py-0.5 text-sm font-bold whitespace-nowrap', status.colour]}
											>{status.label}</span
										>
									{/if}
								</td>
								<td class="py-2 pr-4">
									<a
										href={resolve('/offres/[id]', { id: String(offer.id) })}
										class="font-extrabold text-ink">{offer.title}</a
									>
									<span class="block text-sm text-ink-soft">
										{offer.company_name || 'Entreprise non nommée'}
									</span>
								</td>
								<td class="py-2 pr-4">{offer.locations.join(', ') || '—'}</td>
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
