# Lessons

Bugs the user reported and corrections of how Claude worked. Don't repeat them. Format and rules: `docs/records.md`.

- [A session shown as busy may have finished](2026-11-05-busy-does-not-mean-working.md): when following a background agent's progress, or deciding that it has finished
- [Check agent protocols for mutual waiting, in every start order](2026-11-05-check-protocols-for-mutual-waiting.md): when writing or changing a protocol where several agents wait on each other
- [Ship an example with each configuration file the user fills in](2026-11-07-ship-an-example-with-each-config-file.md): when adding a configuration file or setting the user has to fill in, such as a key file
- [Say why an external call failed, not only that it did](2026-11-10-say-why-a-model-call-failed.md): when handling a failed call to an external API, or writing the message a user sees when one fails
- [Ruled text stays on its rules, whatever its size](2026-11-10-ruled-text-stays-on-its-rules.md): when styling a ruled field (the `ruled` utility, `RuledArea`), or setting a text size or line height on one
- [An offer can name several cities: keep them all](2026-11-10-an-offer-can-name-several-cities.md): when extracting, storing, merging or filtering an offer's place, or adding a field that an offer can state more than once
