# Rôle du fichier :
# Ce script construit les features nationales RubyBets à partir des matchs propres
# et de l'Elo national calculé, sans modifier le pipeline club V17.8.

from pathlib import Path
import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"
EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_COMPETITION_CODES = ["WC", "WCQ"]
DEFAULT_FEATURE_VERSION = "national_v1_elo_form"
DEFAULT_ELO_RANKING_SOURCE = "rubybets_national_elo_v1_before_match"

SUMMARY_FILENAME = "301_national_features_summary.txt"
FEATURES_PREVIEW_FILENAME = "302_national_features_preview.csv"


@dataclass
class NationalFeatureRow:
    clean_match_id: int
    competition_code: str
    season: str | None
    match_date_utc: object
    team_a_name: str
    team_b_name: str
    home_form_points_last_5: float | None
    away_form_points_last_5: float | None
    home_form_points_last_10: float | None
    away_form_points_last_10: float | None
    home_goals_scored_avg_last_10: float | None
    away_goals_scored_avg_last_10: float | None
    home_goals_conceded_avg_last_10: float | None
    away_goals_conceded_avg_last_10: float | None
    ranking_gap: float | None
    elo_gap: float | None
    is_neutral_venue: bool
    team_a_is_host: bool
    team_b_is_host: bool
    host_advantage_side: str
    is_group_stage: bool
    is_knockout_stage: bool
    target_result: str


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
        description="Construire les features nationales RubyBets pour V17.9."
    )

    parser.add_argument(
        "--competition-codes",
        default=",".join(DEFAULT_COMPETITION_CODES),
        help="Codes compétition à traiter, séparés par des virgules. Par défaut : WC,WCQ.",
    )

    parser.add_argument(
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help="Version des features insérées dans ml_national.features.",
    )

    parser.add_argument(
        "--elo-ranking-source",
        default=DEFAULT_ELO_RANKING_SOURCE,
        help="Source Elo avant match à utiliser depuis ml_national.team_rankings.",
    )

    return parser.parse_args()


