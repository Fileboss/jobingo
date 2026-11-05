<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

	type Props = HTMLInputAttributes & {
		value: string;
		label: string;
		element?: HTMLInputElement;
	};
	let {
		value = $bindable(),
		label,
		element = $bindable(),
		class: extra,
		...rest
	}: Props = $props();
</script>

<input
	bind:this={element}
	bind:value
	aria-label={label}
	type="text"
	class={[
		'w-full border-0 border-b border-transparent bg-transparent p-0 font-medium text-ink placeholder:text-ink-soft hover:border-ink/40 focus:border-transparent focus:ring-0',
		extra
	]}
	{...rest}
/>
