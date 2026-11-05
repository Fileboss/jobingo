<script lang="ts">
	let { data } = $props();
</script>

<svelte:head>
	<title>Jobingo</title>
</svelte:head>

<h1>Jobingo</h1>

{#if data.account}
	<p>Compte : {data.account.username}</p>
{:else}
	<p role="alert">Serveur indisponible</p>
{/if}
