---
date: 2026-11-10
status: active
applies_when: styling a ruled field (the `ruled` utility, `RuledArea`), or setting a text size or line height on one
---

# Ruled text stays on its rules, whatever its size

## What happened

On « Mon CV », the « Autres contenus » block sat off its rules: its text drifted across the lines. That block adds `font-mono text-sm` to the ruled field, and Tailwind's `text-sm` also sets `line-height`, which won over the `ruled` utility's 2rem. The rules stayed 2rem apart, the text did not.

In the same review the user found the rules on the bristol cards far too heavy, and the experience column misaligned: an invisible « Monter » left a hole, « Retirer » wrapped to a second line, and the dates had no separator. Claude first read « le souligné » as the buttons' underline and lightened that instead.

## What to do instead

- The `ruled` utility sets `--tw-leading` as well as `line-height`, so a `text-*` size beside it cannot change the line height. Never give a ruled field a line height of its own.
- The rules of ruled paper are very light: ink at 8 %. They guide the eye, they do not draw a grid.
- When the user's word could name two things on the screen, such as « souligné » for a rule or a link's underline, ask which one, or fix the one their screenshot shows.
- A control that does not apply is not rendered, rather than left invisible, so a row of controls starts at its edge.
- Look at a screen in the browser with real-looking, long content before calling it done: these three showed only with a long CV.

## Prevention

A Playwright test in `cv.e2e.ts` checks that every ruled field, a monospace kept block included, computes a 32px line height. It fails without the fix. The rules' lightness and the alignment rely on this entry.
