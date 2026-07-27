# Role du fichier :
# Ce script construit le dataset V18.1 WC enriched en fusionnant Kaggle/Elo
# avec les features rolling StatsBomb anti-fuite sur les matchs Coupe du Monde alignes.

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[3]

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"

ALIGNMENT_CSV = EVIDENCE_DIR / "331_v18_1_kaggle_statsbomb_alignment_matches.csv"
STATSBOMB_ROLLING_CSV = EVIDENCE_DIR / "326_statsbomb_national_rolling_features.csv"

SUMMARY_FILE = EVIDENCE_DIR / "332_v18_1_wc_enriched_dataset_summary.txt"
OUTPUT_CSV = EVIDENCE_DIR / "333_v18_1_wc_enriched_dataset.csv"


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
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Cette fonction recupere l'URL PostgreSQL du projet.
def get_database_url() -> str:
    load_env_files()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL introuvable. Verifie .env ou backend/.env.")

    return database_url


# Cette fonction quote proprement un identifiant SQL.
def qident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


# Cette fonction charge un CSV en liste de dictionnaires.
def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


# Cette fonction convertit une valeur en entier.
def to_int(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


# Cette fonction garde uniquement les matchs alignes proprement.
def filter_matched_alignment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("alignment_status") in {"matched_direct", "matched_reversed"}
    ]


# Cette fonction indexe les features StatsBomb rolling par match_id.
def index_statsbomb_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("statsbomb_match_id")): row
        for row in rows
        if row.get("statsbomb_match_id")
    }


# Cette fonction recupere les colonnes d'une table PostgreSQL.
def get_table_columns(connection: psycopg.Connection, schema: str, table: str) -> list[str]:
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (schema, table))
        return [str(row["column_name"]) for row in cursor.fetchall()]


# Cette fonction charge toutes les features Kaggle/Elo utiles pour les clean_match_id alignes.
def load_kaggle_elo_by_clean_match_id(clean_match_ids: list[int]) -> dict[str, dict[str, Any]]:
    if not clean_match_ids:
        return {}

    database_url = get_database_url()

    with psycopg.connect(database_url) as connection:
        feature_columns = get_table_columns(connection, "ml_national", "features")
        clean_columns = get_table_columns(connection, "ml_national", "clean_matches")

        clean_pk = "clean_match_id" if "clean_match_id" in clean_columns else "id"

        feature_select = [
            f"f.{qident(column)} AS {qident('f_' + column)}"
            for column in feature_columns
        ]

        clean_select = [
            f"cm.{qident(column)} AS {qident('cm_' + column)}"
            for column in clean_columns
        ]

        query = f"""
            SELECT
                {", ".join(feature_select + clean_select)}
            FROM ml_national.features f
            JOIN ml_national.clean_matches cm
              ON f.clean_match_id = cm.{qident(clean_pk)}
            WHERE f.clean_match_id = ANY(%s)
        """

        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, (clean_match_ids,))
            rows = [dict(row) for row in cursor.fetchall()]

    return {
        str(row.get("f_clean_match_id")): row
        for row in rows
    }


# Cette fonction retourne les colonnes rolling StatsBomb utiles.
def get_statsbomb_feature_columns(row: dict[str, Any]) -> list[str]:
    return [
        column
        for column in row.keys()
        if column.startswith("team_a_") or column.startswith("team_b_")
    ]


# Cette fonction aligne les features StatsBomb sur le sens Kaggle Team A / Team B.
def build_aligned_statsbomb_features(
    statsbomb_row: dict[str, Any],
    is_reversed: bool,
) -> dict[str, Any]:
    output: dict[str, Any] = {}

    for column in get_statsbomb_feature_columns(statsbomb_row):
        value = statsbomb_row.get(column)

        if is_reversed and column.startswith("team_a_"):
            output[f"sb_team_b_{column.removeprefix('team_a_')}"] = value

        elif is_reversed and column.startswith("team_b_"):
            output[f"sb_team_a_{column.removeprefix('team_b_')}"] = value

        elif column.startswith("team_a_"):
            output[f"sb_{column}"] = value

        elif column.startswith("team_b_"):
            output[f"sb_{column}"] = value

    return output


