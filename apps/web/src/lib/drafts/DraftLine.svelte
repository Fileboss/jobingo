<script lang="ts">
	import Tick from '#lib/ui/Tick.svelte';
	import type { DraftEditor, DraftItem } from './draft.svelte.ts';

	type Props = { editor: DraftEditor; item: DraftItem; strong?: boolean };
	let { editor, item, strong = false }: Props = $props();

	let editing = $state(false);
	let typed = $state('');

	let on = $derived(editor.isKept(item.id));
	let text = $derived(editor.textOf(item));
	let changed = $derived(text !== item.original);
	let fromModel = $derived(changed && text === item.proposed_rewrite && !item.rejected_reason);

	function edit() {
		typed = text;
		editing = true;
	}

	function done() {
		editor.setText(item, typed);
		editing = false;
	}
</script>

<div class="grid gap-1">
	<div class="flex items-start gap-3">
		<Tick checked={on} onchange={(value) => editor.setKept(item.id, value)} class="min-w-0 flex-1">
			<span
				class={[strong ? 'font-extrabold' : 'leading-snug', !on && 'text-ink-soft line-through']}
				>{text}</span
			>
			{#if !item.proposed && on}
				<span class="ml-1.5 text-sm font-bold whitespace-nowrap text-ink-soft">ajouté par vous</span
				>
			{/if}
		</Tick>
		{#if !editing}
			<button
				type="button"
				onclick={edit}
				aria-label="Modifier : {text}"
				class="shrink-0 cursor-pointer text-sm text-ink underline underline-offset-4"
			>
				Modifier
			</button>
		{/if}
	</div>

	{#if editing}
		<div class="ml-7 grid gap-1.5">
			<textarea
				bind:value={typed}
				rows="2"
				aria-label="Texte de la ligne"
				class="w-full rounded-sm border-ink/40 bg-paper text-[0.9375rem] focus:border-ink focus:ring-ink"
			></textarea>
			<div class="flex flex-wrap gap-x-3 text-sm">
				<button
					type="button"
					onclick={done}
					class="cursor-pointer font-bold text-ink underline underline-offset-4"
				>
					Valider
				</button>
				<button
					type="button"
					onclick={() => (typed = item.original)}
					class="cursor-pointer text-ink underline underline-offset-4"
				>
					Revenir au texte du CV
				</button>
				<button
					type="button"
					onclick={() => (editing = false)}
					class="cursor-pointer text-ink-soft underline underline-offset-4"
				>
					Annuler
				</button>
			</div>
		</div>
	{/if}

	<div class="ml-7 grid gap-0.5 text-sm">
		{#if changed}
			<p class="text-ink-soft">
				<span class="font-bold"
					>{fromModel
						? 'Reformulé par le modèle.'
						: text === item.proposed_rewrite
							? 'Reformulation refusée par le code, adoptée par vous.'
							: 'Votre texte.'}</span
				>
				Dans le CV : <span class="line-through">{item.original}</span>
			</p>
		{/if}
		{#if item.rejected_reason && text !== item.proposed_rewrite}
			<p class="border-l-2 border-alert pl-2">
				<span class="font-bold text-alert">Reformulation refusée</span>
				<span class="text-ink-soft">({item.rejected_reason}) :</span>
				« {item.proposed_rewrite} »
				<button
					type="button"
					onclick={() => editor.setText(item, item.proposed_rewrite)}
					class="ml-1 cursor-pointer font-bold text-ink underline underline-offset-4"
				>
					Utiliser quand même
				</button>
			</p>
		{/if}
		{#if item.unsourced_names.length && fromModel}
			<p class="font-bold text-alert">À vérifier : {item.unsourced_names.join(', ')}</p>
		{/if}
		{#if !item.proposed && item.discard_reason}
			<p class="text-ink-soft">
				<span class="font-bold">Écarté par le modèle :</span>
				{item.discard_reason}
			</p>
		{/if}
	</div>
</div>
