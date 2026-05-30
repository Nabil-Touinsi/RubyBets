# Role du fichier :
# Ce script construit le dataset global V18.3 multi-market RubyBets.
# Il fusionne ml_national.clean_matches et ml_national.features pour exporter les targets 1X2, OVER_1_5, OVER_2_5 et BTTS sans utiliser StatsBomb.

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATHS = [PROJECT_ROOT / ".env", BACKEND_DIR / ".env"]

EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_FEATURE_VERSION = "national_v1_elo_form"
DEFAULT_COMPETITION_CODES = ["WC", "WCQ"]
DEFAULT_TEST_RATIO = 0.20

SUMMARY_FILENAME = "344_v18_3_global_multimarket_dataset_summary.txt"
DATASET_FILENAME = "345_v18_3_global_multimarket_dataset.csv"

VALID_1X2_LABELS = ["TEAM_A_WIN", "DRAW", "TEAM_B_WIN"]
BINARY_LABELS = ["YES", "NO"]

METADATA_COLUMNS = [
    "clean_match_id",
    "feature_id",
    "feature_version",
    "match_date_utc",
    "season",
    "competition_code",
    "competition_name",
    "stage",
    "group_name",
    "team_a_name",
    "team_b_name",
    "team_a_score",
    "team_b_score",
    "total_goals",
]

TARGET_COLUMNS = [
    "target_1x2",
    "target_over_1_5",
    "target_over_2_5",
    "target_btts",
]

FEATURE_COLUMNS = [
    "home_form_points_last_5",
    "away_form_points_last_5",
    "home_form_points_last_10",
    "away_form_points_last_10",
    "home_goals_scored_avg_last_10",
    "away_goals_scored_avg_last_10",
    "home_goals_conceded_avg_last_10",
    "away_goals_conceded_avg_last_10",
    "ranking_gap",
    "elo_gap",
    "is_neutral_venue",
    "team_a_is_host",
    "team_b_is_host",
    "host_side_team_a",
    "host_side_team_b",
    "is_group_stage",
    "is_knockout_stage",
]

EXPORT_COLUMNS = METADATA_COLUMNS + TARGET_COLUMNS + FEATURE_COLUMNS + ["split_role"]


# Charge les variables d'environnement depuis .env sans afficher de secret.
def load_env_files() -> None:
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue

        with env_path.open("r", encoding="utf-8") as env_file:
            for line in env_file:
                clean_line = line.strip()

                if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                    continue

                key, value = clean_line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Recupere l'URL PostgreSQL du projet.
def get_database_url() -> str:
    load_env_files()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL introuvable. Verifie .env ou backend/.env.")

    return database_url


# Prepare les arguments utilisables en ligne de commande.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Construire le dataset global multi-market RubyBets V18.3."
    )

    parser.add_argument(
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help="Version des features ml_national.features a exporter.",
    )

    parser.add_argument(
        "--competition-codes",
        default=",".join(DEFAULT_COMPETITION_CODES),
        help="Codes competition separes par des virgules. Utiliser ALL pour tout exporter.",
    )

    parser.add_argument(
        "--test-ratio",
        type=float,
        default=DEFAULT_TEST_RATIO,
        help="Part chronologique marquee comme test dans le CSV. Par defaut : 0.20.",
    )

    return parser.parse_args()


# Cree le dossier de preuves ML si necessaire.
def ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# Convertit une valeur PostgreSQL en valeur Python exportable.
def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value


# Convertit une valeur booleenne ou vide en indicateur numerique 0/1.
def to_binary_flag(value: Any) -> int:
    return 1 if bool(value) else 0


# Convertit l'argument competition-codes en liste propre.
def parse_competition_codes(raw_value: str) -> list[str]:
    if raw_value.strip().upper() == "ALL":
        return []

    return [
        code.strip().upper()
        for code in raw_value.split(",")
        if code.strip()
    ]


