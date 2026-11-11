<script lang="ts">
	import { resolve } from '$app/paths';
	import type { OfferScore } from './format.ts';

	type Props = { score: OfferScore };
	let { score }: Props = $props();

	const CRITERIA = [
		['mission', 'Mission'],
		['stack', 'Stack technique'],
		['culture', 'Culture']
	] as const;
</script>

{#if !score.passed_filters}
	<p class="font-extrabold text-alert">Écartée par vos filtres, sans appel au modèle.</p>
	<ul class="mt-1 list-disc pl-5">
		{#each score.eliminated_by as reason (reason)}<li>{reason}</li>{/each}
	</ul>
{:else if score.criteria}
	{@const criteria = score.criteria}
	<dl class="flex flex-wrap items-end gap-x-12 gap-y-3 tabular-nums">
		<div>
			<dt class="text-sm font-bold text-ink-soft">Adéquation</dt>
			<dd class="text-6xl leading-none font-extrabold text-ink">
				{score.fit_score}<span class="text-2xl text-ink-soft">/100</span>
			</dd>
		</div>
		<div>
			<dt class="text-sm font-bold text-ink-soft">Salaire</dt>
			<dd class="text-6xl leading-none font-extrabold text-ink">
				{#if score.salary_score === null}<span class="text-2xl text-ink-soft">non indiqué</span
					>{:else}{score.salary_score}<span class="text-2xl text-ink-soft">/100</span>{/if}
			</dd>
		</div>
	</dl>
	<p class="mt-3 max-w-2xl">{score.summary}</p>

	<dl class="mt-4 grid gap-2.5">
		{#each CRITERIA as [name, label] (name)}
			{@const value = criteria[name]}
			<div class="grid grid-cols-[8rem_minmax(0,1fr)_5rem] items-center gap-3 text-sm">
				<dt class="font-bold">{label}</dt>
				<dd class="h-2.5 overflow-hidden rounded-full bg-ink/15" aria-hidden="true">
					<div class="h-full rounded-full bg-ink" style:width="{value * 10}%"></div>
				</dd>
				<dd class="text-right tabular-nums">
					<span class="font-extrabold text-ink">{value}</span>/10
					<span class="text-ink-soft">× {score.weights[name]}</span>
				</dd>
			</div>
		{/each}
	</dl>
	<p class="mt-2 text-sm text-ink-soft">
		Le modèle note chaque critère ; l’adéquation est leur moyenne, pondérée par vos objectifs et
		calculée par le code. Le salaire est noté à part : une offre qui n’en indique pas n’est pas
		pénalisée.
	</p>

	<div class="mt-4 grid gap-4 sm:grid-cols-2">
		{#if score.strengths.length}
			<div>
				<h3 class="font-extrabold text-ink">Points forts</h3>
				<ul class="list-disc pl-5">
					{#each score.strengths as item (item)}<li>{item}</li>{/each}
				</ul>
			</div>
		{/if}
		{#if score.gaps.length}
			<div>
				<h3 class="font-extrabold text-ink">Écarts</h3>
				<ul class="list-disc pl-5">
					{#each score.gaps as item (item)}<li>{item}</li>{/each}
				</ul>
			</div>
		{/if}
	</div>
{/if}

{#if score.unknown.length}
	<p class="mt-3 text-sm">
		<span class="font-bold">Inconnu de l’offre :</span>
		{score.unknown.join(', ')}. Vos filtres n’ont pas pu le vérifier.
	</p>
{/if}
{#if score.llm_call_id}
	<p class="mt-2 text-sm">
		<a
			href={resolve('/suivi/appels/[id]', { id: String(score.llm_call_id) })}
			class="font-bold text-ink">Voir l’appel #{score.llm_call_id}</a
		>
	</p>
{/if}
