# Role du fichier :
# Ce script audite l'alignement entre les matchs nationaux Kaggle/Elo en base PostgreSQL
# et les features rolling StatsBomb afin de preparer la phase V18.1 enriched multimarket.

from __future__ import annotations

import csv
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[3]

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"

STATSBOMB_ROLLING_CSV = EVIDENCE_DIR / "326_statsbomb_national_rolling_features.csv"

SUMMARY_FILE = EVIDENCE_DIR / "330_v18_1_kaggle_statsbomb_alignment_summary.txt"
OUTPUT_CSV = EVIDENCE_DIR / "331_v18_1_kaggle_statsbomb_alignment_matches.csv"


# Cette fonction charge les variables d'environnement depuis .env si disponible.
def load_env_files() -> None:
    env_paths = [
        ROOT_DIR / ".env",
        ROOT_DIR / "backend" / ".env",
    ]

    for env_path in env_paths:
        if not env_path.exists():
            continue

        with env_path.open("r", encoding="utf-8") as file:
            for line in file:
                clean_line = line.strip()

                if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                    continue

                key, value = clean_line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                os.environ.setdefault(key, value)


# Cette fonction recupere l'URL PostgreSQL du projet.
def get_database_url() -> str:
    load_env_files()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL introuvable. Verifie le fichier .env ou backend/.env."
        )

    return database_url


# Cette fonction quote proprement un identifiant SQL.
def qident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


# Cette fonction recupere les colonnes d'une table PostgreSQL.
def get_table_columns(connection: psycopg.Connection, schema: str, table: str) -> set[str]:
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (schema, table))
        return {str(row["column_name"]) for row in cursor.fetchall()}


# Cette fonction choisit la premiere colonne disponible dans une liste de candidates.
def pick_column(columns: set[str], candidates: list[str], label: str) -> str:
    for candidate in candidates:
        if candidate in columns:
            return candidate

    raise RuntimeError(f"Colonne introuvable pour {label}. Candidates : {candidates}")


# Cette fonction cree une expression SELECT securisee selon la colonne disponible.
def select_optional(
    alias: str,
    columns: set[str],
    candidates: list[str],
    output_name: str,
    default_sql: str = "NULL",
) -> str:
    for candidate in candidates:
        if candidate in columns:
            return f"{alias}.{qident(candidate)} AS {qident(output_name)}"

    return f"{default_sql} AS {qident(output_name)}"


# Cette fonction charge les lignes Kaggle/Elo depuis ml_national.features + clean_matches.
def load_kaggle_elo_rows() -> list[dict[str, Any]]:
    database_url = get_database_url()

    with psycopg.connect(database_url) as connection:
        clean_columns = get_table_columns(connection, "ml_national", "clean_matches")
        feature_columns = get_table_columns(connection, "ml_national", "features")

        clean_pk = "clean_match_id" if "clean_match_id" in clean_columns else "id"

        if "clean_match_id" not in feature_columns:
            raise RuntimeError("La table ml_national.features ne contient pas clean_match_id.")

        date_col = pick_column(
            clean_columns,
            ["match_date_utc", "match_date", "date"],
            "date match",
        )

        team_a_col = pick_column(
            clean_columns,
            ["team_a_name", "home_team_name"],
            "equipe A",
        )

        team_b_col = pick_column(
            clean_columns,
            ["team_b_name", "away_team_name"],
            "equipe B",
        )

        score_a_col = pick_column(
            clean_columns,
            ["team_a_score", "home_score"],
            "score equipe A",
        )

        score_b_col = pick_column(
            clean_columns,
            ["team_b_score", "away_score"],
            "score equipe B",
        )

        select_parts = [
            f"cm.{qident(clean_pk)} AS clean_match_id",
            select_optional("f", feature_columns, ["feature_id", "id"], "feature_id"),
            f"cm.{qident(date_col)} AS match_date",
            f"cm.{qident(team_a_col)} AS team_a_name",
            f"cm.{qident(team_b_col)} AS team_b_name",
            f"cm.{qident(score_a_col)} AS team_a_score",
            f"cm.{qident(score_b_col)} AS team_b_score",
            select_optional(
                "cm",
                clean_columns,
                ["competition_name", "tournament", "competition", "competition_code"],
                "competition_name",
            ),
            select_optional(
                "cm",
                clean_columns,
                ["result_1x2", "target_result"],
                "result_1x2",
            ),
            select_optional(
                "f",
                feature_columns,
                ["feature_version"],
                "feature_version",
            ),
            select_optional(
                "f",
                feature_columns,
                ["elo_gap", "abs_elo_gap"],
                "elo_gap",
                default_sql="0",
            ),
        ]

        where_clause = ""
        if "feature_version" in feature_columns:
            where_clause = "WHERE f.feature_version = 'national_v1_elo_form'"

        query = f"""
            SELECT
                {", ".join(select_parts)}
            FROM ml_national.features f
            JOIN ml_national.clean_matches cm
              ON f.clean_match_id = cm.{qident(clean_pk)}
            {where_clause}
        """

        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            rows = [dict(row) for row in cursor.fetchall()]

    return rows


