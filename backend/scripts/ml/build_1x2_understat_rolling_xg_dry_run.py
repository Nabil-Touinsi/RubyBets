# Rôle du fichier :
# Ce script calcule en dry-run des variables rolling xG pré-match à partir du matching Understat -> ml.clean_matches.
# Il ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ni les modèles sauvegardés.

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_INPUT_CANDIDATES = [
    "reports/evidence/ml_training/120_1x2_understat_clean_match_dry_run_v2_matches.csv",
    "reports/evidence/ml_training/115_1x2_understat_clean_match_dry_run_matches.csv",
]

OUTPUT_SUMMARY = "124_1x2_understat_rolling_xg_dry_run_summary.txt"
OUTPUT_FEATURES = "125_1x2_understat_rolling_xg_dry_run_features.csv"
OUTPUT_BY_SEASON = "126_1x2_understat_rolling_xg_dry_run_by_league_season.csv"
OUTPUT_SAMPLES = "127_1x2_understat_rolling_xg_dry_run_samples.csv"
OUTPUT_NEXT_ACTION = "128_1x2_understat_rolling_xg_dry_run_next_action.txt"

REQUIRED_COLUMNS = [
    "clean_match_id",
    "understat_match_id",
    "league_code",
    "season",
    "clean_date",
    "clean_home_team",
    "clean_away_team",
    "clean_home_goals",
    "clean_away_goals",
    "home_xg",
    "away_xg",
]

FEATURE_COLUMNS = [
    "home_xg_for_avg_last_5",
    "home_xg_against_avg_last_5",
    "home_xg_diff_avg_last_5",
    "away_xg_for_avg_last_5",
    "away_xg_against_avg_last_5",
    "away_xg_diff_avg_last_5",
    "xg_for_diff_last_5",
    "xg_against_diff_last_5",
    "xg_balance_diff_last_5",
]


@dataclass
class RollingRunStats:
    """Résumé technique produit à la fin du dry-run."""

    input_path: Path
    loaded_rows: int
    matched_rows: int
    duplicate_clean_match_rows_removed: int
    output_rows: int
    complete_feature_rows: int
    incomplete_feature_rows: int
    complete_feature_rate: float
    unique_teams: int
    status: str


# Trouve automatiquement la racine du projet RubyBets à partir de l'emplacement du script.
def resolve_project_root() -> Path:
    current_path = Path(__file__).resolve()

    for parent in [current_path.parent, *current_path.parents]:
        if (parent / "backend").exists() and (parent / "reports").exists():
            return parent

    # Cas normal si le script est placé dans backend/scripts/ml/.
    try:
        return current_path.parents[3]
    except IndexError:
        return Path.cwd()


# Crée le dossier de sortie reports/evidence/ml_training si nécessaire.
def ensure_output_dir(project_root: Path) -> Path:
    output_dir = project_root / "reports" / "evidence" / "ml_training"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# Retrouve le CSV de matching V2 en priorité, sinon bascule sur le matching V1 si besoin.
def resolve_input_path(project_root: Path, input_arg: str | None) -> Path:
    if input_arg:
        candidate = Path(input_arg)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        if not candidate.exists():
            raise FileNotFoundError(f"CSV introuvable : {candidate}")
        return candidate

    for relative_path in DEFAULT_INPUT_CANDIDATES:
        candidate = project_root / relative_path
        if candidate.exists():
            return candidate

    candidates_as_text = "\n".join(f"- {project_root / path}" for path in DEFAULT_INPUT_CANDIDATES)
    raise FileNotFoundError(
        "Aucun CSV de matching Understat -> clean_matches trouve.\n"
        f"Chemins testes :\n{candidates_as_text}"
    )


# Convertit une valeur en float de manière robuste.
def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    text_value = str(value).strip()
    if not text_value or text_value.lower() in {"nan", "none", "null"}:
        return None

    try:
        return float(text_value)
    except ValueError:
        return None


# Calcule une moyenne simple en ignorant les valeurs absentes.
def mean_or_none(values: list[float]) -> float | None:
    cleaned_values = [value for value in values if value is not None and not math.isnan(value)]
    if not cleaned_values:
        return None
    return round(sum(cleaned_values) / len(cleaned_values), 4)


