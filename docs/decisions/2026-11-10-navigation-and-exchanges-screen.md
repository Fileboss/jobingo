---
date: 2026-11-10
status: active
applies_when: changing the main navigation, adding a screen, or working on the screens for mail received and sends through the approval queue
---

# No Aperçu screen; mail and sends share one « Échanges » screen

## Question

The navigation had nine screens. The user asked to remove « Aperçu », to put « Objectifs » before « Offres », and to merge « Courrier » and « Envois » into a single screen for the communication. Options for Aperçu: delete the screen, fold it into « Mon CV », or only hide it from the menu. Options for the merged screen: one list mixing what is received and what is sent, or two columns side by side.

## Decision

- The « Aperçu » screen is deleted. A CV PDF is made from an application, on the « Adapter » screen. The server routes `/api/cv/{lang}/selection` and `/api/cv/{lang}/pdf` stay for now, with no screen using them.
- The navigation order is: Mon CV, Identité, Objectifs, Offres, Candidatures, Échanges, Suivi de l’IA.
- « Échanges » (`/echanges`) is one list of messages received and sends, mixed by date, with what waits for a click first. Filters: Tout, À valider, À traiter, Reçus, Envois, Alertes, Masqués. The side column holds the mailbox and the send guarantees. A message is at `/echanges/recus/{id}`, a send at `/echanges/envois/{id}`.

## Why

Not stated.