# Convertit une valeur numérique PostgreSQL en float Python.
def to_float(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


# Arrondit une valeur numérique si elle existe.
def round_or_none(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None

    return round(value, digits)


# Calcule une moyenne sur une liste, ou None si aucun historique n'existe.
def average_or_none(values: list[float]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


# Calcule les points Team A / Team B selon le résultat réel.
def build_points_from_result(result_1x2: str) -> tuple[int, int]:
    if result_1x2 == "TEAM_A_WIN":
        return 3, 0

    if result_1x2 == "TEAM_B_WIN":
        return 0, 3

    return 1, 1


# Récupère les matchs propres enrichis avec l'Elo avant match.
def fetch_clean_matches_with_elo(
    connection: psycopg.Connection,
    competition_codes: list[str],
    elo_ranking_source: str,
) -> list[dict]:
    query = """
        SELECT
            cm.id,
            cm.competition_code,
            cm.competition_name,
            cm.season,
            cm.match_date_utc,
            cm.stage,
            cm.group_name,
            cm.home_team_name,
            cm.away_team_name,
            cm.home_score,
            cm.away_score,
            cm.result_1x2,
            cm.is_neutral_venue,
            cm.team_a_is_host,
            cm.team_b_is_host,
            cm.host_advantage_side,
            cm.is_group_stage,
            cm.is_knockout_stage,

            (
                SELECT tr.rating_value
                FROM ml_national.team_rankings tr
                WHERE tr.ranking_source = %s
                  AND tr.team_name = cm.home_team_name
                  AND tr.metadata ->> 'clean_match_id' = cm.id::text
                  AND tr.metadata ->> 'team_side' = 'TEAM_A'
                LIMIT 1
            ) AS team_a_elo_before,

            (
                SELECT tr.rating_value
                FROM ml_national.team_rankings tr
                WHERE tr.ranking_source = %s
                  AND tr.team_name = cm.away_team_name
                  AND tr.metadata ->> 'clean_match_id' = cm.id::text
                  AND tr.metadata ->> 'team_side' = 'TEAM_B'
                LIMIT 1
            ) AS team_b_elo_before

        FROM ml_national.clean_matches cm
        WHERE cm.competition_code = ANY(%s)
          AND cm.match_date_utc IS NOT NULL
          AND cm.home_team_name IS NOT NULL
          AND cm.away_team_name IS NOT NULL
          AND cm.home_score IS NOT NULL
          AND cm.away_score IS NOT NULL
          AND cm.result_1x2 IN ('TEAM_A_WIN', 'DRAW', 'TEAM_B_WIN')
        ORDER BY cm.match_date_utc ASC, cm.id ASC
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (elo_ranking_source, elo_ranking_source, competition_codes))
        return list(cursor.fetchall())


# Construit les features chronologiques sans utiliser d'informations futures.
def build_feature_rows(matches: list[dict]) -> list[NationalFeatureRow]:
    team_points_history = defaultdict(list)
    team_goals_scored_history = defaultdict(list)
    team_goals_conceded_history = defaultdict(list)

    feature_rows = []

    for match in matches:
        team_a_name = match["home_team_name"]
        team_b_name = match["away_team_name"]

        team_a_points_history = team_points_history[team_a_name]
        team_b_points_history = team_points_history[team_b_name]

        team_a_scored_history = team_goals_scored_history[team_a_name]
        team_b_scored_history = team_goals_scored_history[team_b_name]

        team_a_conceded_history = team_goals_conceded_history[team_a_name]
        team_b_conceded_history = team_goals_conceded_history[team_b_name]

        team_a_elo_before = to_float(match.get("team_a_elo_before"))
        team_b_elo_before = to_float(match.get("team_b_elo_before"))

        elo_gap = None
        if team_a_elo_before is not None and team_b_elo_before is not None:
            elo_gap = team_a_elo_before - team_b_elo_before

        feature_rows.append(
            NationalFeatureRow(
                clean_match_id=match["id"],
                competition_code=match["competition_code"],
                season=match.get("season"),
                match_date_utc=match["match_date_utc"],
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                home_form_points_last_5=round_or_none(sum(team_a_points_history[-5:])),
                away_form_points_last_5=round_or_none(sum(team_b_points_history[-5:])),
                home_form_points_last_10=round_or_none(sum(team_a_points_history[-10:])),
                away_form_points_last_10=round_or_none(sum(team_b_points_history[-10:])),
                home_goals_scored_avg_last_10=round_or_none(
                    average_or_none(team_a_scored_history[-10:])
                ),
                away_goals_scored_avg_last_10=round_or_none(
                    average_or_none(team_b_scored_history[-10:])
                ),
                home_goals_conceded_avg_last_10=round_or_none(
                    average_or_none(team_a_conceded_history[-10:])
                ),
                away_goals_conceded_avg_last_10=round_or_none(
                    average_or_none(team_b_conceded_history[-10:])
                ),
                ranking_gap=None,
                elo_gap=round_or_none(elo_gap),
                is_neutral_venue=bool(match.get("is_neutral_venue")),
                team_a_is_host=bool(match.get("team_a_is_host")),
                team_b_is_host=bool(match.get("team_b_is_host")),
                host_advantage_side=match.get("host_advantage_side") or "NONE",
                is_group_stage=bool(match.get("is_group_stage")),
                is_knockout_stage=bool(match.get("is_knockout_stage")),
                target_result=match["result_1x2"],
            )
        )

        team_a_points, team_b_points = build_points_from_result(match["result_1x2"])

        team_points_history[team_a_name].append(team_a_points)
        team_points_history[team_b_name].append(team_b_points)

        team_goals_scored_history[team_a_name].append(float(match["home_score"]))
        team_goals_scored_history[team_b_name].append(float(match["away_score"]))

        team_goals_conceded_history[team_a_name].append(float(match["away_score"]))
        team_goals_conceded_history[team_b_name].append(float(match["home_score"]))

    return feature_rows


# Supprime les anciennes features de la même version.
def delete_existing_features(connection: psycopg.Connection, feature_version: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM ml_national.features
            WHERE feature_version = %s
            """,
            (feature_version,),
        )

        return cursor.rowcount


# Insère les nouvelles features dans ml_national.features.
def insert_feature_rows(
    connection: psycopg.Connection,
    feature_rows: list[NationalFeatureRow],
    feature_version: str,
) -> int:
    inserted_rows = 0

    with connection.cursor() as cursor:
        for row in feature_rows:
            cursor.execute(
                """
                INSERT INTO ml_national.features (
                    clean_match_id,
                    feature_version,
                    team_type,
                    home_form_points_last_5,
                    away_form_points_last_5,
                    home_form_points_last_10,
                    away_form_points_last_10,
                    home_goals_scored_avg_last_10,
                    away_goals_scored_avg_last_10,
                    home_goals_conceded_avg_last_10,
                    away_goals_conceded_avg_last_10,
                    ranking_gap,
                    elo_gap,
                    is_neutral_venue,
                    team_a_is_host,
                    team_b_is_host,
                    host_advantage_side,
                    is_group_stage,
                    is_knockout_stage,
                    target_result
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (clean_match_id, feature_version)
                DO UPDATE SET
                    team_type = EXCLUDED.team_type,
                    home_form_points_last_5 = EXCLUDED.home_form_points_last_5,
                    away_form_points_last_5 = EXCLUDED.away_form_points_last_5,
                    home_form_points_last_10 = EXCLUDED.home_form_points_last_10,
                    away_form_points_last_10 = EXCLUDED.away_form_points_last_10,
                    home_goals_scored_avg_last_10 = EXCLUDED.home_goals_scored_avg_last_10,
                    away_goals_scored_avg_last_10 = EXCLUDED.away_goals_scored_avg_last_10,
                    home_goals_conceded_avg_last_10 = EXCLUDED.home_goals_conceded_avg_last_10,
                    away_goals_conceded_avg_last_10 = EXCLUDED.away_goals_conceded_avg_last_10,
                    ranking_gap = EXCLUDED.ranking_gap,
                    elo_gap = EXCLUDED.elo_gap,
                    is_neutral_venue = EXCLUDED.is_neutral_venue,
                    team_a_is_host = EXCLUDED.team_a_is_host,
                    team_b_is_host = EXCLUDED.team_b_is_host,
                    host_advantage_side = EXCLUDED.host_advantage_side,
                    is_group_stage = EXCLUDED.is_group_stage,
                    is_knockout_stage = EXCLUDED.is_knockout_stage,
                    target_result = EXCLUDED.target_result,
                    created_at = NOW()
                """,
                (
                    row.clean_match_id,
                    feature_version,
                    "national",
                    row.home_form_points_last_5,
                    row.away_form_points_last_5,
                    row.home_form_points_last_10,
                    row.away_form_points_last_10,
                    row.home_goals_scored_avg_last_10,
                    row.away_goals_scored_avg_last_10,
                    row.home_goals_conceded_avg_last_10,
                    row.away_goals_conceded_avg_last_10,
                    row.ranking_gap,
                    row.elo_gap,
                    row.is_neutral_venue,
                    row.team_a_is_host,
                    row.team_b_is_host,
                    row.host_advantage_side,
                    row.is_group_stage,
                    row.is_knockout_stage,
                    row.target_result,
                ),
            )

            inserted_rows += 1

    return inserted_rows


# Crée le dossier de preuves ML si nécessaire.
def ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# Compte les valeurs manquantes par feature importante.
def build_missing_counts(feature_rows: list[NationalFeatureRow]) -> dict[str, int]:
    fields_to_check = [
        "home_form_points_last_5",
        "away_form_points_last_5",
        "home_form_points_last_10",
        "away_form_points_last_10",
        "home_goals_scored_avg_last_10",
        "away_goals_scored_avg_last_10",
        "home_goals_conceded_avg_last_10",
        "away_goals_conceded_avg_last_10",
        "elo_gap",
    ]

    missing_counts = {}

    for field_name in fields_to_check:
        missing_counts[field_name] = sum(
            1
            for row in feature_rows
            if getattr(row, field_name) is None
        )

    return missing_counts


# Exporte un aperçu CSV des features générées.
def export_features_preview_csv(feature_rows: list[NationalFeatureRow]) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / FEATURES_PREVIEW_FILENAME

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "clean_match_id",
                "match_date_utc",
                "competition_code",
                "season",
                "team_a_name",
                "team_b_name",
                "home_form_points_last_5",
                "away_form_points_last_5",
                "home_form_points_last_10",
                "away_form_points_last_10",
                "home_goals_scored_avg_last_10",
                "away_goals_scored_avg_last_10",
                "home_goals_conceded_avg_last_10",
                "away_goals_conceded_avg_last_10",
                "elo_gap",
                "is_neutral_venue",
                "host_advantage_side",
                "is_group_stage",
                "is_knockout_stage",
                "target_result",
            ]
        )

        for row in feature_rows:
            writer.writerow(
                [
                    row.clean_match_id,
                    row.match_date_utc.isoformat(),
                    row.competition_code,
                    row.season,
                    row.team_a_name,
                    row.team_b_name,
                    row.home_form_points_last_5,
                    row.away_form_points_last_5,
                    row.home_form_points_last_10,
                    row.away_form_points_last_10,
                    row.home_goals_scored_avg_last_10,
                    row.away_goals_scored_avg_last_10,
                    row.home_goals_conceded_avg_last_10,
                    row.away_goals_conceded_avg_last_10,
                    row.elo_gap,
                    row.is_neutral_venue,
                    row.host_advantage_side,
                    row.is_group_stage,
                    row.is_knockout_stage,
                    row.target_result,
                ]
            )

    return output_path


