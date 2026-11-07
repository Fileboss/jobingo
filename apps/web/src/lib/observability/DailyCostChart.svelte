<script lang="ts">
	import { formatDay, formatLongDay, formatUsd, usd, type UsageReport } from './format.ts';

	type Props = { daily: UsageReport['daily'] };
	let { daily }: Props = $props();

	const HEIGHT = 200;
	const MARGIN = { top: 12, right: 8, bottom: 28, left: 64 };
	const MAX_BAR = 24;
	const RADIUS = 4;

	let width = $state(640);
	let active = $state<number | null>(null);

	let innerWidth = $derived(Math.max(width - MARGIN.left - MARGIN.right, 50));
	let innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
	let band = $derived(innerWidth / Math.max(daily.length, 1));
	// Capped and never filling the slot: the band's leftover is air, and touching bars
	// keep a 2px gap.
	let barWidth = $derived(Math.max(Math.min(MAX_BAR, band - 2), 1));

	/** Clean ticks: 1, 2 or 5 times a power of ten. */
	let ticks = $derived.by(() => {
		const peak = Math.max(...daily.map((d) => usd(d.cost_usd)), 0);
		if (peak === 0) return [0];
		const raw = peak / 3;
		const power = 10 ** Math.floor(Math.log10(raw));
		const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
		const count = Math.ceil(peak / step);
		return Array.from({ length: count + 1 }, (_, i) => i * step);
	});
	let top = $derived(ticks.at(-1) || 1);

	const y = (value: number) => MARGIN.top + innerHeight - (value / top) * innerHeight;
	const x = (index: number) => MARGIN.left + index * band + band / 2;

	/** A column with a rounded data end, square on the baseline. */
	function column(index: number, value: number): string {
		const h = innerHeight - (y(value) - MARGIN.top);
		const left = x(index) - barWidth / 2;
		const r = Math.min(RADIUS, barWidth / 2, h);
		const base = MARGIN.top + innerHeight;
		return `M${left},${base}V${base - h + r}Q${left},${base - h} ${left + r},${base - h}H${left + barWidth - r}Q${left + barWidth},${base - h} ${left + barWidth},${base - h + r}V${base}Z`;
	}

	// About six dates along the axis, the last day always among them.
	let labelled = $derived.by(() => {
		const every = Math.max(1, Math.ceil(daily.length / 6));
		const last = daily.length - 1;
		return new Set(daily.map((_, i) => i).filter((i) => (last - i) % every === 0));
	});

	let peakDay = $derived.by(() => {
		let best = -1;
		daily.forEach((d, i) => {
			if (usd(d.cost_usd) > 0 && (best < 0 || usd(d.cost_usd) > usd(daily[best].cost_usd)))
				best = i;
		});
		return best;
	});

	function onkeydown(event: KeyboardEvent) {
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
		event.preventDefault();
		const from = active ?? daily.length;
		const next = from + (event.key === 'ArrowLeft' ? -1 : 1);
		active = Math.min(Math.max(next, 0), daily.length - 1);
	}

	let shown = $derived(active === null ? null : daily[active]);
</script>

<div class="relative" bind:clientWidth={width}>
	<!-- Focusable so that the arrow keys read each day: the table below holds every value too. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
	<svg
		viewBox="0 0 {width} {HEIGHT}"
		class="block h-[200px] w-full overflow-visible outline-offset-4"
		role="img"
		aria-label="Coût par jour. Flèches gauche et droite pour lire chaque jour ; les valeurs sont aussi dans le tableau."
		tabindex="0"
		{onkeydown}
		onblur={() => (active = null)}
	>
		{#each ticks as tick (tick)}
			<line
				x1={MARGIN.left}
				x2={MARGIN.left + innerWidth}
				y1={y(tick)}
				y2={y(tick)}
				class="stroke-ink/15"
				stroke-width="1"
			/>
			<text
				x={MARGIN.left - 8}
				y={y(tick)}
				dy="0.32em"
				text-anchor="end"
				class="fill-ink-soft text-xs tabular-nums">{formatUsd(tick)}</text
			>
		{/each}

		{#each daily as entry, index (entry.day)}
			{@const value = usd(entry.cost_usd)}
			{#if value > 0}
				<path d={column(index, value)} class={active === index ? 'fill-ink-deep' : 'fill-ink'} />
			{/if}
			{#if labelled.has(index)}
				<text
					x={x(index)}
					y={MARGIN.top + innerHeight + 18}
					text-anchor="middle"
					class="fill-ink-soft text-xs">{formatDay(entry.day)}</text
				>
			{/if}
			<!-- The hit target is the whole day, not the painted pixels. -->
			<rect
				role="presentation"
				x={MARGIN.left + index * band}
				y={MARGIN.top}
				width={band}
				height={innerHeight}
				fill="transparent"
				onpointerenter={() => (active = index)}
				onpointerleave={() => (active = null)}
			/>
		{/each}

		{#if peakDay >= 0 && active === null}
			<text
				x={x(peakDay)}
				y={y(usd(daily[peakDay].cost_usd)) - 6}
				text-anchor="middle"
				class="fill-ink-deep text-xs font-bold tabular-nums"
				>{formatUsd(daily[peakDay].cost_usd)}</text
			>
		{/if}
		<line
			x1={MARGIN.left}
			x2={MARGIN.left + innerWidth}
			y1={MARGIN.top + innerHeight}
			y2={MARGIN.top + innerHeight}
			class="stroke-ink/40"
			stroke-width="1"
		/>
	</svg>

	{#if shown && active !== null}
		<div
			class="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full bg-ink-deep px-3 py-1.5 text-sm whitespace-nowrap text-white shadow-lg"
			style:left="{Math.min(Math.max(x(active), 90), width - 90)}px"
			style:top="{y(usd(shown.cost_usd)) - 8}px"
			aria-live="polite"
		>
			<p class="text-base font-extrabold tabular-nums">{formatUsd(shown.cost_usd)}</p>
			<p>
				{formatLongDay(shown.day)} · {shown.calls}
				{shown.calls === 1 ? 'appel' : 'appels'}
			</p>
		</div>
	{/if}
</div>