# Calcule les indicateurs rolling d'une équipe à partir de son historique avant le match.
def compute_team_rolling_features(history: list[dict[str, Any]], window_size: int = 5) -> dict[str, Any]:
    recent_history = history[-window_size:]

    xg_for_values = [event["xg_for"] for event in recent_history]
    xg_against_values = [event["xg_against"] for event in recent_history]
    xg_diff_values = [event["xg_diff"] for event in recent_history]

    return {
        "matches_available": len(recent_history),
        "xg_for_avg": mean_or_none(xg_for_values),
        "xg_against_avg": mean_or_none(xg_against_values),
        "xg_diff_avg": mean_or_none(xg_diff_values),
    }


# Valide les colonnes minimales attendues dans le CSV de matching.
def validate_input_columns(df: pd.DataFrame) -> None:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Colonnes manquantes dans le CSV de matching : "
            + ", ".join(missing_columns)
        )


# Charge et nettoie uniquement les lignes matchées utiles au calcul rolling xG.
def load_matched_understat_rows(input_path: Path) -> tuple[pd.DataFrame, int]:
    df = pd.read_csv(input_path)
    validate_input_columns(df)

    loaded_rows = len(df)

    df = df.copy()
    df["clean_match_id"] = pd.to_numeric(df["clean_match_id"], errors="coerce")
    df["understat_match_id"] = pd.to_numeric(df["understat_match_id"], errors="coerce")
    df["home_xg"] = pd.to_numeric(df["home_xg"], errors="coerce")
    df["away_xg"] = pd.to_numeric(df["away_xg"], errors="coerce")
    df["clean_date"] = pd.to_datetime(df["clean_date"], errors="coerce")

    df = df.dropna(
        subset=[
            "clean_match_id",
            "understat_match_id",
            "league_code",
            "season",
            "clean_date",
            "clean_home_team",
            "clean_away_team",
            "home_xg",
            "away_xg",
        ]
    )

    df = df.sort_values(
        by=["clean_date", "league_code", "clean_match_id"],
        ascending=[True, True, True],
    )

    before_dedup = len(df)
    df = df.drop_duplicates(subset=["clean_match_id"], keep="first")
    duplicate_removed = before_dedup - len(df)

    df["clean_match_id"] = df["clean_match_id"].astype(int)
    df["understat_match_id"] = df["understat_match_id"].astype(int)
    df["clean_date"] = df["clean_date"].dt.date.astype(str)

    return df.reset_index(drop=True), duplicate_removed


# Calcule les features rolling xG pré-match sans fuite de donnée du match en cours.
def build_rolling_xg_features(df: pd.DataFrame, window_size: int = 5) -> pd.DataFrame:
    histories_by_team: dict[str, list[dict[str, Any]]] = {}
    output_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        home_team = str(row["clean_home_team"]).strip()
        away_team = str(row["clean_away_team"]).strip()

        home_history = histories_by_team.get(home_team, [])
        away_history = histories_by_team.get(away_team, [])

        home_features = compute_team_rolling_features(home_history, window_size=window_size)
        away_features = compute_team_rolling_features(away_history, window_size=window_size)

        enriched_row = {
            "clean_match_id": row["clean_match_id"],
            "understat_match_id": row["understat_match_id"],
            "league_code": row["league_code"],
            "season": row["season"],
            "clean_date": row["clean_date"],
            "home_team": home_team,
            "away_team": away_team,
            "home_goals": row.get("clean_home_goals"),
            "away_goals": row.get("clean_away_goals"),
            "home_xg": round(float(row["home_xg"]), 4),
            "away_xg": round(float(row["away_xg"]), 4),
            "result": row.get("result"),
            "home_xg_matches_available_last_5": home_features["matches_available"],
            "away_xg_matches_available_last_5": away_features["matches_available"],
            "home_xg_for_avg_last_5": home_features["xg_for_avg"],
            "home_xg_against_avg_last_5": home_features["xg_against_avg"],
            "home_xg_diff_avg_last_5": home_features["xg_diff_avg"],
            "away_xg_for_avg_last_5": away_features["xg_for_avg"],
            "away_xg_against_avg_last_5": away_features["xg_against_avg"],
            "away_xg_diff_avg_last_5": away_features["xg_diff_avg"],
            "match_url": row.get("match_url"),
        }

        enriched_row["xg_for_diff_last_5"] = subtract_or_none(
            enriched_row["home_xg_for_avg_last_5"],
            enriched_row["away_xg_for_avg_last_5"],
        )
        enriched_row["xg_against_diff_last_5"] = subtract_or_none(
            enriched_row["home_xg_against_avg_last_5"],
            enriched_row["away_xg_against_avg_last_5"],
        )
        enriched_row["xg_balance_diff_last_5"] = subtract_or_none(
            enriched_row["home_xg_diff_avg_last_5"],
            enriched_row["away_xg_diff_avg_last_5"],
        )

        output_rows.append(enriched_row)

        home_xg = float(row["home_xg"])
        away_xg = float(row["away_xg"])

        histories_by_team.setdefault(home_team, []).append(
            {
                "date": row["clean_date"],
                "opponent": away_team,
                "venue": "home",
                "xg_for": home_xg,
                "xg_against": away_xg,
                "xg_diff": home_xg - away_xg,
            }
        )

        histories_by_team.setdefault(away_team, []).append(
            {
                "date": row["clean_date"],
                "opponent": home_team,
                "venue": "away",
                "xg_for": away_xg,
                "xg_against": home_xg,
                "xg_diff": away_xg - home_xg,
            }
        )

    return pd.DataFrame(output_rows)


