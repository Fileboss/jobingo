<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import type { components } from '#lib/api/schema.d.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import { remoteLabels } from '#lib/offers/format.ts';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';
	import Tick from '#lib/ui/Tick.svelte';

	type Schemas = components['schemas'];
	type ObjectivesView = Schemas['ObjectivesView'];
	type Contract = Schemas['HardFilters']['contracts'][number];
	type Remote = Schemas['HardFilters']['remote'][number];
	type WeightName = keyof Schemas['Weights'];

	const CONTRACTS: Contract[] = ['CDI', 'CDD', 'freelance', 'stage', 'alternance', 'interim'];
	const REMOTES: Remote[] = ['sur site', 'hybride', 'remote'];
	const WEIGHTS: [WeightName, string, string][] = [
		['mission', 'Mission', 'ce que le poste fait faire'],
		['stack', 'Stack technique', 'les outils et langages'],
		['salary', 'Salaire', 'face à votre attente'],
		['culture', 'Culture', 'l’équipe et ses pratiques']
	];

	let view = $state.raw<ObjectivesView | null>(null);
	let phase = $state<'loading' | 'ready' | 'unavailable'>('loading');
	let saving = $state(false);
	let failure = $state<string | null>(null);

	let contracts = $state<Contract[]>([]);
	let remote = $state<Remote[]>([]);
	let locations = $state('');
	// A number field binds a number, or null when empty.
	let salary = $state<number | null>(null);
	let keywords = $state('');
	let companies = $state('');
	let weights = $state<Record<WeightName, number>>({ mission: 1, stack: 1, salary: 1, culture: 1 });
	let preferences = $state('');
	let savedKey = $state('');

	const list = (text: string) =>
		text
			.split(',')
			.map((term) => term.trim())
			.filter(Boolean);

	function body() {
		return {
			hard_filters: {
				contracts: [...contracts],
				remote: [...remote],
				locations: list(locations),
				salary_min_eur: salary,
				excluded_keywords: list(keywords),
				excluded_companies: list(companies)
			},
			weights: { ...weights },
			preferences: preferences.trim()
		};
	}

	function adopt(data: ObjectivesView) {
		view = data;
		const filters = data.objectives.hard_filters;
		contracts = [...(filters.contracts ?? [])];
		remote = [...(filters.remote ?? [])];
		locations = (filters.locations ?? []).join(', ');
		salary = filters.salary_min_eur ?? null;
		keywords = (filters.excluded_keywords ?? []).join(', ');
		companies = (filters.excluded_companies ?? []).join(', ');
		weights = { ...weights, ...data.objectives.weights };
		preferences = data.objectives.preferences ?? '';
		savedKey = JSON.stringify(body());
	}

	async function load() {
		try {
			const { data } = await api.GET('/api/objectives');
			if (!data) throw new Error('no objectives');
			adopt(data);
			phase = 'ready';
		} catch {
			phase = 'unavailable';
		}
	}

	onMount(load);

	async function save(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		failure = null;
		try {
			const { data } = await api.PUT('/api/objectives', { body: body() });
			if (!data) {
				failure = 'Ces objectifs sont refusés : vérifiez le salaire et les listes.';
				return;
			}
			adopt(data);
		} catch {
			failure = 'Le serveur ne répond pas. Vos réglages sont gardés : réessayez.';
		} finally {
			saving = false;
		}
	}

	function toggle<T>(values: T[], value: T, on: boolean): T[] {
		return on ? [...values, value] : values.filter((v) => v !== value);
	}

	let dirty = $derived(phase === 'ready' && JSON.stringify(body()) !== savedKey);
	let passing = $derived(view?.offers.filter((offer) => offer.passed) ?? []);
	let eliminated = $derived(view?.offers.filter((offer) => !offer.passed) ?? []);
</script>

