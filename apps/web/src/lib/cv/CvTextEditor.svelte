<script lang="ts">
	// Plain textarea until the CodeMirror packages are installed.
	type Props = { value: string; label: string };
	let { value = $bindable(), label }: Props = $props();

	let area = $state<HTMLTextAreaElement>();

	export function goToLine(line: number) {
		if (!area) return;
		const start =
			value
				.split('\n')
				.slice(0, line - 1)
				.join('\n').length + (line > 1 ? 1 : 0);
		area.focus();
		area.setSelectionRange(start, start);
	}
</script>

<textarea
	bind:this={area}
	bind:value
	aria-label={label}
	spellcheck="false"
	rows="24"
	class="field-sizing-content w-full resize-none rounded-sm border-0 bg-paper p-4 font-mono text-sm leading-relaxed text-ink focus:ring-0"
></textarea>
