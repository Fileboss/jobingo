<script lang="ts">
	import { resolve } from '$app/paths';
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Tick from '#lib/ui/Tick.svelte';
	import type { CvPageEditor, OptionName } from './page.svelte.ts';

	let { editor }: { editor: CvPageEditor } = $props();

	const options: { name: OptionName; label: string; hint: string }[] = [
		{
			name: 'panneau_competences',
			label: 'Panneau latéral',
			hint: 'Compétences, coordonnées et photo à droite de la page 1.'
		},
		{ name: 'photo', label: 'Photo', hint: 'Votre photo sur le CV.' },
		{ name: 'loisirs', label: 'Loisirs', hint: 'La section Loisirs sur le CV.' }
	];
</script>

<BristolCard title="Mise en page" colour="grey">
	<div class="grid gap-3 sm:grid-cols-3">
		{#each options as option (option.name)}
			{@const blocker = editor.page?.option_blockers[option.name] ?? null}
			<div>
				<Tick
					checked={editor.options[option.name]}
					disabled={blocker !== null}
					onchange={(value) => editor.setOption(option.name, value)}
				>
					<span class={['font-extrabold', blocker && 'text-ink-soft']}>{option.label}</span>
				</Tick>
				<p class="mt-0.5 ml-7 text-sm leading-snug">
					{#if blocker}
						<span class="font-bold">{blocker}</span>
						{#if option.name === 'photo'}
							<a href={resolve('/identite')} class="whitespace-nowrap underline underline-offset-4">
								Aller à l’identité
							</a>
						{/if}
					{:else}
						{option.hint}
					{/if}
				</p>
			</div>
		{/each}
	</div>
</BristolCard>
