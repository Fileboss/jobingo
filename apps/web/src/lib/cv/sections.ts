/** Anchors of the form's cards, by section of the CV. */
export const sectionId = {
	resume: 'cv-resume',
	experiences: 'cv-experiences',
	projets: 'cv-projets',
	formation: 'cv-formation',
	competences: 'cv-competences',
	loisirs: 'cv-loisirs'
} as const;

const bySectionName: Record<string, string> = {
	Résumé: sectionId.resume,
	Expériences: sectionId.experiences,
	'Projets personnels': sectionId.projets,
	Formation: sectionId.formation,
	Compétences: sectionId.competences,
	Loisirs: sectionId.loisirs
};

/** The card a diagnostic's `section` points to; other sections are in the kept blocks. */
export const cardOfSection = (section: string | null) =>
	section ? (bySectionName[section] ?? 'cv-autres') : null;
