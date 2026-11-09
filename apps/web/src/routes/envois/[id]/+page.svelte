<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { statusColours, statusLabel, type ActionView } from '#lib/actions/format.ts';
	import { api } from '#lib/api/client.ts';
	import { formatDateTime } from '#lib/observability/format.ts';
	import Button from '#lib/ui/Button.svelte';

	let id = $derived(Number(page.params.id));
	let action = $state.raw<ActionView | null>(null);
	let phase = $state<'loading' | 'ready' | 'missing' | 'unavailable'>('loading');
	let busy = $state(false);
	let failure = $state<string | null>(null);

	async function load() {
		try {
			const { data, response } = await api.GET('/api/actions/{action_id}', {
				params: { path: { action_id: id } }
			});
			if (response.status === 404) {
				phase = 'missing';
				return;
			}
			if (!data) throw new Error('no action');
			action = data;
			phase = 'ready';
		} catch {
			phase = 'unavailable';
		}
	}

	onMount(load);

	const path = () => ({ params: { path: { action_id: id } } });

	async function decide(
		call: () => Promise<{ data?: ActionView; error?: { message: string } | unknown }>
	) {
		busy = true;
		failure = null;
		try {
			const { data, error } = await call();
			if (data) action = data;
			else if (error && typeof error === 'object' && 'message' in error)
				failure = String(error.message);
			else failure = 'Échec : rechargez la page.';
		} catch {
			failure = 'Le serveur ne répond pas. Réessayez.';
		} finally {
			busy = false;
		}
	}

	const approve = () =>
		decide(() =>
			api.POST('/api/actions/{action_id}/approve', {
				...path(),
				body: { payload_hash: action?.payload_hash ?? '' }
			})
		);
	const reject = () => decide(() => api.POST('/api/actions/{action_id}/reject', path()));
	const retry = () => decide(() => api.POST('/api/actions/{action_id}/retry', path()));

	/** The archived bytes, saved as they are: never a fresh render. */
	async function save(path: string, filename: string) {
		failure = null;
		try {
			const response = await fetch(path);
			if (!response.ok) throw new Error(String(response.status));
			const url = URL.createObjectURL(await response.blob());
			const link = document.createElement('a');
			link.href = url;
			link.download = filename;
			link.click();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		} catch {
			failure = 'Le fichier n’a pas pu être téléchargé.';
		}
	}

	let from = $derived(
		action
			? action.payload.from_name
				? `${action.payload.from_name} <${action.payload.from_addr}>`
				: action.payload.from_addr
			: ''
	);
</script>

<svelte:head>
	<title>{action?.subject ?? 'Envoi'} | Jobingo</title>
</svelte:head>

