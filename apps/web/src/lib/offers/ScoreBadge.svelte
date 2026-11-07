<script lang="ts">
	import type { ScoredOffer } from './format.ts';

	let { offer }: { offer: ScoredOffer } = $props();
	let score = $derived(offer.current_score);
</script>

{#if !score}
	<span class="text-sm text-ink-soft">non notée</span>
{:else if !score.passed_filters}
	<span class="text-sm font-bold text-alert">filtrée</span>
{:else}
	<span
		class={[
			'inline-flex min-w-11 justify-center rounded-sm px-1.5 py-0.5 text-lg font-extrabold tabular-nums',
			(score.score ?? 0) >= 70
				? 'bg-ink text-white'
				: (score.score ?? 0) >= 50
					? 'bg-bristol-blue text-ink'
					: 'bg-bristol-grey text-ink-soft'
		]}
		title={score.stale ? 'Note périmée : objectifs ou CV changés depuis' : undefined}
		>{score.score}{#if score.stale}<span aria-label=" (périmée)">*</span>{/if}</span
	>
{/if}
