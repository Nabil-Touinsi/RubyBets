<!--
Rôle du fichier :
centraliser la veille technique/réglementaire de RubyBets et la preuve de coordination des lots techniques.
-->

# Gouvernance projet RubyBets — veille et coordination

## 1. Objectif

Ce document sert de preuve commune pour :

- **C6 — organiser une veille technique et réglementaire** ;
- **C16 — coordonner la réalisation technique**.

Il ne remplace pas les documents détaillés du projet. Il centralise uniquement :

- les sources officielles suivies ;
- les décisions prises pour RubyBets ;
- leur impact réel dans le dépôt ;
- la méthode de coordination et de validation des lots.

Dernière mise à jour : **29 juillet 2026**.

---

## 2. Méthode de veille retenue

La veille RubyBets est organisée autour de six axes directement liés au MVP :

1. source de données football ;
2. API et documentation OpenAPI ;
3. persistance et compatibilité des modèles ML ;
4. intégration continue et artefacts de livraison ;
5. protection des données ;
6. positionnement responsable autour des paris sportifs.

### Fréquence

- revue mensuelle pendant la phase active du projet ;
- revue avant une évolution importante de l’API, du pipeline data ou du moteur ML ;
- revue avant chaque livraison ou soutenance ;
- mise à jour immédiate lorsqu’une source officielle modifie une règle importante.

### Critères de sélection des sources

Les sources privilégiées sont :

- documentation officielle des technologies ;
- autorités publiques ;
- organismes de normalisation ;
- documentation des fournisseurs de données ;
- sources directement reliées à une décision technique du dépôt.

Une source n’est conservée dans la veille que si elle produit une décision ou une action concrète pour RubyBets.

---

## 3. Tableau de veille et décisions RubyBets

| Date consultée | Thème | Source officielle | Information retenue | Décision RubyBets | Preuve dans le dépôt |
|---|---|---|---|---|---|
| 29/07/2026 | API football | football-data.org — documentation API v4 | La documentation v4 constitue la référence courante pour les ressources et appels HTTP. | Maintenir les appels v4, le cache backend, la traçabilité de fraîcheur et l’absence de données fictives. | `backend/app/services/football_data_client.py`, `docs/specs_data.md`, preuves API |
| 29/07/2026 | API REST | FastAPI — fonctionnalités et OpenAPI | FastAPI génère automatiquement une documentation interactive OpenAPI/Swagger et des schémas JSON. | Conserver `/docs`, les contrats Pydantic et les tests de routes comme preuves C5/C9/C10. | `backend/app/api/`, tests API, capture Swagger |
| 29/07/2026 | Modèles ML | scikit-learn — model persistence | Les modèles sérialisés doivent être chargés dans un environnement compatible ; les versions de dépendances doivent rester maîtrisées. | Épingler les versions ML, contrôler les métadonnées et valider automatiquement les artefacts avant livraison. | `backend/requirements.txt`, `validate_model_artifacts.py`, `monitor_model_metrics.py` |
| 29/07/2026 | CI/CD | GitHub Actions — workflow artifacts | Les workflows peuvent produire des artefacts téléchargeables et définir une durée de conservation propre. | Conserver les rapports ML comme artefacts GitHub pendant 30 jours et générer un paquet de livraison versionné. | `backend-tests.yml`, `application-release.yml`, commit `6c5890d` |
| 29/07/2026 | RGPD | CNIL — minimisation et Privacy by Design | Les données personnelles doivent être limitées à ce qui est nécessaire et la protection doit être intégrée dès la conception. | Aucun compte, paiement ou donnée personnelle utilisateur dans le MVP ; secrets hors Git ; contrôle PostgreSQL et documentation RGPD. | `docs/database_rgpd.md`, rapport C4, `.gitignore`, commit `a434806` |
| 29/07/2026 | Usage responsable | ANJ / DGCCRF — vigilance sur les conseils en paris sportifs | Les autorités alertent sur les risques liés aux offres de conseils en paris sportifs et sur les comportements de jeu problématique. | Maintenir RubyBets comme aide analytique non-bookmaker : aucune cote publique, aucun pari réel, aucune promesse, ABSTAIN préservé, messages responsables visibles. | contrats V19, écrans responsables, `docs/scoring_engine.md` |

### Sources officielles suivies

- football-data.org — API v4 :  
  https://docs.football-data.org/general/v4/index.html
- FastAPI — fonctionnalités OpenAPI :  
  https://fastapi.tiangolo.com/fr/features/
- scikit-learn — persistance des modèles :  
  https://scikit-learn.org/stable/model_persistence.html
- GitHub Actions — artefacts de workflow :  
  https://docs.github.com/fr/actions/concepts/workflows-and-actions/workflow-artifacts
- CNIL — minimisation des données :  
  https://www.cnil.fr/fr/minimiser-les-donnees-collectees
- CNIL — guide RGPD du développeur :  
  https://www.cnil.fr/fr/guide-rgpd-du-developpeur
- ANJ / DGCCRF — vigilance sur les conseils en paris sportifs :  
  https://anj.fr/index.php/coupe-du-monde-de-football-la-dgccrf-et-lanj-appellent-la-vigilance-face-aux-sites-de-conseils-ps

---