# Charge les matchs nationaux et leurs features globales depuis PostgreSQL.
def fetch_dataset_source_rows(
    connection: psycopg.Connection,
    feature_version: str,
    competition_codes: list[str],
) -> list[dict[str, Any]]:
    competition_filter = ""
    params: list[Any] = [feature_version]

    if competition_codes:
        competition_filter = "AND cm.competition_code = ANY(%s)"
        params.append(competition_codes)

    query = f"""
        SELECT
            cm.id AS clean_match_id,
            f.id AS feature_id,
            f.feature_version,
            cm.match_date_utc,
            cm.season,
            cm.competition_code,
            cm.competition_name,
            cm.stage,
            cm.group_name,
            cm.home_team_name AS team_a_name,
            cm.away_team_name AS team_b_name,
            cm.home_score AS team_a_score,
            cm.away_score AS team_b_score,
            cm.result_1x2,

            f.home_form_points_last_5,
            f.away_form_points_last_5,
            f.home_form_points_last_10,
            f.away_form_points_last_10,
            f.home_goals_scored_avg_last_10,
            f.away_goals_scored_avg_last_10,
            f.home_goals_conceded_avg_last_10,
            f.away_goals_conceded_avg_last_10,
            f.ranking_gap,
            f.elo_gap,
            f.is_neutral_venue,
            f.team_a_is_host,
            f.team_b_is_host,
            f.host_advantage_side,
            f.is_group_stage,
            f.is_knockout_stage,
            f.target_result AS feature_target_result
        FROM ml_national.clean_matches cm
        JOIN ml_national.features f
          ON f.clean_match_id = cm.id
        WHERE f.feature_version = %s
          AND cm.match_date_utc IS NOT NULL
          AND cm.home_team_name IS NOT NULL
          AND cm.away_team_name IS NOT NULL
          AND cm.home_score IS NOT NULL
          AND cm.away_score IS NOT NULL
          AND cm.result_1x2 IN ('TEAM_A_WIN', 'DRAW', 'TEAM_B_WIN')
          {competition_filter}
        ORDER BY cm.match_date_utc ASC, cm.id ASC
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [
        {key: normalize_value(value) for key, value in row.items()}
        for row in rows
    ]


# Calcule les targets multi-market a partir du score reel du match.
def build_market_targets(row: dict[str, Any]) -> dict[str, str]:
    team_a_score = int(row["team_a_score"])
    team_b_score = int(row["team_b_score"])
    total_goals = team_a_score + team_b_score

    return {
        "target_1x2": str(row["result_1x2"]),
        "target_over_1_5": "YES" if total_goals >= 2 else "NO",
        "target_over_2_5": "YES" if total_goals >= 3 else "NO",
        "target_btts": "YES" if team_a_score >= 1 and team_b_score >= 1 else "NO",
    }


# Construit une ligne CSV finale avec metadata, targets et features numeriques.
def build_dataset_row(row: dict[str, Any]) -> dict[str, Any]:
    targets = build_market_targets(row)
    team_a_score = int(row["team_a_score"])
    team_b_score = int(row["team_b_score"])
    host_advantage_side = row.get("host_advantage_side") or "NONE"

    output = {
        "clean_match_id": row.get("clean_match_id"),
        "feature_id": row.get("feature_id"),
        "feature_version": row.get("feature_version"),
        "match_date_utc": row.get("match_date_utc"),
        "season": row.get("season"),
        "competition_code": row.get("competition_code"),
        "competition_name": row.get("competition_name"),
        "stage": row.get("stage"),
        "group_name": row.get("group_name"),
        "team_a_name": row.get("team_a_name"),
        "team_b_name": row.get("team_b_name"),
        "team_a_score": team_a_score,
        "team_b_score": team_b_score,
        "total_goals": team_a_score + team_b_score,
        "target_1x2": targets["target_1x2"],
        "target_over_1_5": targets["target_over_1_5"],
        "target_over_2_5": targets["target_over_2_5"],
        "target_btts": targets["target_btts"],
        "home_form_points_last_5": row.get("home_form_points_last_5"),
        "away_form_points_last_5": row.get("away_form_points_last_5"),
        "home_form_points_last_10": row.get("home_form_points_last_10"),
        "away_form_points_last_10": row.get("away_form_points_last_10"),
        "home_goals_scored_avg_last_10": row.get("home_goals_scored_avg_last_10"),
        "away_goals_scored_avg_last_10": row.get("away_goals_scored_avg_last_10"),
        "home_goals_conceded_avg_last_10": row.get("home_goals_conceded_avg_last_10"),
        "away_goals_conceded_avg_last_10": row.get("away_goals_conceded_avg_last_10"),
        "ranking_gap": row.get("ranking_gap"),
        "elo_gap": row.get("elo_gap"),
        "is_neutral_venue": to_binary_flag(row.get("is_neutral_venue")),
        "team_a_is_host": to_binary_flag(row.get("team_a_is_host")),
        "team_b_is_host": to_binary_flag(row.get("team_b_is_host")),
        "host_side_team_a": 1 if host_advantage_side == "TEAM_A" else 0,
        "host_side_team_b": 1 if host_advantage_side == "TEAM_B" else 0,
        "is_group_stage": to_binary_flag(row.get("is_group_stage")),
        "is_knockout_stage": to_binary_flag(row.get("is_knockout_stage")),
    }

    return output


# Ajoute une colonne split_role selon un decoupage chronologique simple.
def assign_chronological_split(
    dataset_rows: list[dict[str, Any]],
    test_ratio: float,
) -> list[dict[str, Any]]:
    if not 0 < test_ratio < 0.5:
        raise ValueError("test_ratio doit etre compris entre 0 et 0.5.")

    if not dataset_rows:
        return []

    split_index = int(len(dataset_rows) * (1 - test_ratio))

    for index, row in enumerate(dataset_rows):
        row["split_role"] = "test" if index >= split_index else "train"

    return dataset_rows


# Construit toutes les lignes du dataset V18.3 global.
def build_dataset_rows(
    source_rows: list[dict[str, Any]],
    test_ratio: float,
) -> list[dict[str, Any]]:
    dataset_rows = [build_dataset_row(row) for row in source_rows]

    return assign_chronological_split(
        dataset_rows=dataset_rows,
        test_ratio=test_ratio,
    )


# Exporte le dataset V18.3 global en CSV.
def export_dataset_csv(dataset_rows: list[dict[str, Any]]) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / DATASET_FILENAME

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(dataset_rows)

    return output_path


# Compte les valeurs manquantes pour les features utiles du dataset.
def count_missing_features(dataset_rows: list[dict[str, Any]]) -> dict[str, int]:
    missing_counts: dict[str, int] = {}

    for column in FEATURE_COLUMNS:
        missing_counts[column] = sum(
            1
            for row in dataset_rows
            if row.get(column) is None or row.get(column) == ""
        )

    return missing_counts


# Calcule le nombre de lignes avec les features principales completes.
def count_complete_core_feature_rows(dataset_rows: list[dict[str, Any]]) -> int:
    core_columns = [
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "elo_gap",
    ]

    return sum(
        1
        for row in dataset_rows
        if all(row.get(column) is not None and row.get(column) != "" for column in core_columns)
    )


# Calcule un pourcentage securise.
def compute_percentage(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0

    return round((count / denominator) * 100, 2)


# Formate une distribution Counter pour le rapport texte.
def format_counter(counter: Counter, denominator: int, ordered_labels: list[str] | None = None) -> list[str]:
    labels = ordered_labels or sorted(counter.keys())
    lines = []

    for label in labels:
        count = counter.get(label, 0)
        percentage = compute_percentage(count, denominator)
        lines.append(f"- {label} : {count} ({percentage}%)")

    return lines


# Recupere les dates extremes des lignes exportees.
def get_date_range(dataset_rows: list[dict[str, Any]]) -> tuple[str, str]:
    dates = sorted(
        str(row.get("match_date_utc"))
        for row in dataset_rows
        if row.get("match_date_utc")
    )

    if not dates:
        return "N/A", "N/A"

    return dates[0], dates[-1]


# Exporte le rapport texte de synthese du dataset V18.3 global.
def export_summary(
    dataset_rows: list[dict[str, Any]],
    feature_version: str,
    competition_codes: list[str],
    test_ratio: float,
    dataset_csv_path: Path,
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    total_rows = len(dataset_rows)
    train_rows = sum(1 for row in dataset_rows if row.get("split_role") == "train")
    test_rows = sum(1 for row in dataset_rows if row.get("split_role") == "test")
    complete_core_features = count_complete_core_feature_rows(dataset_rows)
    missing_counts = count_missing_features(dataset_rows)

    competition_counter = Counter(row["competition_code"] for row in dataset_rows)
    season_counter = Counter(str(row.get("season") or "UNKNOWN") for row in dataset_rows)
    split_counter = Counter(row.get("split_role") for row in dataset_rows)

    target_counters = {
        "1X2": Counter(row["target_1x2"] for row in dataset_rows),
        "OVER_1_5": Counter(row["target_over_1_5"] for row in dataset_rows),
        "OVER_2_5": Counter(row["target_over_2_5"] for row in dataset_rows),
        "BTTS": Counter(row["target_btts"] for row in dataset_rows),
    }

    first_date, last_date = get_date_range(dataset_rows)
    competition_scope = ", ".join(competition_codes) if competition_codes else "ALL"

    lines = [
        "OK - Dataset V18.3 global multi-market genere.",
        "",
        "Contexte :",
        "- Phase : V18.3 national global multi-market.",
        "- Objectif : construire un CSV global pour entrainer ensuite 1X2, OVER_1_5, OVER_2_5 et BTTS.",
        "- StatsBomb : non utilise dans ce dataset global, car couverture limitee au sous-ensemble WC.",
        f"- Feature version utilisee : {feature_version}",
        f"- Competitions exportees : {competition_scope}",
        "",
        "Volume dataset :",
        f"- Lignes exportees : {total_rows}",
        f"- Colonnes exportees : {len(EXPORT_COLUMNS)}",
        f"- Train rows chronologiques : {train_rows} ({compute_percentage(train_rows, total_rows)}%)",
        f"- Test rows chronologiques : {test_rows} ({compute_percentage(test_rows, total_rows)}%)",
        f"- Test ratio demande : {test_ratio}",
        f"- Lignes avec core features completes : {complete_core_features} ({compute_percentage(complete_core_features, total_rows)}%)",
        "",
        "Periode couverte :",
        f"- Premiere date : {first_date}",
        f"- Derniere date : {last_date}",
        f"- Nombre de saisons distinctes : {len(season_counter)}",
        "",
        "Repartition competitions :",
    ]

    lines.extend(format_counter(competition_counter, total_rows))

    lines.extend(
        [
            "",
            "Repartition split train/test :",
        ]
    )
    lines.extend(format_counter(split_counter, total_rows, ["train", "test"]))

    lines.extend(
        [
            "",
            "Distribution target 1X2 :",
            *format_counter(target_counters["1X2"], total_rows, VALID_1X2_LABELS),
            "",
            "Distribution target OVER_1_5 :",
            *format_counter(target_counters["OVER_1_5"], total_rows, BINARY_LABELS),
            "",
            "Distribution target OVER_2_5 :",
            *format_counter(target_counters["OVER_2_5"], total_rows, BINARY_LABELS),
            "",
            "Distribution target BTTS :",
            *format_counter(target_counters["BTTS"], total_rows, BINARY_LABELS),
            "",
            "Features exportees :",
        ]
    )

    for feature_name in FEATURE_COLUMNS:
        lines.append(f"- {feature_name}")

    lines.extend(["", "Valeurs manquantes par feature :"])

    for feature_name in FEATURE_COLUMNS:
        missing_count = missing_counts.get(feature_name, 0)
        lines.append(
            f"- {feature_name} : {missing_count} ({compute_percentage(missing_count, total_rows)}%)"
        )

    lines.extend(
        [
            "",
            "Fichiers generes :",
            f"- Synthese : {output_path}",
            f"- Dataset CSV : {dataset_csv_path}",
            "",
            "Decision technique :",
            "- Le dataset V18.3 global est pret pour la baseline multi-market globale.",
            "- DOUBLE_CHANCE ne sera pas entrainee comme target separee : elle sera derivee des probabilites 1X2.",
            "- ABSTAIN sera produit plus tard par le selecteur selon les seuils de confiance et de fiabilite.",
            "- Les colonnes home_* et away_* representent Team A / Team B dans ce pipeline national.",
            "- Le dataset reste experimental et ne promet aucun resultat sportif.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# Affiche un resume court dans le terminal.
def print_summary(
    dataset_rows: list[dict[str, Any]],
    summary_path: Path,
    dataset_csv_path: Path,
) -> None:
    total_rows = len(dataset_rows)
    train_rows = sum(1 for row in dataset_rows if row.get("split_role") == "train")
    test_rows = sum(1 for row in dataset_rows if row.get("split_role") == "test")

    print("OK - Dataset V18.3 global multi-market genere.")
    print(f"Lignes exportees : {total_rows}")
    print(f"Train rows : {train_rows}")
    print(f"Test rows : {test_rows}")
    print(f"Summary saved: {summary_path}")
    print(f"Dataset CSV saved: {dataset_csv_path}")


# Orchestre la construction du dataset global V18.3 et ses preuves.
def main() -> None:
    try:
        args = parse_arguments()
        competition_codes = parse_competition_codes(args.competition_codes)
        ensure_evidence_directory()

        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            source_rows = fetch_dataset_source_rows(
                connection=connection,
                feature_version=args.feature_version,
                competition_codes=competition_codes,
            )

        if not source_rows:
            raise ValueError("Aucune ligne exploitable trouvee pour construire le dataset V18.3.")

        dataset_rows = build_dataset_rows(
            source_rows=source_rows,
            test_ratio=args.test_ratio,
        )

        dataset_csv_path = export_dataset_csv(dataset_rows)

        summary_path = export_summary(
            dataset_rows=dataset_rows,
            feature_version=args.feature_version,
            competition_codes=competition_codes,
            test_ratio=args.test_ratio,
            dataset_csv_path=dataset_csv_path,
        )

        print_summary(
            dataset_rows=dataset_rows,
            summary_path=summary_path,
            dataset_csv_path=dataset_csv_path,
        )

    except Exception as error:
        print("Erreur pendant la construction du dataset V18.3 global multi-market.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schema de communication :
# backend/.env ou .env
#     ↓
# PostgreSQL ml_national.clean_matches + ml_national.features
#     ↓
# build_v18_3_global_multimarket_dataset.py
#     ↓
# reports/evidence/ml_training/344_v18_3_global_multimarket_dataset_summary.txt
# reports/evidence/ml_training/345_v18_3_global_multimarket_dataset.csv
#     ↓
# futur train_v18_3_global_multimarket_models.py
