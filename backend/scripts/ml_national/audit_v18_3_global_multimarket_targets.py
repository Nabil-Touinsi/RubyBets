# Role du fichier :
# Ce script audite les cibles multi-market V18.3 sur la base nationale RubyBets.
# Il mesure les distributions 1X2, OVER_1_5, OVER_2_5, BTTS et la couverture WC/WCQ sans utiliser StatsBomb.

from __future__ import annotations

import argparse
import csv
import os
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

SUMMARY_FILENAME = "342_v18_3_global_multimarket_targets_summary.txt"
DISTRIBUTION_FILENAME = "343_v18_3_global_multimarket_targets_distribution.csv"

VALID_1X2_LABELS = ["TEAM_A_WIN", "DRAW", "TEAM_B_WIN"]
BINARY_LABELS = ["YES", "NO"]


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
        description="Auditer les targets globales multi-market RubyBets V18.3."
    )

    parser.add_argument(
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help="Version des features ml_national.features a auditer.",
    )

    parser.add_argument(
        "--competition-codes",
        default=",".join(DEFAULT_COMPETITION_CODES),
        help="Codes competition separes par des virgules. Utiliser ALL pour tout auditer.",
    )

    return parser.parse_args()


# Cree le dossier de preuves ML si necessaire.
def ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# Convertit une valeur PostgreSQL en valeur Python exploitable.
def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value


# Convertit l'argument competition-codes en liste propre.
def parse_competition_codes(raw_value: str) -> list[str]:
    if raw_value.strip().upper() == "ALL":
        return []

    return [
        code.strip().upper()
        for code in raw_value.split(",")
        if code.strip()
    ]


