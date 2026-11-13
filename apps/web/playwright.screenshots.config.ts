import { defineConfig } from '@playwright/test';

// The README's screenshots, apart from the tests: `make screenshots`.
const port = Number(process.env.PREVIEW_PORT ?? 4173);

export default defineConfig({
	webServer: { command: `pnpm run build && pnpm run preview --port ${port} --strictPort`, port },
	testDir: 'screenshots',
	testMatch: '**/*.shots.ts',
	// Chrome, not Playwright's Chromium, which has no PDF viewer for the CV and the letter.
	use: { baseURL: `http://localhost:${port}`, channel: 'chrome' }
});
