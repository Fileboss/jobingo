---
paths:
  - "apps/web/**"
---

# Client rules

- Set the visual direction before the first real screen, then keep to shared design tokens and components. Screens must look good in a demo and in screenshots.
- `openapi.json` and `src/lib/api/schema.d.ts` are generated: never edit them by hand. They come from `make api-types`.
- Keep a strict CSP. SvelteKit writes it into the HTML with the hashes of its inline scripts (`vite.config.ts`), because a `script-src` header would block them. No other inline script.
- The CV and letter preview is the real trial PDF, never an HTML approximation, because a browser ignores `@page`. It is fetched, then shown from a `blob:` URL in an `<iframe>` (`lib/preview/PdfSheet.svelte`), so a failed render leaves the last PDF on screen. `frame-src` allows `blob:` for this; `object-src 'none'` stays. The frame has no `sandbox`: Chrome refuses PDFs in sandboxed frames.
- Check your screens in a real browser with Claude in Chrome, not only with tests. Screenshots and page text go to the model, so only look at fictional data: `make pair` gives agents a fictional database, and a session outside a pair must ask before opening a page that shows the main database, which holds the user's real data.
- The Vite dev server proxies `/api` to the API. Use `make web`, which picks up a worktree's ports.
