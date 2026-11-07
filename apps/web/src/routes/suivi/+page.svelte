<script lang="ts">
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import BudgetMeter from '#lib/observability/BudgetMeter.svelte';
	import DailyCostChart from '#lib/observability/DailyCostChart.svelte';
	import {
		cacheHitRate,
		formatCount,
		formatDay,
		formatInteger,
		formatLongDay,
		formatMs,
		formatShare,
		formatUsd,
		tierLabels,
		usd,
		type UsageReport
	} from '#lib/observability/format.ts';
	import StatTile from '#lib/observability/StatTile.svelte';
	import Button from '#lib/ui/Button.svelte';

	const PERIODS = [7, 30, 90] as const;

	let days = $state<(typeof PERIODS)[number]>(30);
	let report = $state.raw<UsageReport | null>(null);
	let status = $state<'loading' | 'ready' | 'unavailable'>('loading');

	async function load(period: number) {
		try {
			const { data } = await api.GET('/api/observability/usage', {
				params: { query: { days: period } }
			});
			if (!data) throw new Error('no usage');
			report = data;
			status = 'ready';
		} catch {
			status = 'unavailable';
		}
	}

	$effect(() => {
		load(days);
	});

	let total = $derived(report?.total);
	let measured = $derived((total?.calls ?? 0) > 0);
	let failures = $derived(total ? total.failed + total.errors : 0);
</script>

<svelte:head>
	<title>Usage | Suivi de l’IA | Jobingo</title>
</svelte:head>

