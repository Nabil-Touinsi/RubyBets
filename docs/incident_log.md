# Journal d'incident RubyBets

<!-- Rôle du fichier : conserver la preuve complète d'un incident technique, de son diagnostic, de sa correction et de sa non-régression. -->

## Incident RB-INC-2026-07-29-01 — Workflow de livraison applicative

| Champ | Valeur |
|---|---|
| Date | 29 juillet 2026 |
| Périmètre | CI/CD et génération du paquet RubyBets |
| Gravité | Élevée avant livraison, sans impact utilisateur |
| Statut | Clos |
| Commit correctif | `6c5890d` — `ci: validate ML artifacts and automate releases` |

## 1. Symptôme

Le workflow `application-release.yml` n'avait pas été extrait depuis l'archive prévue. Lors de sa création directe, une commande Bash contenait ensuite un caractère de continuation PowerShell — le backtick — à la place de l'antislash Bash.

Sans correction, l'étape de copie du rapport de validation ML aurait pu interrompre la construction du paquet sur le runner Ubuntu.

## 2. Détection

L'incident a été détecté avant commit pendant la revue du lot :

- `git status --short` a montré l'absence initiale de `.github/workflows/application-release.yml` ;
- `git diff --cached` a permis d'identifier la continuation de ligne incompatible avec Bash ;
- aucun tag ni paquet défectueux n'a été publié.

## 3. Cause racine

Deux causes ont été isolées :

1. l'archive du workflow n'était pas présente dans le dossier Téléchargements ;
2. une syntaxe PowerShell avait été copiée dans une étape explicitement exécutée avec `shell: bash`.

Il ne s'agissait pas d'un défaut du moteur V19 ni des modèles ML.

## 4. Correction appliquée

- création directe de `.github/workflows/application-release.yml` dans le dépôt ;
- remplacement du backtick par l'antislash Bash `\` ;
- ajout de `set -euo pipefail` pour interrompre immédiatement le paquetage en cas d'erreur ;
- ajout de contrôles bloquants : 285 tests backend, validation des 7 artefacts ML, lint et build frontend ;
- publication du paquet uniquement après réussite complète du job.

## 5. Validation et non-régression

| Contrôle | Résultat |
|---|---|
| Tests backend locaux | 285/285 réussis en 22,60 s |
| Validation modèles locale | 7/7 artefacts valides, 0 erreur, 0 avertissement |
| `git diff --cached --check` | aucune erreur |
| GitHub Actions Backend tests #92 | succès |
| GitHub Actions Frontend build #90 | succès |
| GitHub Actions Application release #1 | succès en 1 min 13 s |
| Artefact de livraison | 1 paquet généré |

Le dépôt est revenu à un état propre après le push, à l'exception des deux dossiers volontairement non suivis : `archive/frontend_legacy/` et `docs/architecture/`.

## 6. Mesures préventives

- distinguer explicitement les syntaxes PowerShell et Bash dans les workflows ;
- vérifier chaque nouveau workflow avec `git diff --cached --check` avant commit ;
- exécuter manuellement `Application release` avant d'utiliser un nouveau tag ;
- conserver les tests, le lint, le build et la validation des modèles comme portes bloquantes ;
- ne jamais publier de release lorsque le paquet ou son empreinte SHA-256 manque.

## 7. Conclusion RNCP

L'incident a été identifié, diagnostiqué, corrigé, testé et versionné. La réussite d'`Application release #1` et la génération de l'artefact constituent la preuve de non-régression.

**C21 — preuve suffisante.**

<!-- Schéma de communication : application-release.yml -> tests backend + validation ML + build frontend -> paquet + SHA-256 -> artefact GitHub. -->
