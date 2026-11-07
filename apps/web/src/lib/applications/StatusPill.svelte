<script lang="ts">
	import { statusLabels, toneClasses, type Status, type Tone } from './format.ts';

	let { status, tone }: { status: Status; tone: Tone } = $props();
</script>

<span
	class={[
		'inline-block rounded-sm px-2 py-0.5 text-sm font-extrabold whitespace-nowrap text-ink-deep',
		toneClasses[tone]
	]}>{statusLabels[status]}</span
>
