<script lang="ts">
	import type { BristolColour } from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';

	let { onform, ontext }: { onform: () => void; ontext: () => void } = $props();

	const dividers = [
		{ label: 'Résumé', background: 'bg-bristol-yellow' },
		{ label: 'Expériences', background: 'bg-bristol-blue' },
		{ label: 'Formation', background: 'bg-bristol-green' },
		{ label: 'Compétences', background: 'bg-bristol-salmon' },
		{ label: 'Loisirs', background: 'bg-bristol-lilac' }
	] satisfies { label: string; background: `bg-bristol-${BristolColour}` }[];
</script>

<div>
	<div aria-hidden="true" class="hidden md:block">
		{#each dividers as divider, index (divider.label)}
			<div class={['-mb-1 h-16', index > 0 && '-mt-12']}>
				<div
					style:margin-left="{index * 7.25}rem"
					class={['w-fit rounded-t-md px-4 pt-0.5 text-lg font-extrabold', divider.background]}
				>
					{divider.label}
				</div>
				<div class={['h-9', divider.background]}></div>
			</div>
		{/each}
	</div>
	<div class="relative bg-paper px-5 py-10 sm:px-10">
		<h2 class="text-3xl font-extrabold text-ink">Un classeur neuf</h2>
		<p class="mt-3 max-w-xl text-xl leading-normal">
			Notez ici toute votre carrière, une seule fois, même ce que vous ne mettriez pas sur un CV
			d’une page. Pour chaque offre, Jobingo y choisira ce qui compte, sans rien inventer.
		</p>
		<div class="mt-6 flex flex-wrap items-center gap-3">
			<Button onclick={onform}>Remplir les fiches</Button>
			<Button variant="quiet" onclick={ontext}>Coller un texte</Button>
		</div>
	</div>
</div>
