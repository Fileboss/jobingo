<script lang="ts">
	import type { CvDiagnostic } from './diagnostics.ts';

	type Props = {
		diagnostics: CvDiagnostic[];
		/** Where each note points, in the current mode. */
		place: (diagnostic: CvDiagnostic) => string | null;
		onselect: (diagnostic: CvDiagnostic) => void;
	};
	let { diagnostics, place, onselect }: Props = $props();
</script>

{#if diagnostics.length}
	<aside aria-label="Points à vérifier" class="grid content-start gap-3 xl:sticky xl:top-6">
		{#each diagnostics as diagnostic, index (index)}
			<button
				type="button"
				onclick={() => onselect(diagnostic)}
				class="cursor-pointer bg-postit px-4 py-3 text-left text-[0.9375rem] leading-snug shadow-[0_6px_12px_-8px_var(--color-ink-deep)] xl:odd:rotate-1 xl:even:-rotate-1"
			>
				{#if place(diagnostic)}
					<span class="block text-sm text-ink-soft">{place(diagnostic)}</span>
				{/if}
				<span class={['block font-bold', diagnostic.level === 'error' && 'text-alert']}>
					{diagnostic.message}
				</span>
				{#if diagnostic.suggestion}
					<span class="mt-1 block">{diagnostic.suggestion}</span>
				{/if}
			</button>
		{/each}
	</aside>
{/if}
