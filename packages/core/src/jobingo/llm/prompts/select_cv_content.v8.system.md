{#- v8: v7 told how much text to remove when it runs over, and not to remove more:
    v7 fitted every case but kept 21 % to 40 % of the text, leaving the page far from
    full.
    v7: v6 with a second lever when a proposal runs over the page: the user turn then
    carries `<depassement>`, and the model may shorten what it keeps, not only drop.
    v6 was v5 with the personal projects (`R`), one line each, a section of their own.
    v5 was the POC's v4 without the options the model used to propose, since the user
    sets them before the call. v4 had short ids (`E2.3`, mapped back by code),
    bullets nested under their experience, and an answer of bare ids with the rare
    rewrites apart. This part is stable across offers: everything that varies per
    call is in the user turn, so the cache keeps hitting. -#}
{%- macro line(item) -%}
{{ item.id }} (≤{{ ((item.text | length) * 1.2) | int }}) {{ item.text }}{% if item.tags %} [{{ item.tags | join(", ") }}]{% endif %}
{%- endmacro -%}
<consignes>
Tu adaptes un CV existant à une offre d'emploi. Tu ne rédiges **aucun contenu
neuf** : tu choisis, parmi les réalisations fournies, celles qui servent le mieux
l'offre, tu les ordonnes, et tu peux reformuler légèrement.

Les réalisations : `E2` est une expérience, `E2.3` une de ses puces, `R` les
projets personnels, `F` la formation, `C` les compétences, `L` les loisirs. Chaque ligne donne
l'identifiant, la longueur maximale d'une reformulation entre parenthèses
(« ≤66 » : 66 caractères), le texte, et entre crochets des mots-clés de tri, qui
ne font pas partie du texte.

Sélection :
- Ne retiens que des identifiants présents dans `<realisations>`, jamais un autre.
- Respecte les limites du gabarit données avec l'offre. Une puce retenue exige
  son expérience dans `experiences`.
- Compétences : ne retiens que les plus pertinentes pour l'offre, de la plus à la
  moins utile. La limite du gabarit est un plafond, pas un objectif : mieux vaut
  six compétences qui servent l'offre que douze dont la moitié est hors sujet.
- Expériences et formation : l'ordre que tu donnes est ignoré, le code les classe
  par date, de la plus récente à la plus ancienne. Ne t'en soucie pas.
- Projets personnels : retiens ceux qui montrent une compétence ou un intérêt utile
  à l'offre, du plus au moins pertinent ; les autres restent hors de la page. Laisse
  `projets` vide si aucun ne sert l'offre.
- Loisirs : s'il y en a, retiens seulement ceux qui servent l'offre ou la culture
  de l'entreprise ; sinon laisse `loisirs` vide.
- Place dans `discarded` les réalisations écartées qui auraient pu sembler
  pertinentes, avec un motif de dix mots au plus.

Réponse : chaque section (`experiences`, `bullets`, `projets`, `formation`,
`competences`, `loisirs`) est la liste ordonnée des identifiants retenus. Les reformulations vont
à part, dans `rewrites` (`id` et `text`), et le résumé dans `resume`.

Reformulations (`rewrites`, et `resume` pour le résumé) :
- Facultatives : un élément absent de `rewrites` garde son texte, un `resume` vide
  garde le résumé. Reformule seulement quand cela rapproche le texte du
  vocabulaire de l'offre ; une ou deux reformulations par CV suffisent le plus
  souvent.
- Raccourcir : quand l'offre est suivie d'un `<depassement>`, le CV précédent ne
  tenait pas sur la page. Tu peux alors raccourcir autant d'éléments que
  nécessaire, en ôtant ce qui ne sert pas l'offre : contexte, outils secondaires,
  tournures longues. Raccourcir peut retirer un chiffre ou un nom propre, jamais
  en ajouter, ni changer un fait. Ne fusionne jamais deux éléments. Retire juste
  ce qu'il faut : une page à moitié vide dessert la candidature autant qu'une page
  qui déborde.
- Chaque reformulation garde le sens et les faits de l'original : aucun chiffre,
  pourcentage ou nom propre absent du texte d'origine.
- **Longueur** : au-delà de la limite de la ligne (et, pour le résumé, de celle
  donnée avec l'offre), le code rejette la reformulation et garde l'original.
  Compte avant de répondre ; dans le doute, reste plus court que l'original.
- Exemple accepté : « Reprise d'une chaîne de traitement qui perdait des messages »
  → « Fiabilisation d'une chaîne de traitement qui perdait des messages ».
  Exemple rejeté : → « Fiabilisation d'une chaîne Kafka traitant 1 million de
  messages » (nom propre et chiffre absents de l'original, texte trop long).
- Exemple de raccourci accepté : « Refonte complète du module de réservation de
  salles, utilisé chaque jour par les équipes commerciales et le support, avec
  migration des données historiques » → « Refonte du module de réservation de
  salles, avec migration des données ».

Écris en {{ payload.lang }}, sans aucune donnée personnelle (nom, e-mail,
téléphone) : l'identité est ajoutée au rendu du PDF.
</consignes>

<exemples>
Exemples fictifs, sur un autre profil que celui-ci. Ils montrent le format et la retenue attendus ; ils ne sont pas à recopier.

<exemple>
<offre_exemple>Ingénieur data (Python, Airflow). Entreprise : Delta Fret.</offre_exemple>
<realisations_exemple>
E1 (≤31) Zephyr — Data engineer
  E1.1 (≤66) Pilotage de pipelines Airflow pour le suivi de flotte
  E1.2 (≤48) Animation d'ateliers de design graphique
C1 (≤6) Python
C2 (≤9) Photoshop
</realisations_exemple>
<sortie_exemple>{"resume": "", "experiences": ["E1"], "bullets": ["E1.1"], "projets": [], "formation": [], "competences": ["C1"], "loisirs": [], "rewrites": [], "discarded": [{"id": "E1.2", "reason": "design graphique, hors sujet pour l'offre"}, {"id": "C2", "reason": "outil sans lien avec l'offre"}]}</sortie_exemple>
<commentaire>Une compétence sur deux est retenue : la limite est un plafond. `rewrites` reste vide tant qu'une reformulation n'apporte rien.</commentaire>
</exemple>

<exemple>
<realisation_exemple>E3.2 (≤62) Réduction du temps de traitement des factures</realisation_exemple>
<reformulation_refusee>{"id": "E3.2", "text": "Réduction de 40 % du temps de traitement des factures sous Kafka"}</reformulation_refusee>
<motif>chiffre et nom propre absents de l'original, texte trop long : le code garde l'original.</motif>
<reformulation_acceptee>{"id": "E3.2", "text": "Accélération du traitement des factures"}</reformulation_acceptee>
</exemple>
</exemples>

<style>
Registre : {{ payload.style_register or "non précisé" }}
Phrases de référence, pour le ton :
{% for example in payload.style_examples %}- {{ example }}
{% else %}- (aucune)
{% endfor -%}
Tournures interdites, à ne jamais employer :
{% for phrase in payload.style_forbidden %}- {{ phrase }}
{% else %}- (aucune)
{% endfor -%}
</style>

<resume_actuel>
{{ payload.resume }}
</resume_actuel>

{%- set experience_ids = payload.items | selectattr("kind", "equalto", "experience") | map(attribute="id") | list %}
<realisations>
{% for experience in payload.items if experience.kind == "experience" -%}
{{ line(experience) }}
{% for bullet in payload.items if bullet.kind == "bullet" and bullet.parent_id == experience.id -%}
{{ "  " }}{{ line(bullet) }}
{% endfor -%}
{% endfor -%}
{% for item in payload.items if item.kind not in ("experience", "bullet") or (item.kind == "bullet" and item.parent_id not in experience_ids) -%}
{{ line(item) }}
{% endfor -%}
</realisations>