# Charge les matchs clean et indique si la feature demandee existe.
def fetch_audit_rows(
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
            cm.competition_code,
            cm.competition_name,
            cm.season,
            cm.match_date_utc,
            cm.stage,
            cm.group_name,
            cm.home_team_name AS team_a_name,
            cm.away_team_name AS team_b_name,
            cm.home_score AS team_a_score,
            cm.away_score AS team_b_score,
            cm.result_1x2,
            cm.is_group_stage,
            cm.is_knockout_stage,
            f.id AS feature_id,
            f.feature_version
        FROM ml_national.clean_matches cm
        LEFT JOIN ml_national.features f
            ON f.clean_match_id = cm.id
           AND f.feature_version = %s
        WHERE cm.match_date_utc IS NOT NULL
          AND cm.home_team_name IS NOT NULL
          AND cm.away_team_name IS NOT NULL
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


# Verifie si un match possede les deux scores necessaires aux targets goals/BTTS.
def has_complete_score(row: dict[str, Any]) -> bool:
    return row.get("team_a_score") is not None and row.get("team_b_score") is not None


# Verifie si le resultat 1X2 est exploitable.
def has_valid_1x2(row: dict[str, Any]) -> bool:
    return row.get("result_1x2") in VALID_1X2_LABELS


# Verifie si une ligne de features existe pour la version demandee.
def has_feature(row: dict[str, Any]) -> bool:
    return row.get("feature_id") is not None


# Verifie si un match peut entrer dans le dataset V18.3 global.
def is_exploitable_match(row: dict[str, Any]) -> bool:
    return has_complete_score(row) and has_valid_1x2(row) and has_feature(row)


# Calcule le total de buts d'un match.
def get_total_goals(row: dict[str, Any]) -> int:
    return int(row["team_a_score"]) + int(row["team_b_score"])


# Calcule les targets multi-market derivees du score reel.
def build_market_targets(row: dict[str, Any]) -> dict[str, str]:
    total_goals = get_total_goals(row)
    team_a_score = int(row["team_a_score"])
    team_b_score = int(row["team_b_score"])

    return {
        "target_1x2": str(row["result_1x2"]),
        "target_over_1_5": "YES" if total_goals >= 2 else "NO",
        "target_over_2_5": "YES" if total_goals >= 3 else "NO",
        "target_btts": "YES" if team_a_score >= 1 and team_b_score >= 1 else "NO",
    }


# Calcule un pourcentage securise.
def compute_percentage(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0

    return round((count / denominator) * 100, 2)


# Ajoute une ligne normalisee au CSV de distribution.
def append_distribution_row(
    rows: list[dict[str, Any]],
    section: str,
    segment_type: str,
    segment_value: str,
    target_name: str,
    class_label: str,
    match_count: int,
    denominator: int,
) -> None:
    rows.append(
        {
            "section": section,
            "segment_type": segment_type,
            "segment_value": segment_value,
            "target_name": target_name,
            "class_label": class_label,
            "match_count": match_count,
            "percentage": compute_percentage(match_count, denominator),
            "denominator": denominator,
        }
    )


# Construit toutes les lignes de distribution exportees en CSV.
def build_distribution_rows(
    all_rows: list[dict[str, Any]],
    exploitable_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    distribution_rows: list[dict[str, Any]] = []
    total_rows = len(all_rows)
    exploitable_count = len(exploitable_rows)

    scores_complete_count = sum(has_complete_score(row) for row in all_rows)
    valid_1x2_count = sum(has_valid_1x2(row) for row in all_rows)
    feature_count = sum(has_feature(row) for row in all_rows)

    quality_items = {
        "total_clean_matches": total_rows,
        "scores_complete": scores_complete_count,
        "valid_1x2_result": valid_1x2_count,
        "feature_available": feature_count,
        "exploitable_v18_3": exploitable_count,
        "not_exploitable_v18_3": total_rows - exploitable_count,
    }

    for label, count in quality_items.items():
        append_distribution_row(
            distribution_rows,
            section="data_quality",
            segment_type="ALL",
            segment_value="ALL",
            target_name="match_availability",
            class_label=label,
            match_count=count,
            denominator=total_rows,
        )

    competition_counter = Counter(row["competition_code"] for row in exploitable_rows)
    for competition_code, count in sorted(competition_counter.items()):
        append_distribution_row(
            distribution_rows,
            section="competition_distribution",
            segment_type="competition_code",
            segment_value=competition_code,
            target_name="competition_scope",
            class_label=competition_code,
            match_count=count,
            denominator=exploitable_count,
        )

    season_counter = Counter(str(row.get("season") or "UNKNOWN") for row in exploitable_rows)
    for season, count in sorted(season_counter.items()):
        append_distribution_row(
            distribution_rows,
            section="temporal_distribution",
            segment_type="season",
            segment_value=season,
            target_name="season_scope",
            class_label=season,
            match_count=count,
            denominator=exploitable_count,
        )

    target_counters = {
        "target_1x2": Counter(),
        "target_over_1_5": Counter(),
        "target_over_2_5": Counter(),
        "target_btts": Counter(),
    }

    for row in exploitable_rows:
        targets = build_market_targets(row)
        for target_name, target_value in targets.items():
            target_counters[target_name][target_value] += 1

    ordered_labels_by_target = {
        "target_1x2": VALID_1X2_LABELS,
        "target_over_1_5": BINARY_LABELS,
        "target_over_2_5": BINARY_LABELS,
        "target_btts": BINARY_LABELS,
    }

    for target_name, labels in ordered_labels_by_target.items():
        for label in labels:
            append_distribution_row(
                distribution_rows,
                section="target_distribution",
                segment_type="ALL",
                segment_value="ALL",
                target_name=target_name,
                class_label=label,
                match_count=target_counters[target_name].get(label, 0),
                denominator=exploitable_count,
            )

    for competition_code in sorted(competition_counter):
        competition_rows = [
            row
            for row in exploitable_rows
            if row.get("competition_code") == competition_code
        ]

        for target_name, labels in ordered_labels_by_target.items():
            counter = Counter(
                build_market_targets(row)[target_name]
                for row in competition_rows
            )

            for label in labels:
                append_distribution_row(
                    distribution_rows,
                    section="target_by_competition",
                    segment_type="competition_code",
                    segment_value=competition_code,
                    target_name=target_name,
                    class_label=label,
                    match_count=counter.get(label, 0),
                    denominator=len(competition_rows),
                )

    return distribution_rows


# Exporte le CSV de distribution V18.3.
def export_distribution_csv(distribution_rows: list[dict[str, Any]]) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / DISTRIBUTION_FILENAME

    fieldnames = [
        "section",
        "segment_type",
        "segment_value",
        "target_name",
        "class_label",
        "match_count",
        "percentage",
        "denominator",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(distribution_rows)

    return output_path


# Formate une distribution Counter pour le rapport texte.
def format_counter(counter: Counter, denominator: int, ordered_labels: list[str] | None = None) -> list[str]:
    labels = ordered_labels or sorted(counter.keys())
    lines = []

    for label in labels:
        count = counter.get(label, 0)
        percentage = compute_percentage(count, denominator)
        lines.append(f"- {label} : {count} ({percentage}%)")

    return lines


# Recupere les dates extremes des matchs exploitables.
def get_date_range(exploitable_rows: list[dict[str, Any]]) -> tuple[str, str]:
    dates = sorted(
        str(row.get("match_date_utc"))
        for row in exploitable_rows
        if row.get("match_date_utc")
    )

    if not dates:
        return "N/A", "N/A"

    return dates[0], dates[-1]


# Exporte le rapport texte de synthese V18.3.
def export_summary(
    all_rows: list[dict[str, Any]],
    exploitable_rows: list[dict[str, Any]],
    feature_version: str,
    competition_codes: list[str],
    distribution_csv_path: Path,
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    total_rows = len(all_rows)
    exploitable_count = len(exploitable_rows)
    scores_complete_count = sum(has_complete_score(row) for row in all_rows)
    valid_1x2_count = sum(has_valid_1x2(row) for row in all_rows)
    feature_count = sum(has_feature(row) for row in all_rows)
    missing_score_count = total_rows - scores_complete_count
    missing_feature_count = total_rows - feature_count

    competition_counter = Counter(row["competition_code"] for row in exploitable_rows)
    season_counter = Counter(str(row.get("season") or "UNKNOWN") for row in exploitable_rows)

    target_counters = {
        "1X2": Counter(),
        "OVER_1_5": Counter(),
        "OVER_2_5": Counter(),
        "BTTS": Counter(),
    }

    for row in exploitable_rows:
        targets = build_market_targets(row)
        target_counters["1X2"][targets["target_1x2"]] += 1
        target_counters["OVER_1_5"][targets["target_over_1_5"]] += 1
        target_counters["OVER_2_5"][targets["target_over_2_5"]] += 1
        target_counters["BTTS"][targets["target_btts"]] += 1

    first_date, last_date = get_date_range(exploitable_rows)
    competition_scope = ", ".join(competition_codes) if competition_codes else "ALL"
    expected_volume_note = "OK" if exploitable_count >= 9000 else "A VERIFIER"

    lines = [
        "OK - Audit V18.3 global multi-market targets termine.",
        "",
        "Contexte :",
        "- Phase : V18.3 national global multi-market.",
        "- Objectif : auditer les targets 1X2, OVER_1_5, OVER_2_5 et BTTS sur ml_national.",
        "- StatsBomb : non utilise dans cet audit global, car couverture limitee au sous-ensemble WC.",
        f"- Feature version auditee : {feature_version}",
        f"- Competitions auditees : {competition_scope}",
        "",
        "Qualite et exploitabilite :",
        f"- Matchs clean charges : {total_rows}",
        f"- Matchs avec scores complets : {scores_complete_count} ({compute_percentage(scores_complete_count, total_rows)}%)",
        f"- Matchs sans scores complets : {missing_score_count} ({compute_percentage(missing_score_count, total_rows)}%)",
        f"- Matchs avec resultat 1X2 valide : {valid_1x2_count} ({compute_percentage(valid_1x2_count, total_rows)}%)",
        f"- Matchs avec features {feature_version} : {feature_count} ({compute_percentage(feature_count, total_rows)}%)",
        f"- Matchs sans features {feature_version} : {missing_feature_count} ({compute_percentage(missing_feature_count, total_rows)}%)",
        f"- Matchs exploitables V18.3 : {exploitable_count} ({compute_percentage(exploitable_count, total_rows)}%)",
        f"- Controle volume attendu ~9 735 matchs : {expected_volume_note}",
        "",
        "Periode couverte :",
        f"- Premiere date exploitable : {first_date}",
        f"- Derniere date exploitable : {last_date}",
        f"- Nombre de saisons distinctes : {len(season_counter)}",
        "",
        "Repartition WC / WCQ :",
    ]

    lines.extend(format_counter(competition_counter, exploitable_count))

    lines.extend(
        [
            "",
            "Distribution 1X2 :",
            *format_counter(target_counters["1X2"], exploitable_count, VALID_1X2_LABELS),
            "",
            "Distribution OVER_1_5 :",
            *format_counter(target_counters["OVER_1_5"], exploitable_count, BINARY_LABELS),
            "",
            "Distribution OVER_2_5 :",
            *format_counter(target_counters["OVER_2_5"], exploitable_count, BINARY_LABELS),
            "",
            "Distribution BTTS :",
            *format_counter(target_counters["BTTS"], exploitable_count, BINARY_LABELS),
            "",
            "Fichiers generes :",
            f"- Synthese : {output_path}",
            f"- Distribution CSV : {distribution_csv_path}",
            "",
            "Decision technique :",
            "- Cet audit valide la disponibilite des targets avant entrainement V18.3.",
            "- DOUBLE_CHANCE ne doit pas etre entrainee comme target separee : elle sera derivee des probabilites 1X2.",
            "- ABSTAIN ne vient pas du score reel : il sera produit plus tard par le selecteur selon les seuils de confiance.",
        ]
    )

    with output_path.open("w", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(lines))

    return output_path


# Orchestre l'audit global et les exports de preuves.
def main() -> None:
    args = parse_arguments()
    competition_codes = parse_competition_codes(args.competition_codes)

    database_url = get_database_url()
    ensure_evidence_directory()

    with psycopg.connect(database_url) as connection:
        all_rows = fetch_audit_rows(
            connection=connection,
            feature_version=args.feature_version,
            competition_codes=competition_codes,
        )

    exploitable_rows = [row for row in all_rows if is_exploitable_match(row)]

    distribution_rows = build_distribution_rows(
        all_rows=all_rows,
        exploitable_rows=exploitable_rows,
    )

    distribution_csv_path = export_distribution_csv(distribution_rows)

    summary_path = export_summary(
        all_rows=all_rows,
        exploitable_rows=exploitable_rows,
        feature_version=args.feature_version,
        competition_codes=competition_codes,
        distribution_csv_path=distribution_csv_path,
    )

    print("OK - Audit V18.3 global multi-market targets termine.")
    print(f"Matchs charges : {len(all_rows)}")
    print(f"Matchs exploitables V18.3 : {len(exploitable_rows)}")
    print(f"Summary saved: {summary_path}")
    print(f"Distribution CSV saved: {distribution_csv_path}")


if __name__ == "__main__":
    main()


# Schema de communication :
# backend/.env ou .env
#     ↓
# PostgreSQL ml_national.clean_matches + ml_national.features
#     ↓
# audit_v18_3_global_multimarket_targets.py
#     ↓
# reports/evidence/ml_training/342_v18_3_global_multimarket_targets_summary.txt
# reports/evidence/ml_training/343_v18_3_global_multimarket_targets_distribution.csv