# Cette fonction charge les features rolling StatsBomb.
def load_statsbomb_rows() -> list[dict[str, Any]]:
    if not STATSBOMB_ROLLING_CSV.exists():
        raise FileNotFoundError(f"Fichier introuvable : {STATSBOMB_ROLLING_CSV}")

    with STATSBOMB_ROLLING_CSV.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


# Cette fonction normalise un nom d'equipe pour faciliter l'alignement.
def normalize_team_name(name: Any) -> str:
    text = str(name or "").strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))

    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    aliases = {
        "usa": "united states",
        "u s a": "united states",
        "united states of america": "united states",
        "korea republic": "south korea",
        "republic of korea": "south korea",
        "ir iran": "iran",
        "islamic republic of iran": "iran",
        "turkiye": "turkey",
        "czechia": "czech republic",
        "cote d ivoire": "ivory coast",
        "cote divoire": "ivory coast",
        "bosnia and herzegovina": "bosnia herzegovina",
        "north macedonia": "macedonia",
        "republic of ireland": "ireland",
    }

    return aliases.get(text, text)


# Cette fonction transforme une date en format YYYY-MM-DD.
def normalize_date(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    return text[:10]


# Cette fonction convertit une valeur score en entier.
def to_int(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


# Cette fonction indexe les lignes Kaggle/Elo par date pour accelerer l'alignement.
def index_kaggle_rows_by_date(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        date_key = normalize_date(row.get("match_date"))
        index.setdefault(date_key, []).append(row)

    return index


# Cette fonction verifie si deux matchs correspondent en sens direct.
def is_direct_match(statsbomb_row: dict[str, Any], kaggle_row: dict[str, Any]) -> bool:
    return (
        normalize_team_name(statsbomb_row.get("team_a_name"))
        == normalize_team_name(kaggle_row.get("team_a_name"))
        and normalize_team_name(statsbomb_row.get("team_b_name"))
        == normalize_team_name(kaggle_row.get("team_b_name"))
        and to_int(statsbomb_row.get("team_a_score")) == to_int(kaggle_row.get("team_a_score"))
        and to_int(statsbomb_row.get("team_b_score")) == to_int(kaggle_row.get("team_b_score"))
    )


# Cette fonction verifie si deux matchs correspondent en sens inverse.
def is_reversed_match(statsbomb_row: dict[str, Any], kaggle_row: dict[str, Any]) -> bool:
    return (
        normalize_team_name(statsbomb_row.get("team_a_name"))
        == normalize_team_name(kaggle_row.get("team_b_name"))
        and normalize_team_name(statsbomb_row.get("team_b_name"))
        == normalize_team_name(kaggle_row.get("team_a_name"))
        and to_int(statsbomb_row.get("team_a_score")) == to_int(kaggle_row.get("team_b_score"))
        and to_int(statsbomb_row.get("team_b_score")) == to_int(kaggle_row.get("team_a_score"))
    )


# Cette fonction aligne une ligne StatsBomb avec les lignes Kaggle/Elo candidates.
def align_one_match(
    statsbomb_row: dict[str, Any],
    kaggle_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    date_key = normalize_date(statsbomb_row.get("match_date"))
    candidates = kaggle_index.get(date_key, [])

    direct_matches = [row for row in candidates if is_direct_match(statsbomb_row, row)]
    reversed_matches = [row for row in candidates if is_reversed_match(statsbomb_row, row)]

    all_matches = direct_matches + reversed_matches

    if len(all_matches) == 1:
        matched_row = all_matches[0]
        alignment_status = "matched_direct" if direct_matches else "matched_reversed"
        alignment_reason = "date_team_score_match"

    elif len(all_matches) > 1:
        matched_row = all_matches[0]
        alignment_status = "ambiguous"
        alignment_reason = f"{len(all_matches)} candidates matched"

    else:
        matched_row = {}
        alignment_status = "unmatched"
        alignment_reason = f"no exact match on date/team/score; same_date_candidates={len(candidates)}"

    return {
        "alignment_status": alignment_status,
        "alignment_reason": alignment_reason,
        "statsbomb_match_id": statsbomb_row.get("statsbomb_match_id"),
        "statsbomb_competition_name": statsbomb_row.get("competition_name"),
        "statsbomb_season_name": statsbomb_row.get("season_name"),
        "match_date": date_key,
        "statsbomb_team_a_name": statsbomb_row.get("team_a_name"),
        "statsbomb_team_b_name": statsbomb_row.get("team_b_name"),
        "statsbomb_team_a_score": statsbomb_row.get("team_a_score"),
        "statsbomb_team_b_score": statsbomb_row.get("team_b_score"),
        "clean_match_id": matched_row.get("clean_match_id", ""),
        "feature_id": matched_row.get("feature_id", ""),
        "kaggle_competition_name": matched_row.get("competition_name", ""),
        "kaggle_team_a_name": matched_row.get("team_a_name", ""),
        "kaggle_team_b_name": matched_row.get("team_b_name", ""),
        "kaggle_team_a_score": matched_row.get("team_a_score", ""),
        "kaggle_team_b_score": matched_row.get("team_b_score", ""),
        "result_1x2": matched_row.get("result_1x2", ""),
        "feature_version": matched_row.get("feature_version", ""),
        "elo_gap": matched_row.get("elo_gap", ""),
        "target_over_1_5": statsbomb_row.get("target_over_1_5"),
        "target_over_2_5": statsbomb_row.get("target_over_2_5"),
        "target_btts": statsbomb_row.get("target_btts"),
        "team_a_xg_for_last_5": statsbomb_row.get("team_a_xg_for_last_5"),
        "team_b_xg_for_last_5": statsbomb_row.get("team_b_xg_for_last_5"),
        "team_a_shots_for_last_5": statsbomb_row.get("team_a_shots_for_last_5"),
        "team_b_shots_for_last_5": statsbomb_row.get("team_b_shots_for_last_5"),
        "team_a_shots_on_target_for_last_5": statsbomb_row.get("team_a_shots_on_target_for_last_5"),
        "team_b_shots_on_target_for_last_5": statsbomb_row.get("team_b_shots_on_target_for_last_5"),
        "team_a_statsbomb_history_count": statsbomb_row.get("team_a_statsbomb_history_count"),
        "team_b_statsbomb_history_count": statsbomb_row.get("team_b_statsbomb_history_count"),
    }


# Cette fonction aligne toutes les lignes StatsBomb avec Kaggle/Elo.
def build_alignment_rows(
    statsbomb_rows: list[dict[str, Any]],
    kaggle_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kaggle_index = index_kaggle_rows_by_date(kaggle_rows)

    return [
        align_one_match(statsbomb_row, kaggle_index)
        for statsbomb_row in statsbomb_rows
    ]


# Cette fonction sauvegarde le CSV d'alignement.
def save_alignment_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "alignment_status",
        "alignment_reason",
        "statsbomb_match_id",
        "statsbomb_competition_name",
        "statsbomb_season_name",
        "match_date",
        "statsbomb_team_a_name",
        "statsbomb_team_b_name",
        "statsbomb_team_a_score",
        "statsbomb_team_b_score",
        "clean_match_id",
        "feature_id",
        "kaggle_competition_name",
        "kaggle_team_a_name",
        "kaggle_team_b_name",
        "kaggle_team_a_score",
        "kaggle_team_b_score",
        "result_1x2",
        "feature_version",
        "elo_gap",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "team_a_xg_for_last_5",
        "team_b_xg_for_last_5",
        "team_a_shots_for_last_5",
        "team_b_shots_for_last_5",
        "team_a_shots_on_target_for_last_5",
        "team_b_shots_on_target_for_last_5",
        "team_a_statsbomb_history_count",
        "team_b_statsbomb_history_count",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction calcule un ratio securise.
def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0

    return round(float(numerator) / float(denominator), 4)


# Cette fonction sauvegarde la synthese de l'audit d'alignement.
def save_summary(
    statsbomb_rows: list[dict[str, Any]],
    kaggle_rows: list[dict[str, Any]],
    alignment_rows: list[dict[str, Any]],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    total_statsbomb = len(statsbomb_rows)
    total_kaggle = len(kaggle_rows)

    matched_direct = sum(1 for row in alignment_rows if row["alignment_status"] == "matched_direct")
    matched_reversed = sum(1 for row in alignment_rows if row["alignment_status"] == "matched_reversed")
    ambiguous = sum(1 for row in alignment_rows if row["alignment_status"] == "ambiguous")
    unmatched = sum(1 for row in alignment_rows if row["alignment_status"] == "unmatched")

    matched_total = matched_direct + matched_reversed

    matched_by_competition: dict[str, int] = {}
    total_by_competition: dict[str, int] = {}

    for row in alignment_rows:
        competition = str(row["statsbomb_competition_name"])
        season = str(row["statsbomb_season_name"])
        key = f"{competition} {season}"

        total_by_competition[key] = total_by_competition.get(key, 0) + 1

        if row["alignment_status"] in {"matched_direct", "matched_reversed"}:
            matched_by_competition[key] = matched_by_competition.get(key, 0) + 1

    lines = [
        "RubyBets - Audit alignement V18.1 Kaggle + Elo + StatsBomb",
        "",
        f"Source StatsBomb rolling : {STATSBOMB_ROLLING_CSV}",
        f"Fichier d'alignement genere : {OUTPUT_CSV}",
        "",
        "Objectif :",
        "Verifier combien de matchs StatsBomb rolling peuvent etre relies proprement",
        "aux features nationales Kaggle + Elo deja presentes dans PostgreSQL.",
        "",
        "Resultats globaux :",
        f"- Lignes StatsBomb rolling : {total_statsbomb}",
        f"- Lignes Kaggle/Elo chargees depuis ml_national.features : {total_kaggle}",
        f"- Matchs alignes directs : {matched_direct}",
        f"- Matchs alignes inverses : {matched_reversed}",
        f"- Matchs alignes total : {matched_total} / {total_statsbomb} ({safe_ratio(matched_total, total_statsbomb)})",
        f"- Matchs ambigus : {ambiguous}",
        f"- Matchs non alignes : {unmatched}",
        "",
        "Alignement par competition StatsBomb :",
    ]

    for key in sorted(total_by_competition):
        total = total_by_competition[key]
        matched = matched_by_competition.get(key, 0)
        lines.append(f"- {key}: {matched} / {total} ({safe_ratio(matched, total)})")

    lines.extend(
        [
            "",
            "Decision attendue apres lecture :",
            "- Si le volume aligne est suffisant, construire un dataset V18.1 enriched.",
            "- Si seuls les matchs Coupe du Monde s'alignent, limiter V18.1 au perimetre WC enrichi.",
            "- Ne pas fusionner les matchs non alignes pour eviter une erreur de donnees.",
            "- StatsBomb reste un enrichissement rolling anti-fuite, pas le socle principal.",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance l'audit complet d'alignement V18.1.
def main() -> None:
    statsbomb_rows = load_statsbomb_rows()
    kaggle_rows = load_kaggle_elo_rows()

    alignment_rows = build_alignment_rows(statsbomb_rows, kaggle_rows)

    save_alignment_csv(alignment_rows)
    save_summary(statsbomb_rows, kaggle_rows, alignment_rows)

    print("OK - Audit alignement V18.1 Kaggle + Elo + StatsBomb termine.")
    print(f"StatsBomb rows: {len(statsbomb_rows)}")
    print(f"Kaggle/Elo rows: {len(kaggle_rows)}")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"CSV saved: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()


# Schema de communication :
# audit_v18_1_kaggle_statsbomb_match_alignment.py
#   -> lit PostgreSQL ml_national.features + ml_national.clean_matches
#   -> lit reports/evidence/ml_training/326_statsbomb_national_rolling_features.csv
#   -> aligne les matchs par date + equipes + score
#   -> produit reports/evidence/ml_training/330_v18_1_kaggle_statsbomb_alignment_summary.txt
#   -> produit reports/evidence/ml_training/331_v18_1_kaggle_statsbomb_alignment_matches.csv