<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api/client.ts';
	import EventRow from '#lib/observability/EventRow.svelte';
	import {
		formatInteger,
		formatMs,
		formatTimestamp,
		formatUsd,
		type CallDetail
	} from '#lib/observability/format.ts';
	import StatusMark from '#lib/observability/StatusMark.svelte';
	import Button from '#lib/ui/Button.svelte';

	let id = $derived(Number(page.params.id));
	let call = $state.raw<CallDetail | null>(null);
	let phase = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');

	async function load(callId: number) {
		phase = 'loading';
		try {
			const { data, response } = await api.GET('/api/observability/calls/{call_id}', {
				params: { path: { call_id: callId } }
			});
			if (response.status === 404) {
				phase = 'missing';
				return;
			}
			if (!data) throw new Error('no call');
			call = data;
			phase = 'ready';
		} catch {
			phase = 'unavailable';
		}
	}

	$effect(() => {
		load(id);
	});

	const json = (value: unknown) => JSON.stringify(value, null, 2);
</script>

<svelte:head>
	<title>Appel #{id} | Suivi de l’IA | Jobingo</title>
</svelte:head>

<p class="mb-4">
	<a href={resolve('/suivi/appels')} class="font-bold text-ink">← Tous les appels</a>
</p>

{#snippet block(title: string, text: string | null, empty: string)}
	<section class="min-w-0">
		<h3 class="mb-1.5 font-extrabold text-ink">{title}</h3>
		{#if text}
			<pre
				class="max-h-[32rem] overflow-auto bg-desk/60 px-4 py-3 font-mono text-[0.8125rem] leading-relaxed whitespace-pre-wrap text-ink-deep">{text}</pre>
		{:else}
			<p class="text-ink-soft">{empty}</p>
		{/if}
	</section>
{/snippet}

{#if phase === 'loading'}
	<p class="text-ink-soft" role="status">Lecture de l’appel…</p>
{:else if phase === 'missing'}
	<p class="text-xl font-extrabold text-ink">Cet appel n’existe pas.</p>
{:else if phase === 'unavailable'}
	<div role="alert">
		<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
		<p class="mt-1 mb-4">L’appel n’a pas pu être lu. Vérifiez que l’API tourne, puis :</p>
		<Button onclick={() => load(id)}>Réessayer</Button>
	</div>
{:else if call}
	<header class="mb-6 flex flex-wrap items-baseline gap-x-5 gap-y-1">
		<h2 class="text-3xl font-extrabold text-ink">
			Appel #{call.id}
			<span class="ml-2 font-mono text-xl">{call.task}</span>
			<span class="font-mono text-xl text-ink-soft">v{call.prompt_version}</span>
		</h2>
		<StatusMark status={call.status} />
		<span class="text-ink-soft">{formatTimestamp(call.created_at)}</span>
	</header>

	<dl class="mb-8 grid grid-cols-2 gap-x-8 gap-y-3 tabular-nums sm:grid-cols-4 xl:grid-cols-7">
		{#each [['Modèle', call.model], ['Coût', formatUsd(call.cost_usd)], ['Latence', formatMs(call.latency_ms)], ['Requêtes', String(call.attempts)], ['Entrée', formatInteger(call.input_tokens)], ['Cache lu · écrit', `${formatInteger(call.cache_read_tokens)} · ${formatInteger(call.cache_write_tokens)}`], ['Sortie', formatInteger(call.output_tokens)]] as [label, value] (label)}
			<div>
				<dt class="text-sm font-bold text-ink-soft">{label}</dt>
				<dd class={['font-extrabold text-ink', label === 'Modèle' && 'font-mono text-sm']}>
					{value}
				</dd>
			</div>
		{/each}
	</dl>

	{#if call.error}
		<p class="mb-6 border-l-4 border-alert bg-bristol-salmon/40 px-4 py-2">
			<span class="font-bold text-alert">Erreur :</span>
			<span class="font-mono text-sm">{call.error}</span>
		</p>
	{/if}
	{#if call.purged_at}
		<p class="mb-6 bg-bristol-grey px-4 py-2">
			Prompts et réponse effacés le {formatTimestamp(call.purged_at)}, après 90 jours. Les comptes
			et le coût restent.
		</p>
	{/if}

	<div class="grid gap-6 xl:grid-cols-2">
		{@render block('Prompt système', call.system_prompt, 'Aucun, ou effacé.')}
		{@render block('Prompt utilisateur', call.user_prompt, 'Effacé.')}
		{@render block(
			'Réponse validée',
			call.answer === null || call.answer === undefined ? null : json(call.answer),
			call.status === 'ok' ? 'Effacée.' : 'Aucune réponse utilisable.'
		)}
		{@render block('Paramètres', call.parameters ? json(call.parameters) : null, 'Effacés.')}
	</div>

	<section class="mt-8" aria-labelledby="events-title">
		<h3 id="events-title" class="mb-2 text-xl font-extrabold text-ink">
			Ce que l’application en a fait
		</h3>
		{#if call.events.length}
			<ol class="divide-y divide-ink/10">
				{#each call.events as entry (entry.id)}<EventRow event={entry} linkCall={false} />{/each}
			</ol>
		{:else}
			<p class="text-ink-soft">Aucun événement journalisé pour cet appel.</p>
		{/if}
	</section>
{/if}