# Soustrait deux valeurs numériques si elles sont disponibles.
def subtract_or_none(left_value: Any, right_value: Any) -> float | None:
    left_number = safe_float(left_value)
    right_number = safe_float(right_value)

    if left_number is None or right_number is None:
        return None

    return round(left_number - right_number, 4)


# Produit le bilan par ligue/saison pour vérifier la couverture des features rolling.
def build_by_league_season_summary(features_df: pd.DataFrame) -> pd.DataFrame:
    grouped_rows: list[dict[str, Any]] = []

    for (league_code, season), group in features_df.groupby(["league_code", "season"], dropna=False):
        total_rows = len(group)
        complete_rows = int(group[FEATURE_COLUMNS].notna().all(axis=1).sum())
        incomplete_rows = total_rows - complete_rows
        complete_rate = round(complete_rows / total_rows, 4) if total_rows else 0.0

        grouped_rows.append(
            {
                "league_code": league_code,
                "season": season,
                "rows": total_rows,
                "complete_feature_rows": complete_rows,
                "incomplete_feature_rows": incomplete_rows,
                "complete_feature_rate": complete_rate,
                "avg_home_history_available": round(
                    float(group["home_xg_matches_available_last_5"].mean()), 4
                ),
                "avg_away_history_available": round(
                    float(group["away_xg_matches_available_last_5"].mean()), 4
                ),
                "status": "AVAILABLE" if complete_rate >= 0.85 else "REVIEW_NEEDED",
            }
        )

    return pd.DataFrame(grouped_rows).sort_values(["league_code", "season"])


# Détermine le statut global du dry-run rolling xG.
def determine_status(features_df: pd.DataFrame) -> tuple[str, int, int, float]:
    total_rows = len(features_df)

    if total_rows == 0:
        return "V8_UNDERSTAT_ROLLING_XG_DRY_RUN_EMPTY", 0, 0, 0.0

    complete_rows = int(features_df[FEATURE_COLUMNS].notna().all(axis=1).sum())
    incomplete_rows = total_rows - complete_rows
    complete_rate = round(complete_rows / total_rows, 4)

    if complete_rate >= 0.85:
        status = "V8_UNDERSTAT_ROLLING_XG_DRY_RUN_AVAILABLE"
    else:
        status = "V8_UNDERSTAT_ROLLING_XG_DRY_RUN_REVIEW_NEEDED"

    return status, complete_rows, incomplete_rows, complete_rate


# Sauvegarde les CSV de features, de synthèse par saison et d'échantillon de contrôle.
def save_csv_outputs(
    output_dir: Path,
    features_df: pd.DataFrame,
    by_season_df: pd.DataFrame,
) -> tuple[Path, Path, Path]:
    features_path = output_dir / OUTPUT_FEATURES
    by_season_path = output_dir / OUTPUT_BY_SEASON
    samples_path = output_dir / OUTPUT_SAMPLES

    features_df.to_csv(features_path, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)
    by_season_df.to_csv(by_season_path, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)

    sample_columns = [
        "clean_match_id",
        "understat_match_id",
        "league_code",
        "season",
        "clean_date",
        "home_team",
        "away_team",
        "home_xg",
        "away_xg",
        "home_xg_for_avg_last_5",
        "home_xg_against_avg_last_5",
        "away_xg_for_avg_last_5",
        "away_xg_against_avg_last_5",
        "xg_balance_diff_last_5",
        "result",
    ]

    complete_sample = features_df[features_df[FEATURE_COLUMNS].notna().all(axis=1)].head(30)
    incomplete_sample = features_df[~features_df[FEATURE_COLUMNS].notna().all(axis=1)].head(30)
    samples_df = pd.concat([complete_sample, incomplete_sample], ignore_index=True)
    samples_df[sample_columns].to_csv(samples_path, index=False, encoding="utf-8")

    return features_path, by_season_path, samples_path