# Cette fonction construit une ligne enrichie V18.1.
def build_enriched_row(
    alignment_row: dict[str, Any],
    statsbomb_index: dict[str, dict[str, Any]],
    kaggle_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    clean_match_id = str(alignment_row.get("clean_match_id"))
    statsbomb_match_id = str(alignment_row.get("statsbomb_match_id"))

    statsbomb_row = statsbomb_index.get(statsbomb_match_id, {})
    kaggle_row = kaggle_index.get(clean_match_id, {})

    is_reversed = alignment_row.get("alignment_status") == "matched_reversed"

    output = {
        "clean_match_id": clean_match_id,
        "feature_id": alignment_row.get("feature_id"),
        "statsbomb_match_id": statsbomb_match_id,
        "alignment_status": alignment_row.get("alignment_status"),
        "match_date": alignment_row.get("match_date"),
        "competition_name": alignment_row.get("kaggle_competition_name"),
        "statsbomb_competition_name": alignment_row.get("statsbomb_competition_name"),
        "statsbomb_season_name": alignment_row.get("statsbomb_season_name"),
        "team_a_name": alignment_row.get("kaggle_team_a_name"),
        "team_b_name": alignment_row.get("kaggle_team_b_name"),
        "team_a_score": alignment_row.get("kaggle_team_a_score"),
        "team_b_score": alignment_row.get("kaggle_team_b_score"),
        "target_1x2": alignment_row.get("result_1x2"),
        "target_over_1_5": alignment_row.get("target_over_1_5"),
        "target_over_2_5": alignment_row.get("target_over_2_5"),
        "target_btts": alignment_row.get("target_btts"),
    }

    for key, value in kaggle_row.items():
        output[key] = value

    output.update(build_aligned_statsbomb_features(statsbomb_row, is_reversed))

    return output


# Cette fonction construit toutes les lignes enrichies V18.1.
def build_enriched_rows(
    alignment_rows: list[dict[str, Any]],
    statsbomb_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matched_rows = filter_matched_alignment_rows(alignment_rows)
    statsbomb_index = index_statsbomb_rows(statsbomb_rows)

    clean_match_ids = [
        to_int(row.get("clean_match_id"))
        for row in matched_rows
        if row.get("clean_match_id")
    ]

    kaggle_index = load_kaggle_elo_by_clean_match_id(clean_match_ids)

    enriched_rows = [
        build_enriched_row(row, statsbomb_index, kaggle_index)
        for row in matched_rows
    ]

    enriched_rows = sorted(
        enriched_rows,
        key=lambda row: (
            str(row.get("match_date", "")),
            str(row.get("statsbomb_match_id", "")),
        ),
    )

    return enriched_rows


# Cette fonction sauvegarde le CSV enrichi avec colonnes dynamiques.
def save_enriched_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    if not rows:
        OUTPUT_CSV.write_text("", encoding="utf-8")
        return

    priority_columns = [
        "clean_match_id",
        "feature_id",
        "statsbomb_match_id",
        "alignment_status",
        "match_date",
        "competition_name",
        "statsbomb_competition_name",
        "statsbomb_season_name",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "target_1x2",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
    ]

    all_columns = list(dict.fromkeys(
        priority_columns
        + [column for row in rows for column in row.keys()]
    ))

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=all_columns)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction calcule un ratio securise.
def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0

    return round(float(numerator) / float(denominator), 4)


# Cette fonction sauvegarde la synthese du dataset enrichi.
def save_summary(
    alignment_rows: list[dict[str, Any]],
    enriched_rows: list[dict[str, Any]],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    total_alignment = len(alignment_rows)
    total_enriched = len(enriched_rows)

    direct = sum(1 for row in enriched_rows if row.get("alignment_status") == "matched_direct")
    reversed_count = sum(1 for row in enriched_rows if row.get("alignment_status") == "matched_reversed")

    over_1_5 = sum(1 for row in enriched_rows if str(row.get("target_over_1_5")).lower() == "true")
    over_2_5 = sum(1 for row in enriched_rows if str(row.get("target_over_2_5")).lower() == "true")
    btts = sum(1 for row in enriched_rows if str(row.get("target_btts")).lower() == "true")

    competition_counts: dict[str, int] = {}
    for row in enriched_rows:
        key = f"{row.get('statsbomb_competition_name')} {row.get('statsbomb_season_name')}"
        competition_counts[key] = competition_counts.get(key, 0) + 1

    lines = [
        "RubyBets - Dataset V18.1 WC enriched",
        "",
        f"Source alignement : {ALIGNMENT_CSV}",
        f"Source StatsBomb rolling : {STATSBOMB_ROLLING_CSV}",
        f"Fichier genere : {OUTPUT_CSV}",
        "",
        "Objectif :",
        "Construire un dataset enrichi Kaggle + Elo + StatsBomb rolling features",
        "pour tester ensuite 1X2, double chance, OVER_1_5, OVER_2_5 et BTTS.",
        "",
        "Perimetre retenu :",
        "Coupe du Monde 2018 + Coupe du Monde 2022 uniquement.",
        "Les matchs Euro et Copa America ne sont pas fusionnes car non alignes dans le socle Kaggle/Elo actuel.",
        "",
        "Regle de qualite :",
        "Seuls les matchs alignes proprement sont conserves.",
        "Les matchs ambigus ou non alignes sont exclus.",
        "Les features StatsBomb sont des rolling features anti-fuite.",
        "",
        "Resultats :",
        f"- Lignes alignement disponibles : {total_alignment}",
        f"- Lignes enrichies generees : {total_enriched}",
        f"- Alignements directs : {direct}",
        f"- Alignements inverses : {reversed_count}",
        "",
        "Distribution targets enrichies :",
        f"- OVER_1_5 : {over_1_5} / {total_enriched} ({safe_ratio(over_1_5, total_enriched)})",
        f"- OVER_2_5 : {over_2_5} / {total_enriched} ({safe_ratio(over_2_5, total_enriched)})",
        f"- BTTS : {btts} / {total_enriched} ({safe_ratio(btts, total_enriched)})",
        "",
        "Repartition par competition :",
    ]

    for key, count in sorted(competition_counts.items()):
        lines.append(f"- {key}: {count}")

    lines.extend(
        [
            "",
            "Decision :",
            "- Dataset V18.1 WC enriched pret pour entrainement experimental.",
            "- Ce dataset reste limite a 128 matchs Coupe du Monde.",
            "- Il doit servir a comparer Kaggle + Elo seul contre Kaggle + Elo + StatsBomb.",
            "- Aucun resultat ne doit etre integre au produit avant evaluation.",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance la construction complete du dataset enrichi V18.1.
def main() -> None:
    alignment_rows = load_csv(ALIGNMENT_CSV)
    statsbomb_rows = load_csv(STATSBOMB_ROLLING_CSV)

    enriched_rows = build_enriched_rows(alignment_rows, statsbomb_rows)

    save_enriched_csv(enriched_rows)
    save_summary(alignment_rows, enriched_rows)

    print("OK - Dataset V18.1 WC enriched genere.")
    print(f"Rows: {len(enriched_rows)}")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"CSV saved: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()


# Schema de communication :
# build_v18_1_wc_enriched_dataset.py
#   -> lit reports/evidence/ml_training/331_v18_1_kaggle_statsbomb_alignment_matches.csv
#   -> lit reports/evidence/ml_training/326_statsbomb_national_rolling_features.csv
#   -> lit PostgreSQL ml_national.features + ml_national.clean_matches
#   -> fusionne Kaggle + Elo + StatsBomb rolling features sur les matchs alignes
#   -> produit reports/evidence/ml_training/332_v18_1_wc_enriched_dataset_summary.txt
#   -> produit reports/evidence/ml_training/333_v18_1_wc_enriched_dataset.csv