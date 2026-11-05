<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ClassValue } from 'svelte/elements';

	type Props = {
		checked: boolean;
		disabled?: boolean;
		onchange: (checked: boolean) => void;
		class?: ClassValue;
		children: Snippet;
	};
	let { checked, disabled = false, onchange, class: extra, children }: Props = $props();
</script>

<label class={['flex gap-2.5', disabled ? 'cursor-default' : 'cursor-pointer', extra]}>
	<input
		type="checkbox"
		{checked}
		{disabled}
		onchange={(event) => onchange(event.currentTarget.checked)}
		class="mt-[0.2em] size-4.5 shrink-0 cursor-[inherit] rounded-sm border-ink text-ink not-checked:bg-paper/70 focus:ring-ink disabled:border-ink-soft disabled:not-checked:bg-transparent"
	/>
	<span class="min-w-0">{@render children()}</span>
</label>
