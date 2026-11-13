<script lang="ts">
	import type { Filter } from './table.ts';

	type Props = {
		/** What the search box looks in, said in its placeholder. */
		searchIn: string;
		query: string;
		onsearch: (query: string) => void;
		filters: Filter[];
		active: Record<string, string>;
		onfilter: (name: string, value: string | null) => void;
		onreset: () => void;
		shown: number;
		total: number;
		/** The noun counted, singular and plural. */
		noun: [string, string];
	};
	let { searchIn, query, onsearch, filters, active, onfilter, onreset, shown, total, noun }: Props =
		$props();

	let tags = $derived(filters.filter((filter) => filter.name in active));
	const field = 'rounded-sm border-ink/40 bg-paper py-1 text-sm focus:border-ink focus:ring-ink';
</script>

<div class="mb-3 grid gap-2">
	<div class="flex flex-wrap items-end gap-x-4 gap-y-2">
		<label class="grid min-w-56 flex-1 gap-1 sm:max-w-sm">
			<span class="text-sm font-bold">Rechercher</span>
			<input
				type="search"
				value={query}
				oninput={(event) => onsearch(event.currentTarget.value)}
				placeholder={searchIn}
				class={field}
			/>
		</label>
		{#each filters as filter (filter.name)}
			{@const choices = Object.entries(filter.choices)}
			{#if choices.length === 1}
				<label class="flex items-center gap-2 pb-1 text-sm">
					<input
						type="checkbox"
						checked={filter.name in active}
						onchange={(event) =>
							onfilter(filter.name, event.currentTarget.checked ? choices[0][0] : null)}
						class="rounded-sm border-ink text-ink focus:ring-ink"
					/>
					{filter.label}
				</label>
			{:else}
				<label class="grid gap-1">
					<span class="text-sm font-bold">{filter.label}</span>
					<select
						value={active[filter.name] ?? ''}
						onchange={(event) => onfilter(filter.name, event.currentTarget.value || null)}
						class={field}
					>
						<option value="">Tous</option>
						{#each choices as [value, label] (value)}<option {value}>{label}</option>{/each}
					</select>
				</label>
			{/if}
		{/each}
	</div>
	<div class="flex flex-wrap items-center gap-2 text-sm">
		<p role="status" class="text-ink-soft">
			{shown === total
				? `${total} ${noun[total > 1 ? 1 : 0]}`
				: `${shown} ${noun[shown > 1 ? 1 : 0]} sur ${total}`}
		</p>
		{#each tags as filter (filter.name)}
			{@const choices = Object.keys(filter.choices)}
			<button
				type="button"
				onclick={() => onfilter(filter.name, null)}
				aria-label="Retirer le filtre : {filter.label}"
				class="inline-flex cursor-pointer items-center gap-1 rounded-sm bg-bristol-blue px-2 py-0.5 font-bold text-ink-deep hover:bg-bristol-salmon"
			>
				{choices.length === 1
					? filter.label
					: `${filter.label} : ${filter.choices[active[filter.name]]}`}<span aria-hidden="true"
					>×</span
				>
			</button>
		{/each}
		{#if tags.length || query}
			<button
				type="button"
				onclick={onreset}
				class="cursor-pointer font-bold text-ink underline underline-offset-4"
				>Tout réinitialiser</button
			>
		{/if}
	</div>
</div>
