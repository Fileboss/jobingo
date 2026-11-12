<script lang="ts">
	import BristolCard from '#lib/ui/BristolCard.svelte';
	import Button from '#lib/ui/Button.svelte';
	import RuledArea from '#lib/ui/RuledArea.svelte';
	import TextField from '#lib/ui/TextField.svelte';
	import CvExperience from './CvExperience.svelte';
	import { experienceIndexOf } from './diagnostics.ts';
	import { emptyExperience, type CvEditor } from './editor.svelte.ts';
	import { sectionId } from './sections.ts';

	let { editor }: { editor: CvEditor } = $props();
	let fields = $derived(editor.fields);

	let flagged = $derived(
		new Set(editor.diagnostics.map((item) => experienceIndexOf(item, editor.diagnosticsText)))
	);
	let added = $state(false);

	function addExperience() {
		fields.experiences.unshift(emptyExperience());
		added = true;
	}

	function move(index: number, delta: number) {
		const [item] = fields.experiences.splice(index, 1);
		fields.experiences.splice(index + delta, 0, item);
	}

	const listField = (list: 'skills' | 'languages' | 'hobbies' | 'projects') => ({
		get: () => fields[list].join('\n'),
		set: (value: string) => (fields[list] = value.split('\n'))
	});
	const skills = listField('skills');
	const languages = listField('languages');
	const hobbies = listField('hobbies');
	const projects = listField('projects');
</script>

<div class="grid gap-6">
	{#if fields.before.trim()}
		<BristolCard title="Début du document" colour="grey" id="cv-avant">
			<p class="mb-2 text-sm">Ce texte n’appartient à aucune section. Il est conservé tel quel.</p>
			<RuledArea bind:value={fields.before} label="Texte avant les sections" />
		</BristolCard>
	{/if}

	<BristolCard title="Résumé" colour="yellow" tab={0} id={sectionId.resume}>
		<RuledArea
			bind:value={fields.resume}
			label="Résumé"
			placeholder="Quelques lignes sur votre parcours"
		/>
	</BristolCard>

	<BristolCard title="Expériences" colour="blue" tab={1} id={sectionId.experiences}>
		<Button variant="quiet" class="-ml-2" onclick={addExperience}>Ajouter une expérience</Button>
		<div class="divide-y-2 divide-ink/50">
			{#each fields.experiences as experience, index (index)}
				<CvExperience
					{experience}
					flagged={flagged.has(index)}
					first={index === 0}
					last={index === fields.experiences.length - 1}
					autofocus={added && index === 0}
					onmove={(delta) => move(index, delta)}
					onremove={() => fields.experiences.splice(index, 1)}
				/>
			{/each}
		</div>
	</BristolCard>

	<BristolCard title="Projets personnels" colour="yellow" tab={2} id={sectionId.projets}>
		<RuledArea
			bind:value={projects.get, projects.set}
			label="Projets personnels, un par ligne"
			placeholder="Un projet par ligne : son nom, ce qu’il fait, avec quoi"
			rows={3}
		/>
	</BristolCard>

	<BristolCard title="Formation" colour="green" tab={3} id={sectionId.formation}>
		<ul class="grid gap-1">
			{#each fields.formation as entry, index (index)}
				<li class="flex flex-wrap items-baseline gap-x-2">
					<TextField
						bind:value={entry.text}
						label="Formation, ligne {index + 1}"
						placeholder="Diplôme, établissement, année"
						class={['min-w-0 flex-1 basis-60', entry.heading && 'text-lg font-extrabold']}
					/>
					<Button
						variant="quiet"
						class="text-sm"
						aria-pressed={entry.heading}
						onclick={() => (entry.heading = !entry.heading)}>Intertitre</Button
					>
					<Button
						variant="quiet"
						class="text-sm"
						aria-label="Retirer la ligne {index + 1} de la formation"
						onclick={() => fields.formation.splice(index, 1)}>Retirer</Button
					>
				</li>
			{/each}
		</ul>
		<Button
			variant="quiet"
			class="mt-2 -ml-2"
			onclick={() => fields.formation.push({ text: '', heading: false })}>Ajouter une ligne</Button
		>
	</BristolCard>

	<BristolCard title="Compétences" colour="salmon" tab={4} id={sectionId.competences}>
		<RuledArea
			bind:value={skills.get, skills.set}
			label="Compétences, une par ligne"
			placeholder="Une compétence par ligne"
			rows={3}
		/>
	</BristolCard>

	<BristolCard
		title="Langues"
		colour="blue"
		tab={5}
		id={sectionId.langues}
		note="toujours sur la page"
	>
		<RuledArea
			bind:value={languages.get, languages.set}
			label="Langues, une par ligne"
			placeholder="Anglais : C1"
		/>
	</BristolCard>

	<BristolCard title="Loisirs" colour="lilac" tab={6} id={sectionId.loisirs}>
		<RuledArea
			bind:value={hobbies.get, hobbies.set}
			label="Loisirs, un par ligne"
			placeholder="Un loisir par ligne"
		/>
	</BristolCard>

	{#if fields.others.length}
		<BristolCard title="Autres contenus" colour="grey" id="cv-autres">
			<p class="mb-2 text-sm">
				Le formulaire ne sait pas découper ces blocs : conservés tels quels.
			</p>
			{#each fields.others.keys() as index (index)}
				<RuledArea
					bind:value={fields.others[index]}
					label="Bloc conservé {index + 1}"
					class="mb-3 font-mono text-sm"
				/>
			{/each}
		</BristolCard>
	{/if}
</div>
