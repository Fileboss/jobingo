<script lang="ts">
	import Tick from '#lib/ui/Tick.svelte';
	import type { CvPage, CvPageEditor } from './page.svelte.ts';

	type Props = {
		editor: CvPageEditor;
		experience: CvPage['experiences'][number];
		open: boolean;
	};
	let { editor, experience, open }: Props = $props();

	let unfolded = $derived(open);
	let on = $derived(editor.isOn(experience.id));
	let kept = $derived(experience.bullets.filter((bullet) => editor.isOn(bullet.id)).length);
</script>

<article class="py-1.5">
	<div class="flex flex-wrap items-baseline justify-end gap-x-4">
		<Tick
			checked={on}
			onchange={(value) => editor.setItem(experience.id, value)}
			class="min-w-0 flex-1 basis-64"
		>
			<span class={['font-extrabold', !on && 'text-ink-soft line-through']}>{experience.text}</span>
		</Tick>
		{#if experience.bullets.length}
			<button
				type="button"
				aria-expanded={unfolded}
				aria-label="{unfolded ? 'Replier' : 'Déplier'} {experience.text}, {kept} sur {experience
					.bullets.length}"
				onclick={() => (unfolded = !unfolded)}
				class="cursor-pointer text-sm text-ink underline underline-offset-4"
			>
				{kept} ligne{kept > 1 ? 's' : ''} sur {experience.bullets.length}
			</button>
		{/if}
		{#if experience.dates}
			<span class={['text-sm tabular-nums', !on && 'text-ink-soft']}>{experience.dates}</span>
		{/if}
	</div>

	{#if unfolded && experience.bullets.length}
		<ul class="mt-1.5 mb-1 ml-7 grid gap-1">
			{#each experience.bullets as bullet (bullet.id)}
				{@const onPage = on && editor.isOn(bullet.id)}
				<li>
					<Tick
						checked={editor.isOn(bullet.id)}
						onchange={(value) => editor.setItem(bullet.id, value)}
					>
						<span
							class={[
								'text-[0.9375rem] leading-snug',
								!onPage && 'text-ink-soft',
								!editor.isOn(bullet.id) && 'line-through'
							]}>{bullet.text}</span
						>
					</Tick>
				</li>
			{/each}
		</ul>
	{/if}
</article>
