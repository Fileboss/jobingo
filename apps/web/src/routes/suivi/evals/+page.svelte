<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api/client.ts';
	import {
		formatCount,
		formatDate,
		formatMs,
		formatScore,
		formatUsd,
		thinkingLabels,
		type EvalRun,
		type EvalTask
	} from '#lib/observability/format.ts';
	import Button from '#lib/ui/Button.svelte';

	let tasks = $state.raw<EvalTask[]>([]);
	let phase = $state<'loading' | 'ready' | 'unavailable'>('loading');

	async function load() {
		try {
			const { data } = await api.GET('/api/observability/evals');
			if (!data) throw new Error('no evals');
			tasks = data;
			phase = 'ready';
		} catch {
			phase = 'unavailable';
		}
	}

	onMount(load);

	function verdict(run: EvalRun): { label: string; failed: boolean } {
		if (run.passed === null || run.passed === undefined)
			return { label: 'Pas de seuil fixé', failed: false };
		return run.passed
			? { label: `Seuil atteint (${formatScore(run.threshold)})`, failed: false }
			: { label: `Sous le seuil (${formatScore(run.threshold)})`, failed: true };
	}

	const detailLabels: Record<string, string> = {
		cases: 'Cas réussis',
		accepted_rewrites: 'Reformulations acceptées',
		refused_rewrites: 'Reformulations refusées'
	};

	const isCurrent = (run: EvalRun, current: EvalRun | null | undefined) =>
		current != null &&
		run.run_at === current.run_at &&
		run.setup === current.setup &&
		run.prompt_version === current.prompt_version;

	/** What the grader found on a failed case, beyond its id and verdict. */
	function findings(row: Record<string, unknown>): [string, string][] {
		const labels: Record<string, string> = {
			missing: 'Manque',
			unwanted: 'En trop',
			refused_rewrites: 'Reformulations refusées',
			error: 'Erreur'
		};
		return Object.entries(labels)
			.map(([key, label]): [string, unknown] => [label, row[key]])
			.filter(([, value]) => (Array.isArray(value) ? value.length > 0 : Boolean(value)))
			.map(([label, value]) => [label, Array.isArray(value) ? value.join(', ') : String(value)]);
	}
</script>

<svelte:head>
	<title>Evals | Suivi de l’IA | Jobingo</title>
</svelte:head>

<p class="mb-6 max-w-3xl text-ink-soft">
	Chaque tâche est notée par du code sur des cas fictifs, avec la clé dédiée aux evals. Un prompt ou
	un modèle n’est adopté que si son score est au moins aussi bon. Cette page lit les résultats
	enregistrés : elle ne lance rien et ne dépense rien.
</p>

