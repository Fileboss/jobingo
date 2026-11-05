<script lang="ts">
	import type { HTMLButtonAttributes } from 'svelte/elements';

	type Props = HTMLButtonAttributes & {
		variant?: 'primary' | 'quiet' | 'inverse';
	};
	let { variant = 'primary', children, class: extra, ...rest }: Props = $props();

	const styles = {
		primary:
			'bg-ink px-5 py-1.5 text-white hover:bg-ink-deep disabled:bg-transparent disabled:text-ink-soft',
		quiet: 'px-2 py-1 text-ink underline underline-offset-4 hover:text-ink-deep',
		inverse: 'border border-white px-3 py-1 text-white hover:bg-white hover:text-ink'
	};
</script>

<button
	type="button"
	class={[
		'cursor-pointer rounded-sm font-extrabold disabled:cursor-default',
		styles[variant],
		extra
	]}
	{...rest}
>
	{@render children?.()}
</button>
