<script lang="ts">
	import type { Sort } from './table.ts';

	type Props = {
		column: string;
		label: string;
		sort: Sort;
		onsort: (column: string) => void;
		class?: string;
	};
	let { column, label, sort, onsort, class: extra = '' }: Props = $props();

	let active = $derived(sort?.column === column);
	let direction = $derived<'ascending' | 'descending' | 'none'>(
		active ? (sort?.descending ? 'descending' : 'ascending') : 'none'
	);
</script>

<th aria-sort={direction} class={['py-2 font-bold', extra]}>
	<button
		type="button"
		onclick={() => onsort(column)}
		title={active && sort?.descending ? 'Revenir à l’ordre par défaut' : `Trier par ${label}`}
		class={[
			'inline-flex cursor-pointer items-center gap-1 whitespace-nowrap hover:text-ink',
			active && 'text-ink'
		]}
	>
		{label}<span aria-hidden="true" class={['w-3 text-xs', !active && 'opacity-0']}
			>{sort?.descending ? '▼' : '▲'}</span
		>
	</button>
</th>