## 4. Décisions techniques issues de la veille

### Données

- utilisation de données football réelles et documentées ;
- conservation de la fraîcheur et de la source dans les réponses ;
- aucune fabrication d’une valeur métier en cas d’indisponibilité ;
- cache utilisé pour la robustesse, sans masquer l’origine des données.

### API

- FastAPI reste le point d’exposition central ;
- Swagger/OpenAPI sert de preuve de contrat ;
- les erreurs partielles ne doivent pas bloquer tout le parcours ;
- les réponses publiques ne doivent exposer ni secret, ni cote bookmaker, ni score interne non maîtrisé.

### Machine Learning

- les artefacts `.joblib` sont accompagnés de métadonnées ;
- les versions ML sont épinglées dans `requirements.txt` ;
- les modèles sont validés avant livraison ;
- les métriques sont suivies automatiquement ;
- une décision `ABSTAIN` n’est jamais transformée en recommandation.

### Conformité et responsabilité

- aucune collecte de données personnelles utilisateur dans le MVP ;
- aucune fonctionnalité de paiement ou de prise de pari ;
- RubyBets reste une aide à la décision ;
- confiance, risque, justification et limites restent visibles ;
- les futures fonctions de compte utilisateur imposeront une nouvelle analyse RGPD.

---

## 5. Méthode de coordination technique

Chaque lot RubyBets suit le même cycle :

```text
Audit du besoin
      ↓
Définition d'un périmètre isolé
      ↓
Validation explicite avant modification
      ↓
Développement ou documentation ciblée
      ↓
Tests locaux et contrôle Git
      ↓
Validation explicite avant commit
      ↓
Commit séparé et push
      ↓
Contrôle GitHub Actions
      ↓
Mise à jour du statut de la compétence
```

### Règles appliquées

- aucun `git add .` ni `git add -A` ;
- aucun commit sans validation explicite ;
- un commit par lot cohérent ;
- préservation de la logique V19 ;
- absence de données métier inventées ;
- tests backend et frontend avant validation ;
- vérification des workflows après push ;
- dossiers non suivis protégés tant qu’ils ne sont pas audités séparément.

---

## 6. Journal synthétique des lots coordonnés

| Lot | Résultat | Validation | Commit / tag | Compétences renforcées |
|---|---|---|---|---|
| Consolidation backend | Code V17/V18 archivé, logique V19 préservée, tests consolidés | 285 tests réussis avant les lots de preuve | `84ab7e4` | C12, C16, C21 |
| Consolidation frontend | Écrans actifs conservés, code obsolète supprimé, lint et build validés | Build Vite réussi | `dcd97df` | C16, C17, C18 |
| Validation et livraison ML | 7 artefacts contrôlés, workflow de release et paquet de livraison | Backend/Frontend CI verts, Application release verte | `6c5890d` | C13, C19 |
| Monitoring et incident | Endpoints de santé, journal d’incident, tests de non-régression | 287 tests réussis et CI verte | `0f08103` | C20, C21 |
| Monitoring des modèles | 7 modèles et 33 métriques suivis automatiquement | 287 tests réussis et CI verte | `73c1c4c` | C11, C12, C18 |
| PostgreSQL et RGPD | 17 tables, 12 relations, aucune donnée personnelle MVP détectée | Rapport PostgreSQL `PASSED` | `a434806` | C4 |
| Consolidation du code | Version stable identifiée après audit global | Tag poussé | `rubybets-v0.14-codebase-consolidation` | C16, C19 |

---

## 7. Éléments protégés et décisions différées

Ces dossiers restent volontairement hors Git tant qu’un audit séparé n’a pas été validé :

```text
archive/frontend_legacy/
docs/architecture/
```

Le nettoyage de `App.css` reste isolé et ne bloque pas la couverture RNCP.

Cette séparation montre que la coordination repose sur des décisions explicites, et non sur l’ajout automatique de tous les fichiers présents localement.

---

## 8. Preuves associées à C6 et C16

### C6 — veille technique et réglementaire

Preuves :

- tableau de veille daté ;
- sources officielles qualifiées ;
- décisions concrètes reliées au dépôt ;
- positionnement responsable mis à jour selon les alertes ANJ/DGCCRF ;
- règles RGPD reliées au modèle de données réel.

**Statut cible après versioning de ce document : preuve suffisante.**

### C16 — coordination de la réalisation technique

Preuves :

- méthode de lotissement et de validation ;
- historique de commits isolés ;
- tests et workflows vérifiés après chaque lot ;
- tag de consolidation ;
- gestion explicite des éléments protégés et différés ;
- correspondance entre lots, commits et compétences.

**Statut cible après versioning de ce document : preuve suffisante.**

---

## 9. Prochaine revue

La prochaine revue de veille devra être réalisée :

- avant la préparation finale du support de soutenance ;
- lors d’une mise à niveau majeure de FastAPI, scikit-learn, React ou Vite ;
- avant toute collecte de données utilisateur ;
- avant toute évolution rapprochant RubyBets d’un service de pari ou de conseil commercial.

---

<!--
Schéma de communication :
sources officielles
      ↓
docs/project_governance.md
      ↓
décisions techniques + lots Git
      ↓
README / matrice C1-C21 / support de soutenance
-->
