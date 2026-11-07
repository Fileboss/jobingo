<script lang="ts">
	type Props = { label: string; value: string; detail?: string };
	let { label, value, detail }: Props = $props();
</script>

<div class="min-w-0 bg-paper px-4 py-3">
	<dt class="text-sm font-bold text-ink-soft">{label}</dt>
	<dd class="mt-0.5 text-3xl font-extrabold text-ink">{value}</dd>
	{#if detail}<dd class="mt-0.5 text-sm text-ink-soft">{detail}</dd>{/if}
</div>