# Écrit la synthèse texte du dry-run rolling xG.
def write_summary(
    output_dir: Path,
    stats: RollingRunStats,
    features_path: Path,
    by_season_path: Path,
    samples_path: Path,
) -> Path:
    summary_path = output_dir / OUTPUT_SUMMARY

    lines = [
        "RubyBets - ML 1X2 V8 Understat rolling xG dry-run",
        "124 - Synthese calcul rolling xG pre-match",
        "",
        "Objectif :",
        "Calculer des variables rolling xG pre-match a partir du matching Understat -> ml.clean_matches.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Aucune integration produit d'Understat.",
        "- Dry-run experimental interne uniquement.",
        "",
        "Parametres :",
        f"- CSV de matching utilise : {stats.input_path}",
        "- Fenetre rolling : last_5 matchs precedents de chaque equipe.",
        "- Fuite de donnees evitee : le match courant n'est pas utilise pour calculer ses propres features.",
        "",
        "Resultat global :",
        f"- Matching rows loaded : {stats.loaded_rows}",
        f"- Rows utilisables apres nettoyage : {stats.matched_rows}",
        f"- Doublons clean_match_id retires : {stats.duplicate_clean_match_rows_removed}",
        f"- Feature rows generated : {stats.output_rows}",
        f"- Complete feature rows : {stats.complete_feature_rows}",
        f"- Incomplete feature rows : {stats.incomplete_feature_rows}",
        f"- Complete feature rate : {stats.complete_feature_rate}",
        f"- Unique teams with xG history : {stats.unique_teams}",
        f"- Status : {stats.status}",
        "",
        "Features principales generees :",
        "- home_xg_for_avg_last_5",
        "- home_xg_against_avg_last_5",
        "- home_xg_diff_avg_last_5",
        "- away_xg_for_avg_last_5",
        "- away_xg_against_avg_last_5",
        "- away_xg_diff_avg_last_5",
        "- xg_for_diff_last_5",
        "- xg_against_diff_last_5",
        "- xg_balance_diff_last_5",
        "",
        "Fichiers generes :",
        str(summary_path),
        str(features_path),
        str(by_season_path),
        str(samples_path),
        str(output_dir / OUTPUT_NEXT_ACTION),
        "",
        "Decision attendue :",
        "- Si le taux de features completes est coherent : valider le CSV 125.",
        "- Controler le CSV 126 pour identifier d'eventuelles ligues/saisons a revoir.",
        "- Ne pas entrainer de modele tant que les features rolling xG n'ont pas ete validees.",
        "",
        "Statut de suivi :",
        "- Tache realisee si les fichiers 124, 125, 126, 127 et 128 sont generes.",
        "- Statut source a mettre a jour : a produire -> realise pour le calcul rolling xG pre-match en dry-run.",
    ]

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


# Écrit la prochaine action recommandée après le dry-run.
def write_next_action(output_dir: Path, status: str, complete_feature_rate: float) -> Path:
    next_action_path = output_dir / OUTPUT_NEXT_ACTION

    if status == "V8_UNDERSTAT_ROLLING_XG_DRY_RUN_AVAILABLE":
        decision = (
            "Les features rolling xG pre-match sont exploitables en dry-run. "
            "La prochaine action est de valider les CSV 125 et 126, puis de preparer une experience ML V8 en memoire."
        )
    else:
        decision = (
            "Les features rolling xG demandent une revue. "
            "La prochaine action est d'analyser les lignes incompletes dans le CSV 127 et les groupes REVIEW_NEEDED dans le CSV 126."
        )

    lines = [
        "RubyBets - ML 1X2 V8 Understat rolling xG dry-run",
        "128 - Prochaine action recommandee",
        "",
        "Resultat :",
        f"Status : {status}",
        f"Complete feature rate : {complete_feature_rate}",
        "",
        "Decision :",
        decision,
        "",
        "Ordre des prochaines actions :",
        "1. Controler reports/evidence/ml_training/125_1x2_understat_rolling_xg_dry_run_features.csv.",
        "2. Verifier que les features rolling xG sont bien pre-match et ne contiennent pas le match courant.",
        "3. Controler reports/evidence/ml_training/126_1x2_understat_rolling_xg_dry_run_by_league_season.csv.",
        "4. Identifier les groupes REVIEW_NEEDED si certains existent.",
        "5. Creer ensuite une experience ML V8 en memoire, sans modifier ml.features au premier test.",
        "",
        "Garde-fou :",
        "Understat reste une source experimentale interne. Aucune integration produit, API ou frontend pour le moment.",
    ]

    next_action_path.write_text("\n".join(lines), encoding="utf-8")
    return next_action_path