<svelte:head>
	<title>Objectifs | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Objectifs</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Ce que vous cherchez. Les filtres et les pondérations sont appliqués par le code ; seules vos
		préférences, en texte libre, sont lues par le modèle pour noter chaque offre.
	</p>

	{#if phase === 'loading'}
		<p class="text-ink-soft" role="status">Chargement…</p>
	{:else if phase === 'unavailable'}
		<div role="alert">
			<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
			<Button onclick={load}>Réessayer</Button>
		</div>
	{:else}
		<div class="grid gap-x-8 gap-y-10 xl:grid-cols-[minmax(0,1fr)_28rem]">
			<form class="grid gap-6" onsubmit={save}>
				<BristolCard title="Filtres éliminatoires" colour="salmon" tab={0}>
					<p class="mb-4 text-sm">
						Une offre est écartée seulement si elle indique une valeur qui ne passe pas. Si elle ne
						dit rien, elle reste, et l’inconnue est signalée.
					</p>
					<div class="grid gap-5 sm:grid-cols-2">
						<fieldset>
							<legend class="mb-1 font-bold">Contrats acceptés</legend>
							<div class="flex flex-wrap gap-x-5 gap-y-1">
								{#each CONTRACTS as value (value)}
									<Tick
										checked={contracts.includes(value)}
										onchange={(on) => (contracts = toggle(contracts, value, on))}>{value}</Tick
									>
								{/each}
							</div>
						</fieldset>
						<fieldset>
							<legend class="mb-1 font-bold">Télétravail accepté</legend>
							<div class="flex flex-wrap gap-x-5 gap-y-1">
								{#each REMOTES as value (value)}
									<Tick
										checked={remote.includes(value)}
										onchange={(on) => (remote = toggle(remote, value, on))}
										>{remoteLabels[value]}</Tick
									>
								{/each}
							</div>
						</fieldset>
						<label class="grid gap-1">
							<span class="font-bold">Lieux</span>
							<input
								bind:value={locations}
								placeholder="Lyon, Villeurbanne"
								class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
							/>
							<span class="text-sm text-ink-soft"
								>Séparés par des virgules. « Lyon » garde « Lyon 3e ».</span
							>
						</label>
						<label class="grid gap-1">
							<span class="font-bold">Salaire minimum</span>
							<input
								bind:value={salary}
								type="number"
								min="0"
								step="1000"
								inputmode="numeric"
								placeholder="55000"
								class="rounded-sm border-ink/40 bg-paper tabular-nums focus:border-ink focus:ring-ink"
							/>
							<span class="text-sm text-ink-soft"
								>En euros bruts annuels, comparé au haut de la fourchette.</span
							>
						</label>
						<label class="grid gap-1">
							<span class="font-bold">Mots-clés exclus</span>
							<input
								bind:value={keywords}
								placeholder="régie, ESN"
								class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
							/>
							<span class="text-sm text-ink-soft">Cherchés dans l’intitulé et l’annonce.</span>
						</label>
						<label class="grid gap-1">
							<span class="font-bold">Entreprises exclues</span>
							<input
								bind:value={companies}
								class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"
							/>
						</label>
					</div>
				</BristolCard>

				<BristolCard title="Pondérations" colour="yellow" tab={1}>
					<p class="mb-4 text-sm">
						Le modèle note chaque critère de 0 à 10. Le score global est leur moyenne pondérée,
						calculée par le code : à 0, un critère ne compte pas.
					</p>
					<div class="grid gap-4 sm:grid-cols-2">
						{#each WEIGHTS as [name, label, hint] (name)}
							<label class="grid gap-1">
								<span class="flex items-baseline justify-between gap-3">
									<span
										><span class="font-bold">{label}</span>
										<span class="text-sm text-ink-soft">{hint}</span></span
									>
									<span class="font-extrabold text-ink tabular-nums">× {weights[name]}</span>
								</span>
								<input
									type="range"
									min="0"
									max="5"
									step="0.5"
									bind:value={weights[name]}
									class="accent-ink"
								/>
							</label>
						{/each}
					</div>
				</BristolCard>

				<BristolCard title="Ce que vous cherchez" colour="green" tab={2}>
					<label class="grid gap-1">
						<span class="sr-only">Préférences</span>
						<textarea
							bind:value={preferences}
							rows="6"
							maxlength="4000"
							placeholder="Le poste, l’équipe, les pratiques qui comptent pour vous, ce que vous évitez…"
							class="rounded-sm border-ink/40 bg-paper focus:border-ink focus:ring-ink"></textarea>
						<span class="text-sm">
							Lu par le modèle pour noter les offres. Votre nom, votre e-mail et votre téléphone y
							sont remplacés par « [CANDIDAT] » avant l’envoi.
						</span>
					</label>
				</BristolCard>

				{#if failure}
					<p role="alert" class="bg-alert px-4 py-2 font-bold text-white">{failure}</p>
				{/if}
				<div class="flex flex-wrap items-center gap-4">
					<Button type="submit" disabled={!dirty || saving}>Enregistrer</Button>
					<p role="status" class="text-ink-soft">
						{#if saving}
							Enregistrement…
						{:else if dirty}
							Modifications non enregistrées.
						{:else if view?.updated_at}
							Enregistrés le {formatDateTime(view.updated_at)}.
						{:else}
							Jamais enregistrés : rien n’est filtré.
						{/if}
					</p>
				</div>
			</form>

			<aside aria-labelledby="preview-title" class="self-start xl:sticky xl:top-3">
				<h2 id="preview-title" class="text-2xl font-extrabold text-ink">
					Vos offres à travers ces filtres
				</h2>
				{#if !view || view.offers.length === 0}
					<p class="mt-2 text-ink-soft">
						Aucune offre reçue pour l’instant. Collez-en dans
						<a href={resolve('/offres')} class="font-bold text-ink">Offres</a>.
					</p>
				{:else}
					<p class="mt-1 mb-3 text-ink-soft">
						{passing.length} sur {view.offers.length} passent{dirty
							? ', avec les filtres enregistrés'
							: ''}.
					</p>
					{#if eliminated.length}
						<h3 class="mb-1 font-extrabold text-alert">Écartées</h3>
						<ul class="mb-4 grid gap-1.5">
							{#each eliminated as offer (offer.offer_id)}
								<li class="bg-paper px-3 py-2">
									<a
										href={resolve('/offres/[id]', { id: String(offer.offer_id) })}
										class="font-bold text-ink">{offer.title}</a
									>
									<span class="text-sm text-ink-soft">{offer.company_name}</span>
									<p class="text-sm">{offer.eliminated_by.join(' · ')}</p>
								</li>
							{/each}
						</ul>
					{/if}
					{#if passing.length}
						<h3 class="mb-1 font-extrabold text-ink">Retenues</h3>
						<ul class="grid gap-1.5">
							{#each passing as offer (offer.offer_id)}
								<li class="bg-paper px-3 py-2">
									<a
										href={resolve('/offres/[id]', { id: String(offer.offer_id) })}
										class="font-bold text-ink">{offer.title}</a
									>
									<span class="text-sm text-ink-soft">{offer.company_name}</span>
									{#if offer.unknown.length}
										<p class="text-sm text-ink-soft">Inconnu : {offer.unknown.join(', ')}</p>
									{/if}
								</li>
							{/each}
						</ul>
					{/if}
				{/if}
			</aside>
		</div>
	{/if}
</div>
