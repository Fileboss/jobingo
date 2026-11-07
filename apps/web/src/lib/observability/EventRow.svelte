<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatTimestamp, levelLabels, type AppEvent } from './format.ts';

	type Props = { event: AppEvent; linkCall?: boolean };
	let { event, linkCall = true }: Props = $props();

	let serious = $derived(
		event.level === 'WARNING' || event.level === 'ERROR' || event.level === 'CRITICAL'
	);
	let fields = $derived(Object.entries(event.fields).filter(([key]) => key !== 'llm_call_id'));
	const show = (value: unknown) => (typeof value === 'string' ? value : JSON.stringify(value));
</script>

<li class="grid gap-x-4 gap-y-1 py-2 sm:grid-cols-[10rem_5.5rem_minmax(0,1fr)]">
	<span class="text-sm text-ink-soft tabular-nums">{formatTimestamp(event.created_at)}</span>
	<span class={['text-sm font-bold', serious ? 'text-alert' : 'text-ink-soft']}>
		{#if serious}<span aria-hidden="true">▲ </span>{/if}{levelLabels[event.level]}
	</span>
	<div class="min-w-0">
		<span class="font-mono text-sm font-bold text-ink">{event.name}</span>
		{#if linkCall && event.llm_call_id !== null}
			<a
				href={resolve('/suivi/appels/[id]', { id: String(event.llm_call_id) })}
				class="ml-2 text-sm font-bold text-ink">appel #{event.llm_call_id}</a
			>
		{/if}
		{#if fields.length}
			<dl class="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[0.8125rem] text-ink-deep">
				{#each fields as [key, value] (key)}
					<div class="flex min-w-0 gap-1">
						<dt class="text-ink-soft">{key}</dt>
						<dd class="break-all">{show(value)}</dd>
					</div>
				{/each}
			</dl>
		{/if}
	</div>
</li>
