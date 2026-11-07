<script lang="ts">
	import { formatUsd, usd } from './format.ts';

	type Props = { label: string; spent: string; cap: string };
	let { label, spent, cap }: Props = $props();

	// Close to the cap is worth seeing before calls start being refused.
	const WARN_AT = 0.8;
	let share = $derived(usd(cap) > 0 ? usd(spent) / usd(cap) : 1);
	let state = $derived(share >= 1 ? 'reached' : share >= WARN_AT ? 'close' : 'fine');
</script>

<div>
	<div class="flex flex-wrap items-baseline justify-between gap-x-3">
		<span class="font-bold">{label}</span>
		<span class="tabular-nums"
			><span class="font-extrabold text-ink">{formatUsd(spent)}</span>
			<span class="text-ink-soft">sur {formatUsd(cap)}</span></span
		>
	</div>
	<div
		role="meter"
		aria-label={label}
		aria-valuemin={0}
		aria-valuemax={usd(cap)}
		aria-valuenow={usd(spent)}
		aria-valuetext="{formatUsd(spent)} sur {formatUsd(cap)}"
		class={[
			'mt-1.5 h-2.5 overflow-hidden rounded-full',
			state === 'fine' ? 'bg-ink/15' : 'bg-alert/15'
		]}
	>
		<div
			class={['h-full rounded-full', state === 'fine' ? 'bg-ink' : 'bg-alert']}
			style:width="{Math.min(share, 1) * 100}%"
		></div>
	</div>
	{#if state !== 'fine'}
		<p class="mt-1 flex items-center gap-1.5 text-sm font-bold text-alert">
			<svg viewBox="0 0 16 16" class="size-3.5" aria-hidden="true">
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
			</svg>
			{state === 'reached' ? 'Plafond atteint : les appels sont refusés.' : 'Proche du plafond.'}
		</p>
	{/if}
</div>
