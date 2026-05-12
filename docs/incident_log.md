# Journal d’incident technique — RubyBets

Ce document formalise un incident technique réel ou représentatif rencontré pendant la consolidation du MVP RubyBets.

Il sert de preuve RNCP pour la compétence C21 : résoudre un incident technique, documenter le diagnostic, appliquer une correction et valider le résultat.

---

## 1. Objectif du document

Le journal d’incident permet de prouver que RubyBets n’a pas seulement été développé, mais aussi corrigé, stabilisé et suivi comme un vrai projet applicatif.

Pour la soutenance, l’objectif est de montrer :

- un symptôme identifié ;
- une cause probable ;
- une correction appliquée ;
- un fichier impacté ;
- une validation technique ;
- une preuve localisable dans le dépôt ;
- un retour d’expérience.

---

## 2. Contexte du projet

RubyBets est une application web d’aide à la décision football avant-match.

Le MVP repose sur :

```
backend FastAPI
+ source Football-Data.org
+ cache JSON local
+ moteur de scoring explicable
+ frontend React TypeScript
```

Le parcours principal utilisateur consiste à :

```
sélectionner un match
→ consulter le détail
→ lire le contexte
→ lire l’analyse
→ consulter les prédictions
→ générer une recommandation multi-matchs
```

Ce parcours dépend donc de plusieurs appels API.

---

## 3. Incident documenté

| Élément | Description |
|---|---|
| Titre | Fragilité du chargement de la fiche match en cas d’échec API partiel |
| Type | Incident frontend / intégration API |
| Zone concernée | Fiche match RubyBets |
| Fichier principal impacté | `frontend/src/App.tsx` |
| Gravité MVP | Moyenne |
| Compétences RNCP | C20, C21 avec appui C10, C17 et C18 |

---

## 4. Symptôme observé

Lors du chargement d’un match, plusieurs blocs de la fiche match dépendaient d’appels API distincts :

- détail du match ;
- contexte ;
- analyse ;
- prédictions.

Le comportement initial était fragile : si un appel secondaire rencontrait une erreur ou renvoyait une donnée indisponible, cela pouvait dégrader trop fortement l’affichage global de la fiche match.

Le risque était que l’utilisateur ne puisse pas consulter correctement certains blocs, même si d’autres données étaient disponibles.

---

## 5. Cause probable

La cause principale venait d’une gestion trop globale du chargement asynchrone.

Lorsqu’une chaîne d’appels API est traitée comme un ensemble trop dépendant, un échec partiel peut avoir un impact disproportionné sur le reste du parcours.

Dans un produit comme RubyBets, ce comportement est problématique, car les données football peuvent être partiellement disponibles selon :

- la compétition ;
- le match ;
- la fraîcheur de la source ;
- le cache ;
- la disponibilité temporaire de l’API externe.

---

## 6. Correction appliquée

La correction a consisté à rendre le chargement des blocs plus indépendant.

Principe appliqué :

```
Un bloc indisponible ne doit pas bloquer toute la fiche match.
```

Le chargement a été renforcé avec une logique de type :

```
Promise.allSettled
```

Cette approche permet de traiter chaque réponse séparément :

- si le détail du match est disponible, il peut s’afficher ;
- si le contexte est indisponible, le reste peut continuer ;
- si l’analyse échoue, les prédictions peuvent rester exploitables ;
- si les prédictions sont indisponibles, l’interface peut afficher un message maîtrisé.

---

## 7. Fichier concerné

Le fichier principal concerné est :

```
frontend/src/App.tsx
```

Ce fichier orchestre le chargement des données principales lorsqu’un match est sélectionné.

---

## 8. Résultat après correction

Après correction, le parcours match devient plus robuste.

Résultat attendu :

- chaque bloc de la fiche match peut être chargé indépendamment ;
- un échec partiel ne bloque pas tout le parcours ;
- l’utilisateur conserve une interface exploitable ;
- les messages d’indisponibilité restent maîtrisés ;
- le MVP devient plus fiable pour la démonstration.

---

## 9. Validation technique

La validation actuelle repose sur :

```
npm run build OK
```

Preuve archivée :

```
reports/evidence/build_logs/frontend_build.txt
```

Dernier résultat connu :

```
vite v8.0.10
✓ built in 1.52s
```

Cette validation confirme que le frontend React + TypeScript compile correctement après les ajustements d’interface et de robustesse.

---

## 10. Preuves associées

| Preuve | Emplacement |
|---|---|
| Fichier corrigé | `frontend/src/App.tsx` |
| Build frontend validé | `reports/evidence/build_logs/frontend_build.txt` |
| Preuves API utilisées dans le parcours | `reports/evidence/api_responses/` |
| Monitoring applicatif | `docs/application_monitoring.md` |
| Matrice RNCP | `docs/rncp_evidence_matrix.md` |

---

## 11. Impact RNCP

| Compétence | Justification |
|---|---|
| C10 | Le frontend consomme plusieurs routes API et doit gérer leurs réponses proprement |
| C17 | L’interface reste utilisable malgré les cas partiels |
| C18 | La correction est validée par un build frontend |
| C20 | Le cas montre la nécessité de surveiller les routes et les états partiels |
| C21 | L’incident est identifié, corrigé, documenté et relié à une preuve |

---

## 12. Retour d’expérience

Cet incident montre qu’une application Data & IA ne doit pas seulement produire des résultats lorsque toutes les données sont disponibles.

Elle doit aussi gérer les cas dégradés :

- API externe temporairement indisponible ;
- donnée partielle ;
- cache utilisé ;
- contexte incomplet ;
- analyse non disponible ;
- prédiction impossible.

Dans RubyBets, cette logique est importante car l’application travaille avec des données football réelles et dynamiques.

Le choix de rendre les blocs indépendants améliore donc la robustesse du MVP et prépare une architecture plus professionnelle.

---

## 13. Limites de la preuve actuelle

La preuve actuelle est suffisante pour documenter un incident MVP, mais elle peut être renforcée ensuite avec :

- une capture avant/après ;
- une issue GitHub dédiée ;
- un commit explicitement relié à l’incident ;
- un test de non-régression simulant une route indisponible ;
- une capture montrant l’interface avec un bloc partiel.

Ces éléments pourront être ajoutés dans :

```
reports/evidence/incident/
```

---

## 14. Preuves complémentaires à produire

| Priorité | Preuve complémentaire | Emplacement cible |
|---|---|---|
| P1 | Capture du build frontend OK | `reports/evidence/incident/` ou `reports/evidence/build_logs/` |
| P1 | Capture du parcours match fonctionnel | `reports/evidence/screenshots/` |
| P2 | Capture d’un cas partiel maîtrisé | `reports/evidence/incident/` |
| P2 | Commit GitHub lié à la correction | Historique Git |
| P2 | Test de non-régression | `backend/tests/` ou test frontend futur |

---

## 

Un incident important identifié pendant la consolidation du MVP concernait la fragilité du chargement de la fiche match lorsqu’un appel API secondaire échouait. La correction a consisté à rendre les blocs de données indépendants avec une logique de chargement plus robuste. Ainsi, une donnée partielle ne bloque plus tout le parcours utilisateur. Cette correction a été validée par le build frontend et documentée comme preuve de résolution d’incident.