# Exporte un résumé texte exploitable comme preuve RNCP.
def export_summary_txt(
    feature_rows: list[NationalFeatureRow],
    deleted_rows: int,
    inserted_rows: int,
    feature_version: str,
    preview_path: Path,
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    competition_counts = Counter(row.competition_code for row in feature_rows)
    target_counts = Counter(row.target_result for row in feature_rows)
    host_counts = Counter(row.host_advantage_side for row in feature_rows)
    missing_counts = build_missing_counts(feature_rows)

    first_date = feature_rows[0].match_date_utc.date() if feature_rows else "N/A"
    last_date = feature_rows[-1].match_date_utc.date() if feature_rows else "N/A"

    rows_with_complete_core_features = sum(
        1
        for row in feature_rows
        if row.home_form_points_last_10 is not None
        and row.away_form_points_last_10 is not None
        and row.home_goals_scored_avg_last_10 is not None
        and row.away_goals_scored_avg_last_10 is not None
        and row.home_goals_conceded_avg_last_10 is not None
        and row.away_goals_conceded_avg_last_10 is not None
        and row.elo_gap is not None
    )

    lines = [
        "OK - Features nationales RubyBets construites.",
        f"Feature version : {feature_version}",
        f"Matchs transformés en features : {len(feature_rows)}",
        f"Lignes anciennes supprimées : {deleted_rows}",
        f"Lignes insérées/mises à jour : {inserted_rows}",
        f"Première date : {first_date}",
        f"Dernière date : {last_date}",
        f"Lignes avec core features complètes : {rows_with_complete_core_features}",
        "Table cible : ml_national.features",
        f"CSV aperçu features : {preview_path}",
        "",
        "Répartition par compétition :",
    ]

    for competition_code, count in competition_counts.items():
        lines.append(f"- {competition_code}: {count}")

    lines.extend(["", "Répartition target_result :"])

    for target_result, count in target_counts.items():
        lines.append(f"- {target_result}: {count}")

    lines.extend(["", "Répartition contexte hôte :"])

    for host_side, count in host_counts.items():
        lines.append(f"- {host_side}: {count}")

    lines.extend(["", "Valeurs manquantes par feature :"])

    for field_name, count in missing_counts.items():
        lines.append(f"- {field_name}: {count}")

    lines.extend(
        [
            "",
            "Décision technique :",
            "- Les colonnes home_* et away_* sont utilisées comme Team A / Team B dans le pipeline national.",
            "- Les features sont calculées chronologiquement pour éviter toute fuite de données futures.",
            "- ranking_gap reste vide car aucun classement FIFA externe n'est encore intégré.",
            "- elo_gap vient de ml_national.team_rankings et devient la feature de niveau relatif principale.",
            "- Le pipeline club V17.8 et la table ml.features ne sont pas modifiés.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# Affiche un résumé clair dans le terminal.
def print_summary(
    feature_rows: list[NationalFeatureRow],
    inserted_rows: int,
    summary_path: Path,
    preview_path: Path,
) -> None:
    missing_counts = build_missing_counts(feature_rows)

    print("OK - Features nationales RubyBets construites.")
    print(f"Matchs transformés en features : {len(feature_rows)}")
    print(f"Lignes insérées/mises à jour : {inserted_rows}")
    print("Table mise à jour : ml_national.features")
    print(f"Résumé sauvegardé : {summary_path}")
    print(f"Aperçu CSV sauvegardé : {preview_path}")
    print("\nValeurs manquantes principales :")
    print(f"- elo_gap : {missing_counts['elo_gap']}")
    print(f"- home_form_points_last_10 : {missing_counts['home_form_points_last_10']}")
    print(f"- away_form_points_last_10 : {missing_counts['away_form_points_last_10']}")


# Exécute la construction complète des features nationales.
def main() -> None:
    try:
        args = parse_arguments()

        competition_codes = [
            code.strip().upper()
            for code in args.competition_codes.split(",")
            if code.strip()
        ]

        database_url = get_database_url()

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                matches = fetch_clean_matches_with_elo(
                    connection=connection,
                    competition_codes=competition_codes,
                    elo_ranking_source=args.elo_ranking_source,
                )

                if not matches:
                    raise ValueError(
                        "Aucun match national exploitable trouvé dans ml_national.clean_matches"
                    )

                feature_rows = build_feature_rows(matches)

                deleted_rows = delete_existing_features(
                    connection=connection,
                    feature_version=args.feature_version,
                )

                inserted_rows = insert_feature_rows(
                    connection=connection,
                    feature_rows=feature_rows,
                    feature_version=args.feature_version,
                )

        preview_path = export_features_preview_csv(feature_rows)

        summary_path = export_summary_txt(
            feature_rows=feature_rows,
            deleted_rows=deleted_rows,
            inserted_rows=inserted_rows,
            feature_version=args.feature_version,
            preview_path=preview_path,
        )

        print_summary(
            feature_rows=feature_rows,
            inserted_rows=inserted_rows,
            summary_path=summary_path,
            preview_path=preview_path,
        )

    except Exception as error:
        print("Erreur pendant la construction des features nationales.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# ml_national.clean_matches
#        ↓
# ml_national.team_rankings
#        ↓
# backend/scripts/ml_national/build_national_features.py
#        ↓
# ml_national.features
#        ↓
# reports/evidence/ml_training/
#        ↓
# futur entraînement V17.9