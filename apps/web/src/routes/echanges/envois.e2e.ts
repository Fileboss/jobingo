import { expect, test } from '@playwright/test';
import { FakeMailApi } from './mail-api.fake.ts';
import { FakeActionsApi } from './actions-api.fake.ts';

test('a reply is prepared, previewed, then approved by a click', async ({ page }) => {
	const mail = new FakeMailApi();
	const actions = new FakeActionsApi();
	await mail.install(page);
	await actions.install(page);
	await page.goto('/echanges');
	await page.getByRole('button', { name: 'Synchroniser' }).click();
	await page.getByRole('link', { name: 'Votre candidature chez Voltéo' }).click();

	await page.getByRole('button', { name: 'Répondre' }).click();
	await expect(page.getByLabel('À', { exact: true })).toHaveValue('camille@volteo.test');
	await expect(page.getByLabel('Objet')).toHaveValue('Re: Votre candidature chez Voltéo');
	await page.getByLabel('Message', { exact: true }).fill('Merci pour votre retour.');
	await page.getByRole('button', { name: 'Préparer l’envoi' }).click();

	await expect(page).toHaveURL(/\/envois\/1$/);
	expect(actions.proposals[0].message_id).toBe(1);
	await expect(page.getByTestId('action-status')).toHaveText('À valider');
	await expect(page.getByText('Alex Moreau <alex@jobingo.test>')).toBeVisible();
	await expect(page.getByTestId('action-body')).toHaveText('Merci pour votre retour.');

	await page.getByRole('button', { name: 'Valider et envoyer' }).click();

	await expect(page.getByTestId('action-status')).toHaveText('Simulé');
	await expect(page.getByText('rien n’est parti')).toBeVisible();
	expect(actions.approvals).toEqual(['1'.padStart(64, 'c')]);
});

test('the model drafts a reply, the user fills its gap, the trail stays', async ({ page }) => {
	const mail = new FakeMailApi();
	const actions = new FakeActionsApi();
	await mail.install(page);
	await actions.install(page);
	await page.goto('/echanges');
	await page.getByRole('button', { name: 'Synchroniser' }).click();
	await page.getByRole('link', { name: 'Votre candidature chez Voltéo' }).click();
	await page.getByRole('button', { name: 'Répondre' }).click();

	await page.getByLabel('Intention').selectOption({ label: 'Demander des précisions' });
	await page.getByRole('button', { name: 'Rédiger avec l’IA' }).click();

	expect(actions.draftIntents).toEqual(['demander_precisions']);
	await expect(page.getByText('Note de l’IA')).toBeVisible();
	const body = page.getByLabel('Message', { exact: true });
	await expect(body).toHaveValue(/\[À COMPLÉTER : disponibilités\]/);
	await body.fill('Bonjour,\n\nJe suis disponible jeudi matin.\n\nCordialement,');
	await page.getByRole('button', { name: 'Préparer l’envoi' }).click();

	await expect(page).toHaveURL(/\/envois\/1$/);
	expect(actions.proposals[0].llm_call_id).toBe(42);
	await expect(page.getByText('Texte rédigé avec l’IA puis relu par vous')).toBeVisible();
});

test('a failed send says why and can be retried as it was', async ({ page }) => {
	const actions = new FakeActionsApi();
	actions.outcome = 'failed';
	actions.propose({ to: ['camille@volteo.test'], subject: 'Relance', body: 'Bonjour.' });
	await actions.install(page);
	await page.goto('/echanges/envois/1');

	await page.getByRole('button', { name: 'Valider et envoyer' }).click();

	await expect(page.getByText('L’envoi a échoué')).toBeVisible();
	await expect(page.getByText('n’a pas accepté le message')).toBeVisible();
	await page.getByRole('button', { name: 'Relancer, à l’identique' }).click();
	await expect(page.getByTestId('action-status')).toHaveText('Simulé');
});

test('what waits for a click comes first, among the messages received', async ({ page }) => {
	const mail = new FakeMailApi();
	const actions = new FakeActionsApi();
	actions.propose({ to: ['camille@volteo.test'], subject: 'Relance', body: 'Bonjour.' });
	actions.propose({ to: ['rh@plume.test'], subject: 'Candidature', body: 'Bonjour.' });
	actions.actions[0] = { ...actions.actions[0], status: 'rejected' };
	await mail.install(page);
	await actions.install(page);
	await page.goto('/echanges');
	await page.getByRole('button', { name: 'Synchroniser' }).click();

	await expect(page.getByRole('link', { name: 'Échanges' })).toHaveAttribute(
		'aria-current',
		'page'
	);
	const rows = page.getByRole('region', { name: 'Messages et envois' }).getByRole('listitem');
	await expect(rows.first()).toContainText('Candidature');
	await expect(rows.first()).toContainText('À valider');
	await expect(rows.filter({ hasText: 'Votre candidature chez Voltéo' })).toHaveCount(1);

	await page.getByRole('button', { name: /À valider/ }).click();
	await expect(rows).toHaveCount(1);
	await page.getByRole('button', { name: 'Envois' }).click();
	await expect(rows.filter({ hasText: 'Refusé' })).toHaveCount(1);
	await expect(rows).toHaveCount(2);
});

test('/echanges/envois fits a phone, with no horizontal scroll', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 800 });
	const actions = new FakeActionsApi();
	actions.propose({
		to: ['camille@volteo.test'],
		subject: 'Relance',
		body: 'Bonjour.',
		application_id: 7,
		attachments: [{ kind: 'cv' }]
	});
	await new FakeMailApi().install(page);
	await actions.install(page);
	for (const path of ['/echanges', '/echanges/envois/1']) {
		await page.goto(path);
		await expect(page.getByText('Relance').first()).toBeVisible();
		const width = await page.evaluate(() => document.documentElement.scrollWidth);
		expect(width).toBeLessThanOrEqual(390);
	}
});
