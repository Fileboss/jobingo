# Lessons

Bugs the user reported and corrections of how Claude worked. Don't repeat them. Format and rules: `docs/records.md`.

- [A session shown as busy may have finished](2026-11-05-busy-does-not-mean-working.md): when following a background agent's progress, or deciding that it has finished
- [Check agent protocols for mutual waiting, in every start order](2026-11-05-check-protocols-for-mutual-waiting.md): when writing or changing a protocol where several agents wait on each other
- [Ship an example with each configuration file the user fills in](2026-11-07-ship-an-example-with-each-config-file.md): when adding a configuration file or setting the user has to fill in, such as a key file
- [Say why an external call failed, not only that it did](2026-11-10-say-why-a-model-call-failed.md): when handling a failed call to an external API, or writing the message a user sees when one fails
- [Ruled text stays on its rules, whatever its size](2026-11-10-ruled-text-stays-on-its-rules.md): when styling a ruled field (the `ruled` utility, `RuledArea`), or setting a text size or line height on one
- [An offer can name several cities: keep them all](2026-11-10-an-offer-can-name-several-cities.md): when extracting, storing, merging or filtering an offer's place, or adding a field that an offer can state more than once
- [Give an eval case to every way a loop can start](2026-11-12-eval-every-direction-of-a-loop.md): when writing or changing a feedback loop around a model, or the eval cases that measure it
- [The CV page has two areas: fit each with its own content](2026-11-12-the-page-has-two-areas.md): when measuring, fitting or filling the CV page, or reading page counts or missing items
- [A new rule on what goes on the page retires the caps that contradict it](2026-11-12-a-new-rule-retires-old-caps.md): when changing how much of the CV goes on the page, or settling a rule about what a CV must show, while older limits still apply
- [CI runs every server the tests reach, and a red CI is fixed](2026-11-13-ci-runs-what-the-tests-reach.md): when adding a server the tests reach or a CI check, or before reporting work as done while CI is red
