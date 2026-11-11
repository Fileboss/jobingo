import type { Page } from '@playwright/test';
import type { components } from '#lib/api/schema.d.ts';

type Identity = components['schemas']['IdentityDocument'];

const onePixelPng = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/AAAMBAQAY3Y2wAAAAAElFTkSuQmCC',
	'base64'
);

export const fictionalIdentity = {
	name: 'Alex Moreau',
	email: 'alex.moreau@example.fr',
	phone: '+33 6 00 00 00 00',
	address: '12 rue des Lilas, 44000 Nantes',
	linkedin: 'linkedin.com/in/alex-moreau',
	github: 'github.com/alex-moreau',
	website: 'alexmoreau.example'
};

/** The identity and photo API in memory, for Playwright. */
export class FakeIdentityApi {
	identity: Identity = {
		name: '',
		email: '',
		phone: '',
		address: '',
		linkedin: '',
		github: '',
		website: '',
		has_photo: false
	};

	async install(page: Page) {
		await page.route('**/api/identity', async (route) => {
			if (route.request().method() === 'PUT') {
				this.identity = { ...route.request().postDataJSON(), has_photo: this.identity.has_photo };
			}
			await route.fulfill({ json: this.identity });
		});
		await page.route('**/api/identity/photo*', async (route) => {
			const method = route.request().method();
			if (method === 'GET') {
				return route.fulfill({ contentType: 'image/png', body: onePixelPng });
			}
			if (method === 'DELETE') {
				this.identity = { ...this.identity, has_photo: false };
			} else {
				const { data_base64 } = route.request().postDataJSON();
				if (!Buffer.from(data_base64, 'base64').subarray(1, 4).equals(Buffer.from('PNG'))) {
					return route.fulfill({
						status: 400,
						json: { message: 'Ce fichier n’est pas une image JPEG ou PNG lisible.' }
					});
				}
				this.identity = { ...this.identity, has_photo: true };
			}
			await route.fulfill({ json: this.identity });
		});
	}
}

export const pngFile = { name: 'photo.png', mimeType: 'image/png', buffer: onePixelPng };
export const notAnImage = {
	name: 'photo.png',
	mimeType: 'image/png',
	buffer: Buffer.from('ceci n’est pas une image')
};
