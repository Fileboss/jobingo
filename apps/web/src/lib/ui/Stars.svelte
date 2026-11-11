<script lang="ts">
	type Props = {
		/** 1 to 5, or null when not rated. */
		value: number | null;
		/** What is rated, for screen readers. */
		label: string;
		/** Without it, the stars are read-only. Clicking the current star clears it. */
		onchange?: (value: number | null) => void;
		disabled?: boolean;
		size?: 'sm' | 'lg';
	};
	let { value, label, onchange, disabled = false, size = 'lg' }: Props = $props();

	const STARS = [1, 2, 3, 4, 5];
	let hovered = $state<number | null>(null);
	let shown = $derived(hovered ?? value ?? 0);
</script>

{#if onchange}
	<div
		role="group"
		aria-label={label}
		class="inline-flex items-center"
		onpointerleave={() => (hovered = null)}
	>
		{#each STARS as star (star)}
			<button
				type="button"
				aria-pressed={value === star}
				aria-label="{star} étoile{star > 1 ? 's' : ''}"
				title={value === star ? 'Retirer la note' : `${star} sur 5`}
				{disabled}
				onpointerenter={() => (hovered = star)}
				onclick={() => onchange(value === star ? null : star)}
				class={[
					'cursor-pointer px-0.5 leading-none transition-colors disabled:cursor-default',
					size === 'lg' ? 'text-3xl' : 'text-lg',
					star <= shown ? 'text-ink' : 'text-ink/20'
				]}
			>
				★
			</button>
		{/each}
	</div>
{:else if value}
	<span
		class={['leading-none tracking-tight', size === 'lg' ? 'text-3xl' : 'text-base']}
		aria-label="{label} : {value} sur 5"
		title="{value} sur 5"
	>
		{#each STARS as star (star)}<span
				aria-hidden="true"
				class={star <= value ? 'text-ink' : 'text-ink/20'}>★</span
			>{/each}
	</span>
{/if}
