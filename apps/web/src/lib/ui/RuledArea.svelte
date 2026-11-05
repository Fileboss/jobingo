<script lang="ts">
	import type { HTMLTextareaAttributes } from 'svelte/elements';

	type Props = HTMLTextareaAttributes & { value: string; label: string };
	let { value = $bindable(), label, rows = 2, class: extra, ...rest }: Props = $props();
</script>

<textarea
	bind:value
	aria-label={label}
	{rows}
	class={[
		'field-sizing-content w-full resize-none border-0 bg-transparent ruled p-0 font-medium text-ink placeholder:text-ink-soft focus:ring-0',
		extra
	]}
	{...rest}></textarea>
