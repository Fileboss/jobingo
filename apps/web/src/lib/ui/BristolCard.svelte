<script lang="ts">
	import type { Snippet } from 'svelte';

	export type BristolColour = 'yellow' | 'blue' | 'green' | 'salmon' | 'lilac' | 'grey';

	type Props = {
		title: string;
		colour: BristolColour;
		/** Rank of the tab along the top edge, like the staggered dividers of a binder. */
		tab?: number;
		id?: string;
		/** A few words written on the tab, after the title. */
		note?: string;
		children: Snippet;
	};
	let { title, colour, tab = 0, id, note, children }: Props = $props();

	const backgrounds: Record<BristolColour, string> = {
		yellow: 'bg-bristol-yellow',
		blue: 'bg-bristol-blue',
		green: 'bg-bristol-green',
		salmon: 'bg-bristol-salmon',
		lilac: 'bg-bristol-lilac',
		grey: 'bg-bristol-grey'
	};
</script>

<section {id} class="scroll-mt-6" aria-labelledby={id ? `${id}-title` : undefined}>
	<h2
		id={id ? `${id}-title` : undefined}
		style:--tab={tab}
		class={[
			'w-fit rounded-t-md px-4 pt-0.5 text-lg font-extrabold md:ml-[calc(var(--tab)*7.25rem)]',
			backgrounds[colour]
		]}
	>
		{title}
		{#if note}<span class="ml-1 text-base font-medium">{note}</span>{/if}
	</h2>
	<div class={['rounded-tr-sm rounded-b-sm px-4 py-5 sm:px-7', backgrounds[colour]]}>
		{@render children()}
	</div>
</section>
