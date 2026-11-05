import type { components } from '#lib/api/schema.d.ts';

export type CvDiagnostic = components['schemas']['CvDiagnostic'];

/**
 * The experience a diagnostic belongs to in the form, as an index in `fields.experiences`.
 * `line_no` is 1-based and refers to `text`, the view the server returned with it; 0 means no line.
 */
export function experienceIndexOf(diagnostic: CvDiagnostic, text: string): number | null {
	if (diagnostic.line_no < 1) return null;
	let index = -1;
	let inExperiences = false;
	for (const line of text.split('\n').slice(0, diagnostic.line_no)) {
		if (/^##\s/.test(line)) {
			inExperiences = /^##\s+Exp[ée]riences?\s*$/i.test(line);
		} else if (inExperiences && /^###\s/.test(line)) {
			index += 1;
		}
	}
	return inExperiences && index >= 0 ? index : null;
}
