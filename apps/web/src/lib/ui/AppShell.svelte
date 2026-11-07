<script lang="ts">
	import type { Snippet } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	let { children }: { children: Snippet } = $props();

	const screens = [
		{ href: resolve('/cv'), label: 'Mon CV' },
		{ href: resolve('/identite'), label: 'Identité' },
		{ href: resolve('/apercu'), label: 'Aperçu' },
		{ href: resolve('/offres'), label: 'Offres' },
		{ href: resolve('/objectifs'), label: 'Objectifs' },
		{ href: resolve('/adapter'), label: 'Adapter' },
		{ href: resolve('/candidatures'), label: 'Candidatures' },
		{ href: resolve('/suivi'), label: 'Suivi de l’IA' }
	];
	const upcoming = ['Courrier'];
</script>

<div class="flex min-h-dvh flex-col">
	<header class="flex flex-wrap items-baseline gap-x-8 gap-y-1 px-4 py-3.5 sm:px-6">
		<a href={resolve('/cv')} class="text-2xl font-extrabold text-ink no-underline">Jobingo</a>
		<nav aria-label="Navigation principale">
			<ul class="flex flex-wrap gap-x-5 gap-y-1">
				{#each screens as screen (screen.href)}
					<li>
						<a
							href={screen.href}
							aria-current={page.url.pathname === screen.href ||
							([
								resolve('/suivi'),
								resolve('/adapter'),
								resolve('/offres'),
								resolve('/candidatures')
							].includes(screen.href) &&
								page.url.pathname.startsWith(screen.href + '/'))
								? 'page'
								: undefined}
							class="font-bold text-ink underline-offset-4 aria-[current=page]:underline"
						>
							{screen.label}
						</a>
					</li>
				{/each}
				{#each upcoming as label (label)}
					<li class="text-ink-soft">
						{label}<span class="sr-only"> (bientôt disponible)</span>
					</li>
				{/each}
			</ul>
		</nav>
	</header>
	{@render children()}
</div>
