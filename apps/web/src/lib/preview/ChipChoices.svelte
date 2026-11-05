<script lang="ts">
	import type { CvPage, CvPageEditor } from './page.svelte.ts';

	type Props = { editor: CvPageEditor; items: CvPage['competences']; label: string };
	let { editor, items, label }: Props = $props();
</script>

<ul aria-label={label} class="flex flex-wrap gap-1.5">
	{#each items as item (item.id)}
		{@const on = editor.isOn(item.id)}
		<li>
			<label
				class={[
					'relative block cursor-pointer rounded-sm border px-2.5 py-0.5 text-[0.9375rem] font-semibold focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink',
					on
						? 'border-ink bg-paper/80 text-ink'
						: 'border-dashed border-ink-soft font-medium text-ink-soft line-through'
				]}
			>
				<input
					type="checkbox"
					checked={on}
					onchange={(event) => editor.setItem(item.id, event.currentTarget.checked)}
					class="absolute inset-0 size-full cursor-pointer rounded-sm border-0 bg-transparent opacity-0"
				/>
				{item.text}
			</label>
		</li>
	{/each}
</ul>