# Orchestration principale du dry-run rolling xG.
def run_rolling_xg_dry_run(input_path_arg: str | None = None, window_size: int = 5) -> None:
    project_root = resolve_project_root()
    output_dir = ensure_output_dir(project_root)
    input_path = resolve_input_path(project_root, input_path_arg)

    print("Chargement du matching Understat -> ml.clean_matches...")
    matched_df, duplicate_removed = load_matched_understat_rows(input_path)
    print(f"Rows utilisables chargees: {len(matched_df)}")

    print("Calcul des rolling xG pre-match en dry-run...")
    features_df = build_rolling_xg_features(matched_df, window_size=window_size)
    by_season_df = build_by_league_season_summary(features_df)

    status, complete_rows, incomplete_rows, complete_rate = determine_status(features_df)

    stats = RollingRunStats(
        input_path=input_path,
        loaded_rows=len(pd.read_csv(input_path)),
        matched_rows=len(matched_df),
        duplicate_clean_match_rows_removed=duplicate_removed,
        output_rows=len(features_df),
        complete_feature_rows=complete_rows,
        incomplete_feature_rows=incomplete_rows,
        complete_feature_rate=complete_rate,
        unique_teams=int(
            pd.concat([features_df["home_team"], features_df["away_team"]]).nunique()
        ),
        status=status,
    )

    print("Generation des preuves CSV et synthese...")
    features_path, by_season_path, samples_path = save_csv_outputs(
        output_dir=output_dir,
        features_df=features_df,
        by_season_df=by_season_df,
    )
    summary_path = write_summary(
        output_dir=output_dir,
        stats=stats,
        features_path=features_path,
        by_season_path=by_season_path,
        samples_path=samples_path,
    )
    next_action_path = write_next_action(
        output_dir=output_dir,
        status=status,
        complete_feature_rate=complete_rate,
    )

    print("OK - Rolling xG dry-run termine.")
    print(f"Rows generated: {stats.output_rows}")
    print(f"Complete feature rows: {stats.complete_feature_rows}")
    print(f"Incomplete feature rows: {stats.incomplete_feature_rows}")
    print(f"Complete feature rate: {stats.complete_feature_rate}")
    print(f"Status: {stats.status}")
    print(f"Summary saved: {summary_path}")
    print(f"Features CSV saved: {features_path}")
    print(f"By season CSV saved: {by_season_path}")
    print(f"Samples CSV saved: {samples_path}")
    print(f"Next action saved: {next_action_path}")


# Point d'entrée CLI du script.
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calcule en dry-run les rolling xG pre-match depuis le matching Understat V2."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Chemin optionnel vers le CSV de matching Understat -> clean_matches.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=5,
        help="Nombre de matchs precedents a utiliser pour le rolling xG.",
    )

    args = parser.parse_args()

    try:
        run_rolling_xg_dry_run(
            input_path_arg=args.input,
            window_size=args.window_size,
        )
    except Exception as exc:
        print("ERREUR - Rolling xG dry-run interrompu.")
        print(f"Type: {type(exc).__name__}")
        print(f"Message: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# backend/scripts/ml/build_1x2_understat_rolling_xg_dry_run.py
#        |
#        | lit
#        v
# reports/evidence/ml_training/120_1x2_understat_clean_match_dry_run_v2_matches.csv
#        |
#        | calcule en mémoire, sans insertion SQL
#        v
# reports/evidence/ml_training/124_...summary.txt
# reports/evidence/ml_training/125_...features.csv
# reports/evidence/ml_training/126_...by_league_season.csv
# reports/evidence/ml_training/127_...samples.csv
# reports/evidence/ml_training/128_...next_action.txt
