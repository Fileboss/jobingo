<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api/client.ts';
	import EventRow from '#lib/observability/EventRow.svelte';
	import { levelLabels, type AppEvent, type EventLevel } from '#lib/observability/format.ts';
	import Button from '#lib/ui/Button.svelte';

	const LEVELS: EventLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];
	const SEARCH_DELAY_MS = 300;

	let level = $derived((page.url.searchParams.get('level') ?? 'INFO') as EventLevel);
	let query = $derived(page.url.searchParams.get('q') ?? '');

	let events = $state.raw<AppEvent[]>([]);
	let next = $state<number | null>(null);
	let phase = $state<'loading' | 'ready' | 'unavailable'>('loading');
	let loadingMore = $state(false);

	async function fetchPage(before: number | null) {
		const { data } = await api.GET('/api/observability/events', {
			params: { query: { level, q: query || undefined, before_id: before ?? undefined } }
		});
		if (!data) throw new Error('no events');
		return data;
	}

	async function load() {
		try {
			const data = await fetchPage(null);
			events = data.events;
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
			events = [...events, ...data.events];
			next = data.next_before_id ?? null;
		} catch {
			phase = 'unavailable';
		} finally {
			loadingMore = false;
		}
	}

	$effect(() => {
		void level;
		void query;
		load();
	});

	/** The filters are a GET form: SvelteKit turns its submission into a navigation. */
	let form: HTMLFormElement | undefined = $state();
	// The box keeps what is typed: rebinding it to the URL would erase the letters typed
	// while the previous search was loading.
	let text = $state(page.url.searchParams.get('q') ?? '');
	let timer: ReturnType<typeof setTimeout> | undefined;
	function searchLater() {
		clearTimeout(timer);
		timer = setTimeout(() => form?.requestSubmit(), SEARCH_DELAY_MS);
	}
</script>

<svelte:head>
	<title>Journal | Suivi de l’IA | Jobingo</title>
</svelte:head>

<form
	bind:this={form}
	method="GET"
	action={resolve('/suivi/journal')}
	data-sveltekit-replacestate
	data-sveltekit-reset="false"
	class="mb-5 flex flex-wrap items-end gap-4"
>
	<label class="grid gap-1">
		<span class="text-sm font-bold text-ink-soft">Niveau minimum</span>
		<select
			name="level"
			value={level}
			onchange={() => form?.requestSubmit()}
			class="rounded-sm border-ink/40 py-1 pr-9 text-ink focus:border-ink focus:ring-ink"
		>
			{#each LEVELS as value (value)}<option {value}>{levelLabels[value]}</option>{/each}
		</select>
	</label>
	<label class="grid min-w-64 flex-1 gap-1 sm:max-w-md">
		<span class="text-sm font-bold text-ink-soft">Rechercher</span>
		<input
			type="search"
			name="q"
			bind:value={text}
			oninput={searchLater}
			placeholder="llm.call, une tâche, un motif…"
			class="rounded-sm border-ink/40 py-1 text-ink placeholder:text-ink-soft/70 focus:border-ink focus:ring-ink"
		/>
	</label>
</form>

{#if phase === 'loading'}
	<p class="text-ink-soft" role="status">Lecture du journal…</p>
{:else if phase === 'unavailable'}
	<div role="alert">
		<p class="text-xl font-extrabold text-ink">Le serveur ne répond pas.</p>
		<p class="mt-1 mb-4">Le journal n’a pas pu être lu. Vérifiez que l’API tourne, puis :</p>
		<Button onclick={load}>Réessayer</Button>
	</div>
{:else if events.length === 0}
	<div class="border border-dashed border-ink/30 px-5 py-8 text-center">
		<p class="text-xl font-extrabold text-ink">Aucun événement</p>
		<p class="mt-1 text-ink-soft">
			{query || level !== 'INFO'
				? 'Aucun événement ne correspond à ces filtres.'
				: 'Rien n’a encore été journalisé.'}
		</p>
	</div>
{:else}
	<ol class="divide-y divide-ink/10">
		{#each events as entry (entry.id)}<EventRow event={entry} />{/each}
	</ol>
	{#if next !== null}
		<div class="mt-4">
			<Button variant="quiet" disabled={loadingMore} onclick={more}
				>Afficher les plus anciens</Button
			>
		</div>
	{/if}
{/if}
