import { defineConfig } from '@playwright/test';

// Each worktree has its own port (scripts/worktree.sh).
const port = Number(process.env.PREVIEW_PORT ?? 4173);

export default defineConfig({
	webServer: { command: `pnpm run build && pnpm run preview --port ${port} --strictPort`, port },
	testMatch: '**/*.e2e.{ts,js}'
});
