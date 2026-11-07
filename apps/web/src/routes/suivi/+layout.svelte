<script lang="ts">
	import type { Snippet } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	let { children }: { children: Snippet } = $props();

	const tabs = [
		{
			href: resolve('/suivi'),
			label: 'Usage',
			match: (path: string) => path === resolve('/suivi')
		},
		{
			href: resolve('/suivi/appels'),
			label: 'Appels',
			match: (path: string) => path.startsWith(resolve('/suivi/appels'))
		},
		{
			href: resolve('/suivi/journal'),
			label: 'Journal',
			match: (path: string) => path.startsWith(resolve('/suivi/journal'))
		}
	];
</script>

<div class="mx-auto w-full max-w-[96rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<h1 class="text-5xl leading-tight font-extrabold text-ink">Suivi de l’IA</h1>
	<p class="mt-1 mb-6 max-w-3xl text-lg text-ink-soft">
		Ce que le modèle a fait, ce que cela a coûté, et la trace de chaque appel. Tout est mesuré sur
		les appels réels, rien n’est estimé.
	</p>

	<nav aria-label="Sections du suivi">
		<ul class="flex gap-1">
			{#each tabs as tab (tab.href)}
				{@const current = tab.match(page.url.pathname)}
				<li>
					<a
						href={tab.href}
						aria-current={current ? 'page' : undefined}
						class={[
							'block rounded-t-md px-5 pt-1 pb-1.5 text-lg font-extrabold no-underline',
							current ? 'bg-paper text-ink' : 'bg-bristol-grey/70 text-ink-soft hover:text-ink'
						]}
					>
						{tab.label}
					</a>
				</li>
			{/each}
		</ul>
	</nav>
	<div class="rounded-tr-sm rounded-b-sm bg-paper px-4 py-6 sm:px-7">
		{@render children()}
	</div>
</div>
