# Rôle du fichier :
# Ce script analyse les erreurs de la baseline nationale V17.9
# afin d'identifier les segments faibles avant tout enrichissement StatsBomb.

from pathlib import Path
import argparse
import csv
import os
import sys
from decimal import Decimal

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_FEATURE_VERSION = "national_v1_elo_form"
DEFAULT_PREDICTIONS_FILE = EVIDENCE_DIR / "306_national_v17_9_predictions.csv"

SUMMARY_FILENAME = "307_national_v17_9_diagnostic_summary.txt"
SEGMENTS_FILENAME = "308_national_v17_9_diagnostic_segments.csv"
ERRORS_FILENAME = "309_national_v17_9_error_patterns.csv"
DRAW_ERRORS_FILENAME = "310_national_v17_9_draw_errors.csv"

TARGET_LABELS = [
    "TEAM_A_WIN",
    "DRAW",
    "TEAM_B_WIN",
]


# Charge les variables du fichier backend/.env sans afficher de secret.
def load_env_file() -> None:
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"Fichier .env introuvable : {ENV_PATH}")

    with ENV_PATH.open("r", encoding="utf-8") as env_file:
        for line in env_file:
            clean_line = line.strip()

            if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                continue

            key, value = clean_line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Récupère l'URL PostgreSQL depuis backend/.env.
def get_database_url() -> str:
    load_env_file()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL est absent du fichier backend/.env")

    return database_url


# Prépare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnostiquer les erreurs de la baseline nationale V17.9."
    )

    parser.add_argument(
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help="Version des features utilisée pour le diagnostic.",
    )

    parser.add_argument(
        "--predictions-file",
        default=str(DEFAULT_PREDICTIONS_FILE),
        help="Chemin du CSV de prédictions généré par train_national_v17_9_baseline.py.",
    )

    return parser.parse_args()


# Crée le dossier de preuves ML si nécessaire.
def ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# Convertit les valeurs PostgreSQL numériques en float.
def normalize_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)

    return value


# Charge les prédictions produites par le script d'entraînement.
def load_predictions(predictions_file: str) -> pd.DataFrame:
    predictions_path = Path(predictions_file)

    if not predictions_path.exists():
        raise FileNotFoundError(f"Fichier de prédictions introuvable : {predictions_path}")

    dataframe = pd.read_csv(predictions_path)

    required_columns = {
        "clean_match_id",
        "target_result",
        "predicted_result",
        "is_correct",
    }

    missing_columns = required_columns - set(dataframe.columns)

    if missing_columns:
        raise ValueError(f"Colonnes manquantes dans le CSV prédictions : {missing_columns}")

    dataframe["clean_match_id"] = dataframe["clean_match_id"].astype(int)
    dataframe["is_correct"] = dataframe["is_correct"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    )

    return dataframe


