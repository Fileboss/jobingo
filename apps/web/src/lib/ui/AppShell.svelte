<script lang="ts">
	import type { Snippet } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	let { children }: { children: Snippet } = $props();

	const upcoming = ['Offres', 'Candidatures', 'Courrier', 'Suivi de l’IA'];
</script>

<div class="flex min-h-dvh flex-col">
	<header class="flex flex-wrap items-baseline gap-x-8 gap-y-1 px-4 py-3.5 sm:px-6">
		<a href={resolve('/cv')} class="text-2xl font-extrabold text-ink no-underline">Jobingo</a>
		<nav aria-label="Navigation principale">
			<ul class="flex flex-wrap gap-x-5 gap-y-1">
				<li>
					<a
						href={resolve('/cv')}
						aria-current={page.url.pathname === resolve('/cv') ? 'page' : undefined}
						class="font-bold text-ink underline-offset-4 aria-[current=page]:underline"
					>
						Mon CV
					</a>
				</li>
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