<div class="mb-6 flex flex-wrap items-center gap-3" role="group" aria-label="Période">
	{#each PERIODS as period (period)}
		<button
			type="button"
			aria-pressed={days === period}
			onclick={() => (days = period)}
			class="cursor-pointer rounded-sm border border-ink px-3 py-1 font-bold text-ink aria-pressed:bg-ink aria-pressed:text-white"
		>
			{period} jours
		</button>
	{/each}
	{#if report}
		<span class="text-ink-soft">depuis le {formatLongDay(report.since.slice(0, 10))}</span>
	{/if}
</div>

{#if status === 'loading' && !report}
	<p class="text-ink-soft" role="status">Lecture du journal…</p>
{:else if status === 'unavailable'}
	<div role="alert">
		<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
		<p class="mt-1 mb-4">Le journal n’a pas pu être lu. Vérifiez que l’API tourne, puis :</p>
		<Button onclick={() => load(days)}>Réessayer</Button>
	</div>
{:else if report && total}
	{#if !report.configured}
		<p class="mb-6 max-w-2xl bg-postit px-4 py-3 shadow-[0_6px_12px_-8px_var(--color-ink-deep)]">
			<span class="font-bold">Aucune clé API configurée.</span> Aucun appel ne peut partir tant que
			<code class="font-mono text-sm">ANTHROPIC_API_KEY</code> n’est pas renseignée.
		</p>
	{/if}

	<div class="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
		<section aria-labelledby="cost-title" class="min-w-0">
			<h2 id="cost-title" class="text-sm font-bold text-ink-soft">Coût sur {report.days} jours</h2>
			<p class="text-6xl font-extrabold text-ink">{formatUsd(total.cost_usd)}</p>
			<p class="mt-1 text-ink-soft">
				{formatInteger(total.calls)}
				{total.calls === 1 ? 'appel' : 'appels'}, échecs compris, car un appel échoué est facturé
				lui aussi.
			</p>

			{#if measured}
				<div class="mt-6">
					<DailyCostChart daily={report.daily} />
				</div>
				<details class="mt-2">
					<summary class="cursor-pointer text-sm font-bold text-ink"
						>Voir les valeurs par jour</summary
					>
					<table class="mt-2 w-full max-w-md text-sm tabular-nums">
						<thead>
							<tr class="text-left text-ink-soft">
								<th class="py-1 font-bold">Jour</th>
								<th class="py-1 text-right font-bold">Appels</th>
								<th class="py-1 text-right font-bold">Coût</th>
							</tr>
						</thead>
						<tbody>
							{#each report.daily.filter((d) => d.calls > 0) as entry (entry.day)}
								<tr class="border-t border-ink/10">
									<td class="py-1">{formatDay(entry.day)}</td>
									<td class="py-1 text-right">{entry.calls}</td>
									<td class="py-1 text-right">{formatUsd(entry.cost_usd)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</details>
			{:else}
				<div class="mt-6 border border-dashed border-ink/30 px-5 py-8 text-center">
					<p class="text-xl font-extrabold text-ink">Pas encore mesuré</p>
					<p class="mt-1 text-ink-soft">
						Aucun appel au modèle sur la période. Les chiffres apparaîtront avec le premier appel.
					</p>
				</div>
			{/if}
		</section>

		<aside class="grid content-start gap-5" aria-label="Plafonds et modèles">
			<section aria-labelledby="budget-title" class="grid gap-4 bg-bristol-blue/60 px-4 py-4">
				<h2 id="budget-title" class="font-extrabold text-ink">Plafonds de dépense</h2>
				<BudgetMeter
					label="Aujourd’hui"
					spent={report.budget.today_usd}
					cap={report.budget.daily_cap_usd}
				/>
				<BudgetMeter
					label="Ce mois-ci"
					spent={report.budget.month_usd}
					cap={report.budget.monthly_cap_usd}
				/>
			</section>
			<section aria-labelledby="models-title" class="bg-bristol-grey px-4 py-4">
				<h2 id="models-title" class="mb-2 font-extrabold text-ink">Modèles</h2>
				<dl class="grid gap-2">
					{#each report.models as model (model.tier)}
						<div>
							<dt class="text-sm font-bold text-ink-soft">{tierLabels[model.tier]}</dt>
							<dd class="font-mono text-sm text-ink">{model.model}</dd>
							<dd class="text-sm text-ink-soft">
								réflexion {model.thinking === 'off' ? 'désactivée' : 'adaptative'}, effort {model.effort}
							</dd>
						</div>
					{/each}
				</dl>
			</section>
		</aside>
	</div>

	{#if measured}
		<dl class="mt-8 grid grid-cols-2 gap-px bg-ink/10 sm:grid-cols-3 xl:grid-cols-6">
			<StatTile label="Coût par appel" value={formatUsd(usd(total.cost_usd) / total.calls)} />
			<StatTile
				label="Tokens"
				value={formatCount(total.input_tokens + total.cache_read_tokens + total.cache_write_tokens)}
				detail="{formatCount(total.output_tokens)} en sortie"
			/>
			<StatTile
				label="Lu depuis le cache"
				value={cacheHitRate(total)}
				detail="du prompt, à prix réduit"
			/>
			<StatTile
				label="Échecs"
				value={formatShare(failures, total.calls)}
				detail="{total.failed} invalides, {total.errors} API"
			/>
			<StatTile
				label="Relances"
				value={formatShare(total.retried, total.calls)}
				detail="deux requêtes facturées"
			/>
			<StatTile
				label="Latence p50 · p95"
				value={formatMs(total.latency_p50_ms)}
				detail={total.latency_p95_ms === null
					? 'aucun appel réussi'
					: `p95 ${formatMs(total.latency_p95_ms)}, appels réussis`}
			/>
		</dl>

		<section aria-labelledby="tasks-title" class="mt-10">
			<h2 id="tasks-title" class="mb-3 text-2xl font-extrabold text-ink">Par tâche</h2>
			<div class="overflow-x-auto">
				<table class="w-full min-w-[56rem] text-left tabular-nums">
					<thead>
						<tr class="border-b-2 border-ink text-sm text-ink-soft">
							<th class="py-2 pr-4 font-bold">Tâche</th>
							<th class="py-2 pr-4 text-right font-bold">Appels</th>
							<th class="py-2 pr-4 text-right font-bold">Échecs</th>
							<th class="py-2 pr-4 text-right font-bold">Relances</th>
							<th class="py-2 pr-4 text-right font-bold">Cache</th>
							<th class="py-2 pr-4 text-right font-bold">Sortie</th>
							<th class="py-2 pr-4 text-right font-bold">Latence p50</th>
							<th class="py-2 pr-4 text-right font-bold">p95</th>
							<th class="py-2 pr-4 text-right font-bold">Par appel</th>
							<th class="py-2 text-right font-bold">Coût</th>
						</tr>
					</thead>
					<tbody>
						{#each report.tasks as task (task.task)}
							<tr class="border-b border-ink/10">
								<td class="py-2 pr-4">
									<a
										href="{resolve('/suivi/appels')}?task={encodeURIComponent(task.task)}"
										class="font-mono text-sm font-bold text-ink">{task.task}</a
									>
								</td>
								<td class="py-2 pr-4 text-right">{formatInteger(task.calls)}</td>
								<td
									class={[
										'py-2 pr-4 text-right',
										task.failed + task.errors > 0 && 'font-bold text-alert'
									]}
								>
									{task.failed + task.errors}
								</td>
								<td class="py-2 pr-4 text-right">{task.retried}</td>
								<td class="py-2 pr-4 text-right">{cacheHitRate(task)}</td>
								<td class="py-2 pr-4 text-right">{formatCount(task.output_tokens)}</td>
								<td class="py-2 pr-4 text-right">{formatMs(task.latency_p50_ms)}</td>
								<td class="py-2 pr-4 text-right">{formatMs(task.latency_p95_ms)}</td>
								<td class="py-2 pr-4 text-right">{formatUsd(usd(task.cost_usd) / task.calls)}</td>
								<td class="py-2 text-right font-bold">{formatUsd(task.cost_usd)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}
{/if}