# Récupère les features et le contexte match depuis PostgreSQL.
def fetch_feature_context(
    connection: psycopg.Connection,
    feature_version: str,
) -> pd.DataFrame:
    query = """
        SELECT
            f.clean_match_id,
            f.feature_version,
            cm.match_date_utc,
            cm.competition_code,
            cm.season,
            cm.home_team_name AS team_a_name,
            cm.away_team_name AS team_b_name,
            f.home_form_points_last_10,
            f.away_form_points_last_10,
            f.home_goals_scored_avg_last_10,
            f.away_goals_scored_avg_last_10,
            f.home_goals_conceded_avg_last_10,
            f.away_goals_conceded_avg_last_10,
            f.elo_gap,
            f.is_neutral_venue,
            f.team_a_is_host,
            f.team_b_is_host,
            f.host_advantage_side,
            f.is_group_stage,
            f.is_knockout_stage,
            f.target_result
        FROM ml_national.features f
        JOIN ml_national.clean_matches cm
            ON cm.id = f.clean_match_id
        WHERE f.feature_version = %s
        ORDER BY cm.match_date_utc ASC, f.clean_match_id ASC
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (feature_version,))
        rows = cursor.fetchall()

    normalized_rows = [
        {key: normalize_value(value) for key, value in row.items()}
        for row in rows
    ]

    return pd.DataFrame(normalized_rows)


# Fusionne les prédictions avec les features de contexte.
def build_diagnostic_dataframe(
    predictions_dataframe: pd.DataFrame,
    feature_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    diagnostic_dataframe = predictions_dataframe.merge(
        feature_dataframe.drop(columns=["target_result"], errors="ignore"),
        on="clean_match_id",
        how="left",
        suffixes=("", "_feature"),
    )

    diagnostic_dataframe["match_date_utc"] = pd.to_datetime(
        diagnostic_dataframe["match_date_utc"],
        utc=True,
    )

    diagnostic_dataframe["elo_gap"] = pd.to_numeric(
        diagnostic_dataframe["elo_gap"],
        errors="coerce",
    )

    diagnostic_dataframe["abs_elo_gap"] = diagnostic_dataframe["elo_gap"].abs()

    diagnostic_dataframe["elo_gap_bucket"] = pd.cut(
        diagnostic_dataframe["abs_elo_gap"],
        bins=[-1, 50, 100, 200, 400, 10000],
        labels=["0-50", "50-100", "100-200", "200-400", "400+"],
    )

    diagnostic_dataframe["is_neutral_venue"] = diagnostic_dataframe["is_neutral_venue"].fillna(False)
    diagnostic_dataframe["team_a_is_host"] = diagnostic_dataframe["team_a_is_host"].fillna(False)
    diagnostic_dataframe["team_b_is_host"] = diagnostic_dataframe["team_b_is_host"].fillna(False)
    diagnostic_dataframe["is_group_stage"] = diagnostic_dataframe["is_group_stage"].fillna(False)
    diagnostic_dataframe["is_knockout_stage"] = diagnostic_dataframe["is_knockout_stage"].fillna(False)
    diagnostic_dataframe["host_advantage_side"] = diagnostic_dataframe["host_advantage_side"].fillna("NONE")

    return diagnostic_dataframe


# Calcule les métriques globales du diagnostic.
def build_global_metrics(diagnostic_dataframe: pd.DataFrame) -> dict[str, float]:
    y_true = diagnostic_dataframe["target_result"]
    y_pred = diagnostic_dataframe["predicted_result"]

    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "f1_macro": f1_score(y_true, y_pred, average="macro"),
        "f1_weighted": f1_score(y_true, y_pred, average="weighted"),
    }


# Calcule les métriques d'un segment donné.
def build_segment_metrics(
    dataframe: pd.DataFrame,
    segment_name: str,
    segment_value: object,
) -> dict[str, object]:
    if dataframe.empty:
        return {
            "segment_name": segment_name,
            "segment_value": segment_value,
            "rows": 0,
            "accuracy": None,
            "f1_macro": None,
            "team_a_win_rows": 0,
            "draw_rows": 0,
            "team_b_win_rows": 0,
        }

    y_true = dataframe["target_result"]
    y_pred = dataframe["predicted_result"]

    return {
        "segment_name": segment_name,
        "segment_value": segment_value,
        "rows": len(dataframe),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "f1_macro": round(f1_score(y_true, y_pred, average="macro"), 4),
        "team_a_win_rows": int((dataframe["target_result"] == "TEAM_A_WIN").sum()),
        "draw_rows": int((dataframe["target_result"] == "DRAW").sum()),
        "team_b_win_rows": int((dataframe["target_result"] == "TEAM_B_WIN").sum()),
    }


# Construit les diagnostics par segments métier.
def build_segment_diagnostics(diagnostic_dataframe: pd.DataFrame) -> list[dict[str, object]]:
    segment_rows = []

    segment_columns = [
        "competition_code",
        "is_neutral_venue",
        "host_advantage_side",
        "is_group_stage",
        "is_knockout_stage",
        "elo_gap_bucket",
        "target_result",
    ]

    for column in segment_columns:
        for value, segment_dataframe in diagnostic_dataframe.groupby(column, dropna=False):
            segment_rows.append(
                build_segment_metrics(
                    dataframe=segment_dataframe,
                    segment_name=column,
                    segment_value=value,
                )
            )

    return segment_rows


# Extrait les erreurs les plus fréquentes du modèle.
def build_error_patterns(diagnostic_dataframe: pd.DataFrame) -> pd.DataFrame:
    errors_dataframe = diagnostic_dataframe[
        diagnostic_dataframe["target_result"] != diagnostic_dataframe["predicted_result"]
    ].copy()

    if errors_dataframe.empty:
        return pd.DataFrame(
            columns=[
                "target_result",
                "predicted_result",
                "error_count",
                "sample_match_ids",
            ]
        )

    grouped = (
        errors_dataframe.groupby(["target_result", "predicted_result"])
        .agg(
            error_count=("clean_match_id", "count"),
            sample_match_ids=("clean_match_id", lambda values: ", ".join(map(str, list(values)[:10]))),
        )
        .reset_index()
        .sort_values(by="error_count", ascending=False)
    )

    return grouped


# Extrait les erreurs liées aux matchs nuls.
def build_draw_errors(diagnostic_dataframe: pd.DataFrame) -> pd.DataFrame:
    draw_errors_dataframe = diagnostic_dataframe[
        (diagnostic_dataframe["target_result"] == "DRAW")
        & (diagnostic_dataframe["predicted_result"] != "DRAW")
    ].copy()

    columns = [
        "clean_match_id",
        "match_date_utc",
        "competition_code",
        "season",
        "team_a_name",
        "team_b_name",
        "target_result",
        "predicted_result",
        "elo_gap",
        "abs_elo_gap",
        "elo_gap_bucket",
        "is_neutral_venue",
        "host_advantage_side",
        "is_group_stage",
        "is_knockout_stage",
    ]

    return draw_errors_dataframe[columns].sort_values(
        by=["abs_elo_gap", "match_date_utc"],
        ascending=[True, False],
    )


# Exporte le CSV des segments.
def export_segments_csv(segment_rows: list[dict[str, object]]) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SEGMENTS_FILENAME

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "segment_name",
                "segment_value",
                "rows",
                "accuracy",
                "f1_macro",
                "team_a_win_rows",
                "draw_rows",
                "team_b_win_rows",
            ],
        )

        writer.writeheader()
        writer.writerows(segment_rows)

    return output_path


# Exporte le CSV des erreurs fréquentes.
def export_error_patterns_csv(error_patterns_dataframe: pd.DataFrame) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / ERRORS_FILENAME

    error_patterns_dataframe.to_csv(output_path, index=False, encoding="utf-8")

    return output_path


# Exporte le CSV des erreurs sur les matchs nuls.
def export_draw_errors_csv(draw_errors_dataframe: pd.DataFrame) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / DRAW_ERRORS_FILENAME

    draw_errors_dataframe.to_csv(output_path, index=False, encoding="utf-8")

    return output_path


# Exporte le résumé texte du diagnostic.
def export_summary_txt(
    diagnostic_dataframe: pd.DataFrame,
    global_metrics: dict[str, float],
    segment_rows: list[dict[str, object]],
    error_patterns_dataframe: pd.DataFrame,
    segments_path: Path,
    errors_path: Path,
    draw_errors_path: Path,
    args: argparse.Namespace,
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    report = classification_report(
        diagnostic_dataframe["target_result"],
        diagnostic_dataframe["predicted_result"],
        labels=TARGET_LABELS,
        zero_division=0,
        output_dict=True,
    )

    confusion = confusion_matrix(
        diagnostic_dataframe["target_result"],
        diagnostic_dataframe["predicted_result"],
        labels=TARGET_LABELS,
    )

    weakest_segments = sorted(
        [
            row
            for row in segment_rows
            if row["rows"] >= 50 and row["accuracy"] is not None
        ],
        key=lambda row: row["accuracy"],
    )[:10]

    strongest_segments = sorted(
        [
            row
            for row in segment_rows
            if row["rows"] >= 50 and row["accuracy"] is not None
        ],
        key=lambda row: row["accuracy"],
        reverse=True,
    )[:10]

    lines = [
        "OK - Diagnostic V17.9 national baseline terminé.",
        f"Feature version : {args.feature_version}",
        f"Fichier prédictions : {args.predictions_file}",
        f"Lignes analysées : {len(diagnostic_dataframe)}",
        f"Accuracy globale : {round(global_metrics['accuracy'], 4)}",
        f"F1 macro global : {round(global_metrics['f1_macro'], 4)}",
        f"F1 weighted global : {round(global_metrics['f1_weighted'], 4)}",
        "",
        "Scores par classe :",
    ]

    for label in TARGET_LABELS:
        metrics = report.get(label, {})
        lines.extend(
            [
                f"- {label}",
                f"  precision : {round(metrics.get('precision', 0), 4)}",
                f"  recall    : {round(metrics.get('recall', 0), 4)}",
                f"  f1-score  : {round(metrics.get('f1-score', 0), 4)}",
                f"  support   : {int(metrics.get('support', 0))}",
            ]
        )

    lines.extend(
        [
            "",
            "Confusion matrix :",
            "Labels : TEAM_A_WIN, DRAW, TEAM_B_WIN",
        ]
    )

    for row in confusion.tolist():
        lines.append(str(row))

    lines.extend(["", "Top 10 segments faibles avec au moins 50 lignes :"])

    for row in weakest_segments:
        lines.append(
            f"- {row['segment_name']}={row['segment_value']} | "
            f"rows={row['rows']} | accuracy={row['accuracy']} | f1_macro={row['f1_macro']}"
        )

    lines.extend(["", "Top 10 segments forts avec au moins 50 lignes :"])

    for row in strongest_segments:
        lines.append(
            f"- {row['segment_name']}={row['segment_value']} | "
            f"rows={row['rows']} | accuracy={row['accuracy']} | f1_macro={row['f1_macro']}"
        )

    lines.extend(["", "Erreurs les plus fréquentes :"])

    for _, row in error_patterns_dataframe.head(10).iterrows():
        lines.append(
            f"- réel={row['target_result']} -> prédit={row['predicted_result']} | "
            f"erreurs={row['error_count']}"
        )

    lines.extend(
        [
            "",
            f"CSV segments : {segments_path}",
            f"CSV erreurs fréquentes : {errors_path}",
            f"CSV erreurs DRAW : {draw_errors_path}",
            "",
            "Décision technique :",
            "- Le diagnostic doit être analysé avant toute intégration frontend.",
            "- StatsBomb reste une option d'enrichissement après observation des segments faibles.",
            "- Le point prioritaire à surveiller reste la prédiction des DRAW.",
            "- Le modèle national V17.9 ne remplace pas le modèle club V17.8.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path


# Affiche un résumé court dans le terminal.
def print_summary(
    diagnostic_dataframe: pd.DataFrame,
    global_metrics: dict[str, float],
    summary_path: Path,
    segments_path: Path,
) -> None:
    draw_dataframe = diagnostic_dataframe[diagnostic_dataframe["target_result"] == "DRAW"]
    draw_accuracy = accuracy_score(
        draw_dataframe["target_result"],
        draw_dataframe["predicted_result"],
    )

    print("OK - Diagnostic V17.9 national baseline terminé.")
    print(f"Lignes analysées : {len(diagnostic_dataframe)}")
    print(f"Accuracy globale : {round(global_metrics['accuracy'], 4)}")
    print(f"F1 macro global : {round(global_metrics['f1_macro'], 4)}")
    print(f"Accuracy sur les DRAW réels : {round(draw_accuracy, 4)}")
    print(f"Résumé sauvegardé : {summary_path}")
    print(f"Segments sauvegardés : {segments_path}")


# Exécute le diagnostic complet de la baseline nationale.
def main() -> None:
    try:
        args = parse_arguments()
        ensure_evidence_directory()

        predictions_dataframe = load_predictions(args.predictions_file)

        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            feature_dataframe = fetch_feature_context(
                connection=connection,
                feature_version=args.feature_version,
            )

        diagnostic_dataframe = build_diagnostic_dataframe(
            predictions_dataframe=predictions_dataframe,
            feature_dataframe=feature_dataframe,
        )

        global_metrics = build_global_metrics(diagnostic_dataframe)
        segment_rows = build_segment_diagnostics(diagnostic_dataframe)
        error_patterns_dataframe = build_error_patterns(diagnostic_dataframe)
        draw_errors_dataframe = build_draw_errors(diagnostic_dataframe)

        segments_path = export_segments_csv(segment_rows)
        errors_path = export_error_patterns_csv(error_patterns_dataframe)
        draw_errors_path = export_draw_errors_csv(draw_errors_dataframe)

        summary_path = export_summary_txt(
            diagnostic_dataframe=diagnostic_dataframe,
            global_metrics=global_metrics,
            segment_rows=segment_rows,
            error_patterns_dataframe=error_patterns_dataframe,
            segments_path=segments_path,
            errors_path=errors_path,
            draw_errors_path=draw_errors_path,
            args=args,
        )

        print_summary(
            diagnostic_dataframe=diagnostic_dataframe,
            global_metrics=global_metrics,
            summary_path=summary_path,
            segments_path=segments_path,
        )

    except Exception as error:
        print("Erreur pendant le diagnostic V17.9 national baseline.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# 306_national_v17_9_predictions.csv
#        ↓
# ml_national.features + ml_national.clean_matches
#        ↓
# backend/scripts/ml_national/diagnose_national_v17_9_baseline.py
#        ↓
# reports/evidence/ml_training/
#        ↓
# décision : améliorer baseline ou enrichir avec StatsBomb