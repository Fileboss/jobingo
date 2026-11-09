<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import Button from '#lib/ui/Button.svelte';
	import { splitAddresses, type EmailProposal } from './format.ts';

	type Props = {
		/** The application it concerns: attachments come from it. */
		applicationId?: number | null;
		/** The received message it answers. */
		messageId?: number | null;
		to?: string;
		subject?: string;
		letters?: { id: number; created_at: string }[];
		oncancel: () => void;
	};
	let {
		applicationId = null,
		messageId = null,
		to: initialTo = '',
		subject: initialSubject = '',
		letters = [],
		oncancel
	}: Props = $props();

	// Seeded once from the props: what the user then types is theirs.
	let to = $state((() => initialTo)());
	let cc = $state('');
	let subject = $state((() => initialSubject)());
	let body = $state('');
	let withCv = $state(false);
	let letterIds = $state<number[]>([]);
	let busy = $state(false);
	let failure = $state<string | null>(null);

	async function propose(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		failure = null;
		const proposal: EmailProposal = {
			application_id: applicationId,
			message_id: messageId,
			to: splitAddresses(to),
			cc: splitAddresses(cc),
			subject,
			body,
			attachments: [
				...(withCv ? [{ kind: 'cv' as const }] : []),
				...letterIds.map((id) => ({ kind: 'letter' as const, letter_id: id }))
			]
		};
		try {
			const { data, error } = await api.POST('/api/actions', { body: proposal });
			if (data) await goto(resolve('/envois/[id]', { id: String(data.id) }));
			else failure = error && 'message' in error ? error.message : 'La proposition a échoué.';
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			busy = false;
		}
	}
</script>

<form class="grid gap-3 bg-paper px-4 py-4 sm:px-6" onsubmit={propose}>
	<label class="grid gap-1">
		<span class="text-sm font-bold">À</span>
		<input
			bind:value={to}
			required
			autocomplete="off"
			class="rounded-sm border-ink/40 focus:border-ink focus:ring-ink"
		/>
	</label>
	<label class="grid gap-1">
		<span class="text-sm font-bold">Copie</span>
		<input
			bind:value={cc}
			placeholder="Facultatif"
			autocomplete="off"
			class="rounded-sm border-ink/40 focus:border-ink focus:ring-ink"
		/>
	</label>
	<label class="grid gap-1">
		<span class="text-sm font-bold">Objet</span>
		<input
			bind:value={subject}
			required
			maxlength="300"
			class="rounded-sm border-ink/40 focus:border-ink focus:ring-ink"
		/>
	</label>
	<label class="grid gap-1">
		<span class="text-sm font-bold">Message</span>
		<textarea
			bind:value={body}
			required
			rows="8"
			maxlength="20000"
			class="rounded-sm border-ink/40 leading-7 focus:border-ink focus:ring-ink"></textarea>
	</label>
	{#if applicationId !== null}
		<fieldset class="grid gap-1">
			<legend class="text-sm font-bold">Pièces jointes</legend>
			<label class="flex items-center gap-2">
				<input type="checkbox" bind:checked={withCv} class="rounded-sm text-ink" />
				CV, adapté à l’offre s’il l’a été
			</label>
			{#each letters as letter (letter.id)}
				<label class="flex items-center gap-2">
					<input
						type="checkbox"
						value={letter.id}
						bind:group={letterIds}
						class="rounded-sm text-ink"
					/>
					Lettre du {formatDateTime(letter.created_at)}
				</label>
			{/each}
			<p class="text-sm text-ink-soft">
				Les PDF sont produits et archivés maintenant : c’est ce fichier-là qui partira.
			</p>
		</fieldset>
	{/if}
	{#if failure}
		<p role="alert" class="bg-alert px-3 py-2 font-bold text-white">{failure}</p>
	{/if}
	<div class="flex flex-wrap items-center gap-3">
		<Button type="submit" disabled={busy}>{busy ? 'Préparation…' : 'Préparer l’envoi'}</Button>
		<Button variant="quiet" onclick={oncancel}>Annuler</Button>
		<span class="text-sm text-ink-soft"
			>Rien ne part avant votre validation, à l’écran suivant.</span
		>
	</div>
</form>
