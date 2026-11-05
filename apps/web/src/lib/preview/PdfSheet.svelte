<script lang="ts">
	import { onDestroy } from 'svelte';

	/** A new document loads hidden behind the current one, so the sheet never goes blank. */
	let { url, placeholder }: { url: string | null; placeholder: string } = $props();

	// The viewer's own toolbar duplicates the download next to the sheet.
	// The frame overhangs the sheet to crop the viewer's grey margin.
	const VIEW = '#toolbar=0&navpanes=0&view=FitH';
	const SWAP_FALLBACK_MS = 1500;

	let shown = $state<string | null>(null);
	let incoming = $state<string | null>(null);
	let timer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		if (!url || url === shown || url === incoming) return;
		if (incoming) URL.revokeObjectURL(incoming);
		incoming = url;
		// Chrome's PDF viewer may not report a load in every state.
		clearTimeout(timer);
		timer = setTimeout(swap, SWAP_FALLBACK_MS);
	});

	function swap() {
		clearTimeout(timer);
		if (!incoming) return;
		if (shown) URL.revokeObjectURL(shown);
		shown = incoming;
		incoming = null;
	}

	onDestroy(() => {
		clearTimeout(timer);
		if (shown) URL.revokeObjectURL(shown);
		if (incoming) URL.revokeObjectURL(incoming);
	});

	let frames = $derived([shown, incoming].filter((frame) => frame !== null));
</script>

<div
	class="relative aspect-[210/297] overflow-hidden bg-paper shadow-[0_18px_30px_-18px_var(--color-ink-deep)]"
>
	{#each frames as frame (frame)}
		<iframe
			src={frame + VIEW}
			title="Aperçu du CV"
			inert={frame !== shown}
			onload={() => {
				if (frame === incoming) swap();
			}}
			class={[
				'absolute -top-1 -left-2.5 h-[calc(100%+0.5625rem)] w-[calc(100%+1.25rem)] max-w-none border-0',
				frame !== shown && 'opacity-0'
			]}
		></iframe>
	{/each}
	{#if !frames.length}
		<p class="absolute inset-0 grid place-items-center px-8 text-center text-ink-soft">
			{placeholder}
		</p>
	{/if}
</div>
