import { expect, test, type Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type LetterView = components['schemas']['LetterView'];

const pdf = `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj
trailer<</Root 1 0 R>>
%%EOF`;

const slot = (
	name: string,
	max: number,
	text: string,
	extra: Partial<LetterView['slots'][number]> = {}
) => ({
	name,
	max_words: max,
	text,
	words: text.split(/\s+/).filter(Boolean).length,
	proposed: text,
	rejected_reason: '',
	unsourced_names: [],
	...extra
});

function letter(): LetterView {
	return {
		id: 3,
		application_id: 5,
		llm_call_id: 30,
		created_at: '2026-11-07T09:00:00Z',
		updated_at: '2026-11-07T09:00:00Z',
		application_title: 'Data engineer',
		company_name: 'Plume Énergie',
		recipient: 'Plume Énergie',
		slots: [
			slot('accroche', 60, 'Votre poste de data engineer m’intéresse.'),
			slot('adequation', 140, 'J’ai migré 120 tâches vers Airflow, comme chez Stratus.', {
				unsourced_names: ['Stratus']
			}),
			slot('motivation', 100, '', {
				proposed: 'Votre plateforme sert 400 collectivités.',
				rejected_reason: 'chiffre absent des sources : 400'
			})
		],
		cited_ids: [],
		warnings: [],
		problems: ['« motivation » est vide'],
		max_pages: 1
	};
}

async function open(page: Page) {
	let current = letter();
	const sent: { texts: Record<string, string>; recipient: string }[] = [];
	await page.route('**/api/letters/3', (route) => route.fulfill({ json: current }));
	await page.route('**/api/letters/3/texts', (route) => {
		const body = route.request().postDataJSON();
		sent.push(body);
		current = {
			...current,
			recipient: body.recipient,
			slots: current.slots.map((s) => ({ ...s, text: body.texts[s.name] ?? '' })),
			problems: Object.values(body.texts).every((t) => String(t).trim()) ? [] : current.problems
		};
		return route.fulfill({ json: current });
	});
	await page.route('**/api/letters/3/pdf', (route) =>
		route.fulfill({
			contentType: 'application/pdf',
			headers: { 'X-Page-Count': '1', 'Content-Disposition': 'inline; filename="lettre.pdf"' },
			body: pdf
		})
	);
	await page.goto('/lettres/3');
	return sent;
}

test('a refused slot is empty until the user decides, and blocks the download', async ({
	page
}) => {
	const sent = await open(page);
	await expect(page.getByText('Proposition refusée')).toBeVisible();
	await expect(page.getByText('À vérifier : Stratus')).toBeVisible();
	await expect(page.getByText('À régler avant de télécharger')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Télécharger le PDF' })).toHaveCount(0);

	await page.getByRole('button', { name: 'Utiliser quand même' }).click();

	await expect
		.poll(() => sent.at(-1)?.texts.motivation)
		.toBe('Votre plateforme sert 400 collectivités.');
	await expect(page.getByRole('link', { name: 'Télécharger le PDF' })).toBeVisible();
});

test('the word count follows what is typed', async ({ page }) => {
	await open(page);
	const accroche = page.getByLabel('Accroche', { exact: true });
	await accroche.fill(Array.from({ length: 61 }, () => 'mot').join(' '));
	await expect(page.getByText('61 mots sur 60')).toBeVisible();
});

test('the screen fits a phone, with no horizontal scroll', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 800 });
	await open(page);
	await expect(page.getByText('Lettre de motivation')).toBeVisible();
	const width = await page.evaluate(() => document.documentElement.scrollWidth);
	expect(width).toBeLessThanOrEqual(390);
});