{#if phase === 'loading'}
	<p class="text-ink-soft" role="status">Lecture des résultats…</p>
{:else if phase === 'unavailable'}
	<div role="alert">
		<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
		<p class="mt-1 mb-4">Les résultats n’ont pas pu être lus. Vérifiez que l’API tourne, puis :</p>
		<Button onclick={load}>Réessayer</Button>
	</div>
{:else}
	<div class="grid gap-10">
		{#each tasks as task (task.task)}
			{@const current = task.current}
			<section aria-labelledby="eval-{task.task}" class="min-w-0">
				<h2 id="eval-{task.task}" class="flex flex-wrap items-baseline gap-x-3">
					<span class="font-mono text-2xl font-bold text-ink">{task.task}</span>
					<span class="text-ink-soft">prompt v{task.shipped_version} en service</span>
				</h2>

				{#if !current}
					<div class="mt-3 border border-dashed border-ink/30 px-5 py-8 text-center">
						<p class="text-xl font-extrabold text-ink">Pas encore mesuré</p>
						<p class="mx-auto mt-1 max-w-xl text-ink-soft">
							Aucun résultat pour le prompt v{task.shipped_version}. Les evals se lancent avec
							<code class="font-mono text-sm text-ink">make eval</code>, sur la clé des evals :
							aucun score n’est affiché tant qu’il n’a pas été mesuré.
						</p>
					</div>
				{:else}
					{@const result = verdict(current)}
					<div class="mt-3 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
						<div>
							<p class="text-6xl font-extrabold text-ink">{formatScore(current.score)}</p>
							<p class="mt-1 max-w-xl">{current.metric}</p>
							<p
								class={[
									'mt-2 flex items-center gap-1.5 font-bold',
									result.failed ? 'text-alert' : 'text-ink'
								]}
							>
								{#if result.failed}<span aria-hidden="true">▲</span>{/if}
								{result.label}
							</p>
							<dl class="mt-4 flex flex-wrap gap-x-8 gap-y-2 tabular-nums">
								{#each Object.entries(current.detail) as [key, value] (key)}
									<div>
										<dt class="text-sm font-bold text-ink-soft">{detailLabels[key] ?? key}</dt>
										<dd class="font-extrabold text-ink">{String(value)}</dd>
									</div>
								{/each}
							</dl>
						</div>
						<dl class="grid content-start gap-2 bg-bristol-green/60 px-4 py-4 text-sm">
							<div>
								<dt class="font-bold text-ink-soft">Modèle</dt>
								<dd class="font-mono text-ink">{current.model}</dd>
								<dd class="text-ink-soft">
									{thinkingLabels[current.thinking] ?? current.thinking}, effort {current.effort}
								</dd>
							</div>
							<div>
								<dt class="font-bold text-ink-soft">Coût du passage</dt>
								<dd class="font-extrabold text-ink">
									{formatUsd(current.spend.cost_usd)} pour {current.cases} cas
								</dd>
							</div>
							<div>
								<dt class="font-bold text-ink-soft">Latence p50 · p95</dt>
								<dd class="font-extrabold text-ink">
									{formatMs(current.spend.latency_p50_ms)} · {formatMs(
										current.spend.latency_p95_ms
									)}
								</dd>
							</div>
							<div>
								<dt class="font-bold text-ink-soft">Mesuré le</dt>
								<dd class="font-extrabold text-ink">{formatDate(current.run_at)}</dd>
								{#if current.regraded_from_cache}
									<dd class="text-ink-soft">notes recalculées depuis les réponses en cache</dd>
								{/if}
							</div>
						</dl>
					</div>

					{#if current.failing?.length}
						<details class="mt-6">
							<summary class="cursor-pointer font-bold text-ink">
								{current.failing.length}
								{current.failing.length === 1 ? 'cas échoué' : 'cas échoués'}
							</summary>
							<ul class="mt-2 divide-y divide-ink/10">
								{#each current.failing as row, index (index)}
									<li class="grid gap-1 py-2 sm:grid-cols-[6rem_minmax(0,1fr)]">
										<span class="font-mono text-sm font-bold text-ink">{String(row.id ?? '?')}</span
										>
										<dl class="grid gap-0.5 text-sm">
											{#each findings(row) as [label, value] (label)}
												<div class="flex flex-wrap gap-x-2">
													<dt class="font-bold text-ink-soft">{label}</dt>
													<dd class="font-mono break-all">{value}</dd>
												</div>
											{/each}
										</dl>
									</li>
								{/each}
							</ul>
						</details>
					{/if}
				{/if}

				{#if task.runs.length}
					<h3 class="mt-8 mb-2 font-extrabold text-ink">Passages enregistrés</h3>
					<div class="overflow-x-auto">
						<table class="w-full min-w-[44rem] text-left tabular-nums">
							<thead>
								<tr class="border-b-2 border-ink text-sm text-ink-soft">
									<th class="py-2 pr-4 font-bold">Date</th>
									<th class="py-2 pr-4 font-bold">Prompt</th>
									<th class="py-2 pr-4 font-bold">Réglage</th>
									<th class="py-2 pr-4 text-right font-bold">Score</th>
									<th class="py-2 pr-4 text-right font-bold">Coût</th>
									<th class="py-2 pr-4 text-right font-bold">p50</th>
									<th class="py-2 text-right font-bold">Sortie</th>
								</tr>
							</thead>
							<tbody>
								{#each task.runs as run (`${run.prompt_version}.${run.setup}.${run.run_at}`)}
									<tr
										class={[
											'border-b border-ink/10',
											isCurrent(run, current) && 'bg-bristol-green/30 font-bold'
										]}
									>
										<td class="py-2 pr-4 whitespace-nowrap">{formatDate(run.run_at)}</td>
										<td class="py-2 pr-4">v{run.prompt_version}</td>
										<td class="py-2 pr-4 font-mono text-sm">{run.setup}</td>
										<td class="py-2 pr-4 text-right">{formatScore(run.score)}</td>
										<td class="py-2 pr-4 text-right">{formatUsd(run.spend.cost_usd)}</td>
										<td class="py-2 pr-4 text-right">{formatMs(run.spend.latency_p50_ms)}</td>
										<td class="py-2 text-right">{formatCount(run.spend.output_tokens)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>
		{/each}
	</div>
{/if}
