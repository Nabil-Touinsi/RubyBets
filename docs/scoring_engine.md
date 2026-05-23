# Moteur de scoring RubyBets

<!-- RUBYBETS_ML_1X2_UPDATE_START -->

## Clarification scoring V1 / baseline ML 1X2

RubyBets conserve deux niveaux clairement separes :

1. **Scoring explicable V1** : moteur principal du MVP, base sur des regles metier et des donnees reelles.
2. **Baseline ML 1X2 experimentale** : evolution technique entrainee sur historique, exposee par API pour preuve RNCP, mais non integree au frontend.

### Decision de positionnement

La baseline ML ne remplace pas le scoring explicable V1. Elle sert a demontrer une experimentation Machine Learning propre : preparation du dataset, entrainement, comparaison de modeles, sauvegarde du meilleur modele, exposition API et tests automatises.

### Baseline retenue

| Element | Valeur |
|---|---|
| Type | Classification supervisee |
| Cible | `target_result` |
| Classes | `HOME_WIN`, `DRAW`, `AWAY_WIN` |
| Modele retenu | `LogisticRegression_balanced` |
| Artefact | `models/ml/1x2/best_1x2_model.joblib` |
| Integration produit | Backend experimental uniquement |

### Features utilisees

- `home_form_points_last_5`
- `away_form_points_last_5`
- `home_goals_scored_avg_last_5`
- `away_goals_scored_avg_last_5`
- `home_goals_conceded_avg_last_5`
- `away_goals_conceded_avg_last_5`

La variable `home_advantage` reste exclue de cette baseline car elle ne fournit pas d'information discriminante dans l'etat actuel.

### Limites assumees

- Le modele peut se tromper sur des matchs historiques.
- Les probabilites exposees sont des sorties experimentales.
- Le ML ne garantit aucun resultat sportif.
- Le ML n'est pas utilise dans le frontend MVP.
- Les predictions avancees, comme buts exacts, corners, cartons ou buteurs, restent hors perimetre actuel.

### Formulation soutenance

> RubyBets dispose d'une baseline ML experimentale 1X2 entrainee sur un dataset historique propre. Elle complete le dossier technique Data & IA, mais ne remplace pas le scoring explicable V1 utilise pour le MVP et ne constitue jamais une garantie de resultat sportif.

<!-- RUBYBETS_ML_1X2_UPDATE_END -->