<div class="mx-auto w-full max-w-[72rem] flex-1 px-3 pt-2 pb-12 sm:px-6">
	<a href={resolve('/envois')} class="font-bold text-ink">← Envois</a>

	{#if phase === 'loading'}
		<p class="mt-4 text-ink-soft" role="status">Chargement…</p>
	{:else if phase === 'missing'}
		<p class="mt-4 font-extrabold text-ink">Cet envoi n’existe pas.</p>
	{:else if phase === 'unavailable'}
		<div class="mt-4" role="alert">
			<p class="font-extrabold text-ink">Le serveur ne répond pas.</p>
			<Button onclick={load}>Réessayer</Button>
		</div>
	{:else if action}
		<div class="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
			<h1 class="text-4xl leading-tight font-extrabold break-words text-ink">{action.subject}</h1>
			<span class={['px-2 font-bold', statusColours[action.status]]} data-testid="action-status"
				>{statusLabel(action)}</span
			>
		</div>
		{#if action.llm_call_id}
			<p class="mt-1 text-sm">
				Texte rédigé avec l’IA puis relu par vous ·
				<a
					href={resolve('/suivi/appels/[id]', { id: String(action.llm_call_id) })}
					class="font-bold text-ink">voir l’appel au modèle</a
				>
			</p>
		{/if}
		{#if action.application_id && action.application_title}
			<a
				href={resolve('/candidatures/[id]', { id: String(action.application_id) })}
				class="mt-1 inline-block font-bold text-ink">{action.application_title}</a
			>
		{/if}

		{#if action.status === 'proposed'}
			<section class="mt-5 bg-postit px-4 py-4 sm:px-6" aria-labelledby="decide-title">
				<h2 id="decide-title" class="text-xl font-extrabold text-ink">
					Ce message part tel qu’il est ci-dessous
				</h2>
				<p class="mt-1">
					Valider envoie exactement ce contenu, d’empreinte
					<code class="text-sm break-all">{action.payload_hash.slice(0, 16)}…</code>. Pour le
					modifier, refusez-le et préparez-en un autre.
				</p>
				<div class="mt-3 flex flex-wrap gap-3">
					<Button onclick={approve} disabled={busy}>{busy ? 'Envoi…' : 'Valider et envoyer'}</Button
					>
					<Button variant="quiet" onclick={reject} disabled={busy}>Refuser</Button>
				</div>
			</section>
		{:else if action.status === 'failed'}
			<section class="mt-5 bg-bristol-salmon px-4 py-4 sm:px-6" aria-labelledby="failed-title">
				<h2 id="failed-title" class="text-xl font-extrabold text-ink">L’envoi a échoué</h2>
				<p class="mt-1">{action.error}</p>
				<div class="mt-3 flex flex-wrap gap-3">
					<Button onclick={retry} disabled={busy}>Relancer, à l’identique</Button>
					<Button variant="quiet" onclick={reject} disabled={busy}>Abandonner</Button>
				</div>
			</section>
		{:else if action.status === 'sent'}
			<p class="mt-5 bg-bristol-green px-4 py-3">
				{action.dry_run
					? 'Simulation : le message a été construit mais rien n’est parti (SMTP_DRY_RUN=1).'
					: `Envoyé le ${formatDateTime(action.sent_at ?? action.created_at)}.`}
				<button
					type="button"
					onclick={() => save(`/api/actions/${action?.id}/eml`, `envoi-${action?.id}.eml`)}
					class="cursor-pointer font-bold underline underline-offset-4"
				>
					Télécharger le message exact (.eml)
				</button>
				>
			</p>
		{:else if action.status === 'rejected'}
			<p class="mt-5 bg-bristol-grey px-4 py-3">Refusé : rien n’est parti. Il reste au dossier.</p>
		{/if}

		{#if failure}
			<p role="alert" class="mt-4 bg-alert px-4 py-2 font-bold text-white">{failure}</p>
		{/if}

		<section aria-labelledby="preview-title" class="mt-6 bg-paper">
			<h2 id="preview-title" class="sr-only">Aperçu du message</h2>
			<dl
				class="grid gap-x-6 gap-y-1 border-b border-ink/10 px-4 py-4 text-sm sm:grid-cols-[auto_minmax(0,1fr)] sm:px-7"
			>
				<dt class="font-bold text-ink-soft">De</dt>
				<dd class="break-all">{from}</dd>
				<dt class="font-bold text-ink-soft">À</dt>
				<dd class="break-all">{action.payload.to.join(', ')}</dd>
				{#if action.payload.cc.length}
					<dt class="font-bold text-ink-soft">Copie</dt>
					<dd class="break-all">{action.payload.cc.join(', ')}</dd>
				{/if}
				<dt class="font-bold text-ink-soft">Objet</dt>
				<dd class="font-bold break-words">{action.payload.subject}</dd>
				{#if action.payload.in_reply_to}
					<dt class="font-bold text-ink-soft">En réponse</dt>
					<dd>
						{#if action.message_id}<a
								href={resolve('/courrier/[id]', { id: String(action.message_id) })}
								class="font-bold text-ink">au message reçu</a
							>{:else}à un message reçu{/if}
					</dd>
				{/if}
			</dl>
			<p
				class="px-4 py-4 leading-7 break-words whitespace-pre-wrap text-ink-deep sm:px-7"
				data-testid="action-body"
			>
				{action.payload.body_text}
			</p>
			{#if action.payload.attachments.length}
				<ul class="grid gap-1 border-t border-ink/10 px-4 py-3 sm:px-7">
					{#each action.payload.attachments as attachment (attachment.document_id)}
						<li class="text-sm">
							<button
								type="button"
								onclick={() =>
									save(`/api/documents/${attachment.document_id}/pdf`, attachment.filename)}
								class="cursor-pointer font-bold text-ink underline underline-offset-4"
							>
								{attachment.filename}
							</button>
							<span class="break-all text-ink-soft">
								· SHA-256 {attachment.sha256.slice(0, 12)}…
							</span>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/if}
</div>
