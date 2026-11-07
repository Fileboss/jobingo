<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api/client.ts';
	import {
		formatCount,
		formatDateTime,
		formatMs,
		formatUsd,
		statusLabels,
		type CallStatus,
		type CallSummary
	} from '#lib/observability/format.ts';
	import StatusMark from '#lib/observability/StatusMark.svelte';
	import Button from '#lib/ui/Button.svelte';

	const STATUSES = Object.keys(statusLabels) as CallStatus[];

	let task = $derived(page.url.searchParams.get('task') ?? '');
	let status = $derived((page.url.searchParams.get('status') ?? '') as CallStatus | '');

	let calls = $state.raw<CallSummary[]>([]);
	let tasks = $state.raw<string[]>([]);
	let next = $state<number | null>(null);
	let phase = $state<'loading' | 'ready' | 'unavailable'>('loading');
	let loadingMore = $state(false);

	async function fetchPage(before: number | null) {
		const { data } = await api.GET('/api/observability/calls', {
			params: {
				query: {
					task: task || undefined,
					status: status || undefined,
					before_id: before ?? undefined
				}
			}
		});
		if (!data) throw new Error('no calls');
		return data;
	}

	async function load() {
		try {
			const data = await fetchPage(null);
			calls = data.calls;
			tasks = data.tasks;
			next = data.next_before_id ?? null;
			phase = 'ready';
		} catch {
			phase = 'unavailable';
		}
	}

	async function more() {
		if (next === null) return;
		loadingMore = true;
		try {
			const data = await fetchPage(next);
			calls = [...calls, ...data.calls];
			next = data.next_before_id ?? null;
		} catch {
			phase = 'unavailable';
		} finally {
			loadingMore = false;
		}
	}

	$effect(() => {
		void task;
		void status;
		load();
	});

	/** A filter is a GET form: SvelteKit turns its submission into a navigation. */
	const submit = (event: Event & { currentTarget: HTMLSelectElement }) =>
		event.currentTarget.form?.requestSubmit();

	const detailHref = (id: number) => resolve('/suivi/appels/[id]', { id: String(id) });
</script>

<svelte:head>
	<title>Appels | Suivi de l’IA | Jobingo</title>
</svelte:head>

<form
	method="GET"
	action={resolve('/suivi/appels')}
	data-sveltekit-replacestate
	data-sveltekit-reset="false"
	class="mb-5 flex flex-wrap items-end gap-4"
>
	<label class="grid gap-1">
		<span class="text-sm font-bold text-ink-soft">Tâche</span>
		<select
			name="task"
			value={task}
			onchange={submit}
			class="rounded-sm border-ink/40 py-1 pr-9 font-mono text-sm text-ink focus:border-ink focus:ring-ink"
		>
			<option value="">Toutes</option>
			{#each tasks as name (name)}<option value={name}>{name}</option>{/each}
			{#if task && !tasks.includes(task)}<option value={task}>{task}</option>{/if}
		</select>
	</label>
	<label class="grid gap-1">
		<span class="text-sm font-bold text-ink-soft">Statut</span>
		<select
			name="status"
			value={status}
			onchange={submit}
			class="rounded-sm border-ink/40 py-1 pr-9 text-ink focus:border-ink focus:ring-ink"
		>
			<option value="">Tous</option>
			{#each STATUSES as value (value)}<option {value}>{statusLabels[value]}</option>{/each}
		</select>
	</label>
</form>

{#if phase === 'loading'}
	<p class="text-ink-soft" role="status">Lecture du journal…</p>
{:else if phase === 'unavailable'}
	<div role="alert">
		<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
		<p class="mt-1 mb-4">Les appels n’ont pas pu être lus. Vérifiez que l’API tourne, puis :</p>
		<Button onclick={load}>Réessayer</Button>
	</div>
{:else if calls.length === 0}
	<div class="border border-dashed border-ink/30 px-5 py-8 text-center">
		<p class="text-xl font-extrabold text-ink">Aucun appel</p>
		<p class="mt-1 text-ink-soft">
			{task || status
				? 'Aucun appel ne correspond à ces filtres.'
				: 'Le modèle n’a encore jamais été appelé.'}
		</p>
	</div>
{:else}
	<div class="overflow-x-auto">
		<table class="w-full min-w-[56rem] text-left tabular-nums">
			<thead>
				<tr class="border-b-2 border-ink text-sm text-ink-soft">
					<th class="py-2 pr-4 font-bold">N°</th>
					<th class="py-2 pr-4 font-bold">Date</th>
					<th class="py-2 pr-4 font-bold">Tâche</th>
					<th class="py-2 pr-4 font-bold">Modèle</th>
					<th class="py-2 pr-4 font-bold">Statut</th>
					<th class="py-2 pr-4 text-right font-bold">Tokens</th>
					<th class="py-2 pr-4 text-right font-bold">Latence</th>
					<th class="py-2 text-right font-bold">Coût</th>
				</tr>
			</thead>
			<tbody>
				{#each calls as call (call.id)}
					<tr class="border-b border-ink/10 hover:bg-desk/50">
						<td class="py-2 pr-4">
							<a href={detailHref(call.id)} class="font-bold text-ink">#{call.id}</a>
						</td>
						<td class="py-2 pr-4 whitespace-nowrap">{formatDateTime(call.created_at)}</td>
						<td class="py-2 pr-4 font-mono text-sm">
							{call.task}<span class="ml-1.5 text-ink-soft">v{call.prompt_version}</span>
						</td>
						<td class="py-2 pr-4 font-mono text-sm text-ink-soft">{call.model}</td>
						<td class="py-2 pr-4">
							<StatusMark status={call.status} />
							{#if call.attempts > 1}<span class="ml-1 text-sm text-ink-soft">· 2 essais</span>{/if}
						</td>
						<td class="py-2 pr-4 text-right">
							{formatCount(call.input_tokens + call.cache_read_tokens + call.cache_write_tokens)}
							<span class="text-ink-soft">→ {formatCount(call.output_tokens)}</span>
						</td>
						<td class="py-2 pr-4 text-right">{formatMs(call.latency_ms)}</td>
						<td class="py-2 text-right font-bold">{formatUsd(call.cost_usd)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{#if next !== null}
		<div class="mt-4">
			<Button variant="quiet" disabled={loadingMore} onclick={more}
				>Afficher les plus anciens</Button
			>
		</div>
	{/if}
{/if}
