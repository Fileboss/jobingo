<script lang="ts">
	import { statusLabels, type CallStatus } from './format.ts';

	let { status }: { status: CallStatus } = $props();
</script>

<!-- Never colour alone: an icon and a word carry the state. -->
<span
	class={[
		'inline-flex items-center gap-1.5 font-bold whitespace-nowrap',
		status === 'ok' ? 'text-ink' : 'text-alert'
	]}
>
	<svg viewBox="0 0 16 16" class="size-3.5 shrink-0" aria-hidden="true">
		{#if status === 'ok'}
			<path
				d="M3 8.5l3.2 3L13 4.5"
				fill="none"
				stroke="currentColor"
				stroke-width="2.2"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
		{:else if status === 'failed'}
			<path
				d="M4 4l8 8M12 4l-8 8"
				fill="none"
				stroke="currentColor"
				stroke-width="2.2"
				stroke-linecap="round"
			/>
		{:else}
			<path
				d="M8 2.5l6 11H2z"
				fill="none"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linejoin="round"
			/>
			<path
				d="M8 6.5v3.2M8 11.6v.1"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
			/>
		{/if}
	</svg>
	{statusLabels[status]}
</span>
