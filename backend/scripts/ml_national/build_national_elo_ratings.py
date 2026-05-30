# Rôle du fichier :
# Ce script calcule un Elo interne RubyBets pour les équipes nationales
# à partir des matchs propres stockés dans ml_national.clean_matches.

from pathlib import Path
import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"
EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

DEFAULT_COMPETITION_CODES = ["WC", "WCQ"]
DEFAULT_INITIAL_ELO = 1500.0
DEFAULT_WC_K_FACTOR = 60.0
DEFAULT_WCQ_K_FACTOR = 40.0
DEFAULT_HOST_ADVANTAGE_ELO = 50.0
DEFAULT_RANKING_SOURCE = "rubybets_national_elo_v1"

SUMMARY_FILENAME = "298_national_elo_summary.txt"
FINAL_RANKINGS_FILENAME = "299_national_elo_final_rankings.csv"
MATCH_UPDATES_FILENAME = "300_national_elo_match_updates.csv"


@dataclass
class EloMatchUpdate:
    clean_match_id: int
    match_date_utc: datetime
    competition_code: str
    season: str | None
    team_a_name: str
    team_b_name: str
    result_1x2: str
    team_a_elo_before: float
    team_b_elo_before: float
    team_a_elo_after: float
    team_b_elo_after: float
    team_a_expected_score: float
    team_b_expected_score: float
    team_a_actual_score: float
    team_b_actual_score: float
    k_factor: float
    elo_gap_before: float
    host_advantage_side: str
    is_neutral_venue: bool


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
        description="Calculer l'Elo national RubyBets depuis ml_national.clean_matches."
    )

    parser.add_argument(
        "--competition-codes",
        default=",".join(DEFAULT_COMPETITION_CODES),
        help="Codes compétition à traiter, séparés par des virgules. Par défaut : WC,WCQ.",
    )

    parser.add_argument(
        "--initial-elo",
        type=float,
        default=DEFAULT_INITIAL_ELO,
        help="Elo initial attribué à chaque nouvelle sélection. Par défaut : 1500.",
    )

    parser.add_argument(
        "--wc-k-factor",
        type=float,
        default=DEFAULT_WC_K_FACTOR,
        help="Facteur K pour la Coupe du Monde finale. Par défaut : 60.",
    )

    parser.add_argument(
        "--wcq-k-factor",
        type=float,
        default=DEFAULT_WCQ_K_FACTOR,
        help="Facteur K pour les qualifications Coupe du Monde. Par défaut : 40.",
    )

    parser.add_argument(
        "--host-advantage-elo",
        type=float,
        default=DEFAULT_HOST_ADVANTAGE_ELO,
        help="Bonus Elo appliqué uniquement au contexte hôte explicite. Par défaut : 50.",
    )

    parser.add_argument(
        "--ranking-source",
        default=DEFAULT_RANKING_SOURCE,
        help="Préfixe de source utilisé dans ml_national.team_rankings.",
    )

    return parser.parse_args()


# Récupère les matchs nationaux terminés et exploitables.
def fetch_clean_matches(
    connection: psycopg.Connection,
    competition_codes: list[str],
) -> list[dict]:
    query = """
        SELECT
            id,
            competition_code,
            competition_name,
            season,
            match_date_utc,
            stage,
            group_name,
            home_team_name,
            away_team_name,
            home_score,
            away_score,
            result_1x2,
            is_neutral_venue,
            team_a_is_host,
            team_b_is_host,
            host_advantage_side,
            is_group_stage,
            is_knockout_stage
        FROM ml_national.clean_matches
        WHERE competition_code = ANY(%s)
          AND match_date_utc IS NOT NULL
          AND home_team_name IS NOT NULL
          AND away_team_name IS NOT NULL
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND result_1x2 IN ('TEAM_A_WIN', 'DRAW', 'TEAM_B_WIN')
        ORDER BY match_date_utc ASC, id ASC
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, (competition_codes,))
        return list(cursor.fetchall())


# Convertit le résultat Team A / Team B en score Elo numérique.
def build_actual_score(result_1x2: str) -> tuple[float, float]:
    if result_1x2 == "TEAM_A_WIN":
        return 1.0, 0.0

    if result_1x2 == "TEAM_B_WIN":
        return 0.0, 1.0

    return 0.5, 0.5


# Détermine le facteur K selon la compétition.
def build_k_factor(match: dict, wc_k_factor: float, wcq_k_factor: float) -> float:
    competition_code = match.get("competition_code")

    if competition_code == "WC":
        return wc_k_factor

    if competition_code == "WCQ":
        return wcq_k_factor

    return wcq_k_factor


# Calcule le bonus de contexte hôte sans appliquer un domicile club classique.
def build_host_adjustments(match: dict, host_advantage_elo: float) -> tuple[float, float]:
    host_advantage_side = match.get("host_advantage_side") or "NONE"

    if host_advantage_side == "TEAM_A":
        return host_advantage_elo, 0.0

    if host_advantage_side == "TEAM_B":
        return 0.0, host_advantage_elo

    return 0.0, 0.0


# Calcule la probabilité Elo attendue pour Team A et Team B.
def build_expected_scores(
    team_a_elo: float,
    team_b_elo: float,
    team_a_host_adjustment: float,
    team_b_host_adjustment: float,
) -> tuple[float, float]:
    adjusted_team_a_elo = team_a_elo + team_a_host_adjustment
    adjusted_team_b_elo = team_b_elo + team_b_host_adjustment

    expected_team_a = 1 / (1 + 10 ** ((adjusted_team_b_elo - adjusted_team_a_elo) / 400))
    expected_team_b = 1 - expected_team_a

    return expected_team_a, expected_team_b


# Calcule les évolutions Elo match par match dans l'ordre chronologique.
def build_elo_updates(
    matches: list[dict],
    initial_elo: float,
    wc_k_factor: float,
    wcq_k_factor: float,
    host_advantage_elo: float,
) -> tuple[list[EloMatchUpdate], dict[str, float], dict[str, int]]:
    ratings = defaultdict(lambda: initial_elo)
    matches_played_by_team = Counter()
    updates = []

    for match in matches:
        team_a_name = match["home_team_name"]
        team_b_name = match["away_team_name"]

        team_a_elo_before = float(ratings[team_a_name])
        team_b_elo_before = float(ratings[team_b_name])

        team_a_host_adjustment, team_b_host_adjustment = build_host_adjustments(
            match=match,
            host_advantage_elo=host_advantage_elo,
        )

        team_a_expected_score, team_b_expected_score = build_expected_scores(
            team_a_elo=team_a_elo_before,
            team_b_elo=team_b_elo_before,
            team_a_host_adjustment=team_a_host_adjustment,
            team_b_host_adjustment=team_b_host_adjustment,
        )

        team_a_actual_score, team_b_actual_score = build_actual_score(match["result_1x2"])

        k_factor = build_k_factor(
            match=match,
            wc_k_factor=wc_k_factor,
            wcq_k_factor=wcq_k_factor,
        )

        team_a_elo_after = team_a_elo_before + k_factor * (
            team_a_actual_score - team_a_expected_score
        )
        team_b_elo_after = team_b_elo_before + k_factor * (
            team_b_actual_score - team_b_expected_score
        )

        ratings[team_a_name] = team_a_elo_after
        ratings[team_b_name] = team_b_elo_after

        matches_played_by_team[team_a_name] += 1
        matches_played_by_team[team_b_name] += 1

        updates.append(
            EloMatchUpdate(
                clean_match_id=match["id"],
                match_date_utc=match["match_date_utc"],
                competition_code=match["competition_code"],
                season=match.get("season"),
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                result_1x2=match["result_1x2"],
                team_a_elo_before=team_a_elo_before,
                team_b_elo_before=team_b_elo_before,
                team_a_elo_after=team_a_elo_after,
                team_b_elo_after=team_b_elo_after,
                team_a_expected_score=team_a_expected_score,
                team_b_expected_score=team_b_expected_score,
                team_a_actual_score=team_a_actual_score,
                team_b_actual_score=team_b_actual_score,
                k_factor=k_factor,
                elo_gap_before=team_a_elo_before - team_b_elo_before,
                host_advantage_side=match.get("host_advantage_side") or "NONE",
                is_neutral_venue=bool(match.get("is_neutral_venue")),
            )
        )

    return updates, dict(ratings), dict(matches_played_by_team)


# Supprime les anciennes lignes Elo RubyBets pour éviter les doublons de calcul.
def delete_existing_elo_rankings(connection: psycopg.Connection, ranking_source: str) -> int:
    ranking_sources = [
        f"{ranking_source}_before_match",
        f"{ranking_source}_after_match",
        f"{ranking_source}_latest",
    ]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM ml_national.team_rankings
            WHERE ranking_source = ANY(%s)
            """,
            (ranking_sources,),
        )

        return cursor.rowcount


# Insère les Elo avant et après match dans ml_national.team_rankings.
def insert_match_elo_rankings(
    connection: psycopg.Connection,
    updates: list[EloMatchUpdate],
    ranking_source: str,
) -> int:
    inserted_rows = 0

    with connection.cursor() as cursor:
        for update in updates:
            ranking_date = update.match_date_utc.date()

            rows_to_insert = [
                {
                    "team_name": update.team_a_name,
                    "ranking_source": f"{ranking_source}_before_match",
                    "rating_value": update.team_a_elo_before,
                    "metadata": {
                        "clean_match_id": update.clean_match_id,
                        "team_side": "TEAM_A",
                        "opponent": update.team_b_name,
                        "competition_code": update.competition_code,
                        "season": update.season,
                        "result_1x2": update.result_1x2,
                        "elo_gap_before": update.elo_gap_before,
                        "expected_score": update.team_a_expected_score,
                        "actual_score": update.team_a_actual_score,
                        "k_factor": update.k_factor,
                        "host_advantage_side": update.host_advantage_side,
                        "is_neutral_venue": update.is_neutral_venue,
                    },
                },
                {
                    "team_name": update.team_b_name,
                    "ranking_source": f"{ranking_source}_before_match",
                    "rating_value": update.team_b_elo_before,
                    "metadata": {
                        "clean_match_id": update.clean_match_id,
                        "team_side": "TEAM_B",
                        "opponent": update.team_a_name,
                        "competition_code": update.competition_code,
                        "season": update.season,
                        "result_1x2": update.result_1x2,
                        "elo_gap_before": -update.elo_gap_before,
                        "expected_score": update.team_b_expected_score,
                        "actual_score": update.team_b_actual_score,
                        "k_factor": update.k_factor,
                        "host_advantage_side": update.host_advantage_side,
                        "is_neutral_venue": update.is_neutral_venue,
                    },
                },
                {
                    "team_name": update.team_a_name,
                    "ranking_source": f"{ranking_source}_after_match",
                    "rating_value": update.team_a_elo_after,
                    "metadata": {
                        "clean_match_id": update.clean_match_id,
                        "team_side": "TEAM_A",
                        "opponent": update.team_b_name,
                        "competition_code": update.competition_code,
                        "season": update.season,
                        "result_1x2": update.result_1x2,
                        "rating_delta": update.team_a_elo_after - update.team_a_elo_before,
                        "k_factor": update.k_factor,
                        "host_advantage_side": update.host_advantage_side,
                        "is_neutral_venue": update.is_neutral_venue,
                    },
                },
                {
                    "team_name": update.team_b_name,
                    "ranking_source": f"{ranking_source}_after_match",
                    "rating_value": update.team_b_elo_after,
                    "metadata": {
                        "clean_match_id": update.clean_match_id,
                        "team_side": "TEAM_B",
                        "opponent": update.team_a_name,
                        "competition_code": update.competition_code,
                        "season": update.season,
                        "result_1x2": update.result_1x2,
                        "rating_delta": update.team_b_elo_after - update.team_b_elo_before,
                        "k_factor": update.k_factor,
                        "host_advantage_side": update.host_advantage_side,
                        "is_neutral_venue": update.is_neutral_venue,
                    },
                },
            ]

            for row in rows_to_insert:
                cursor.execute(
                    """
                    INSERT INTO ml_national.team_rankings (
                        team_name,
                        ranking_source,
                        ranking_date,
                        rank_position,
                        rating_value,
                        metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (team_name, ranking_source, ranking_date)
                    DO UPDATE SET
                        rank_position = EXCLUDED.rank_position,
                        rating_value = EXCLUDED.rating_value,
                        metadata = EXCLUDED.metadata,
                        created_at = NOW()
                    """,
                    (
                        row["team_name"],
                        row["ranking_source"],
                        ranking_date,
                        None,
                        round(row["rating_value"], 3),
                        Jsonb(row["metadata"]),
                    ),
                )

                inserted_rows += 1

    return inserted_rows


# Insère le classement final des sélections après le dernier match traité.
def insert_latest_elo_rankings(
    connection: psycopg.Connection,
    final_ratings: dict[str, float],
    matches_played_by_team: dict[str, int],
    ranking_source: str,
    ranking_date: date,
    initial_elo: float,
) -> int:
    sorted_rankings = sorted(
        final_ratings.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    inserted_rows = 0

    with connection.cursor() as cursor:
        for rank_position, (team_name, rating_value) in enumerate(sorted_rankings, start=1):
            cursor.execute(
                """
                INSERT INTO ml_national.team_rankings (
                    team_name,
                    ranking_source,
                    ranking_date,
                    rank_position,
                    rating_value,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (team_name, ranking_source, ranking_date)
                DO UPDATE SET
                    rank_position = EXCLUDED.rank_position,
                    rating_value = EXCLUDED.rating_value,
                    metadata = EXCLUDED.metadata,
                    created_at = NOW()
                """,
                (
                    team_name,
                    f"{ranking_source}_latest",
                    ranking_date,
                    rank_position,
                    round(rating_value, 3),
                    Jsonb(
                        {
                            "ranking_type": "latest_snapshot",
                            "matches_played": matches_played_by_team.get(team_name, 0),
                            "initial_elo_reference": initial_elo,
                        }
                    ),
                ),
            )

            inserted_rows += 1

    return inserted_rows


# Crée le dossier de preuves ML si nécessaire.
def ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# Exporte un CSV avec le classement final Elo.
def export_final_rankings_csv(
    final_ratings: dict[str, float],
    matches_played_by_team: dict[str, int],
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / FINAL_RANKINGS_FILENAME

    sorted_rankings = sorted(
        final_ratings.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["rank", "team_name", "elo_rating", "matches_played"])

        for rank_position, (team_name, rating_value) in enumerate(sorted_rankings, start=1):
            writer.writerow(
                [
                    rank_position,
                    team_name,
                    round(rating_value, 3),
                    matches_played_by_team.get(team_name, 0),
                ]
            )

    return output_path


# Exporte un CSV détaillant les évolutions Elo match par match.
def export_match_updates_csv(updates: list[EloMatchUpdate]) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / MATCH_UPDATES_FILENAME

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
                "result_1x2",
                "team_a_elo_before",
                "team_b_elo_before",
                "elo_gap_before",
                "team_a_elo_after",
                "team_b_elo_after",
                "k_factor",
                "host_advantage_side",
                "is_neutral_venue",
            ]
        )

        for update in updates:
            writer.writerow(
                [
                    update.clean_match_id,
                    update.match_date_utc.isoformat(),
                    update.competition_code,
                    update.season,
                    update.team_a_name,
                    update.team_b_name,
                    update.result_1x2,
                    round(update.team_a_elo_before, 3),
                    round(update.team_b_elo_before, 3),
                    round(update.elo_gap_before, 3),
                    round(update.team_a_elo_after, 3),
                    round(update.team_b_elo_after, 3),
                    round(update.k_factor, 3),
                    update.host_advantage_side,
                    update.is_neutral_venue,
                ]
            )

    return output_path


# Produit un résumé texte exploitable comme preuve RNCP.
def export_summary_txt(
    matches: list[dict],
    updates: list[EloMatchUpdate],
    final_ratings: dict[str, float],
    deleted_rows: int,
    inserted_match_rows: int,
    inserted_latest_rows: int,
    final_rankings_path: Path,
    match_updates_path: Path,
    args: argparse.Namespace,
) -> Path:
    ensure_evidence_directory()
    output_path = EVIDENCE_DIR / SUMMARY_FILENAME

    competition_counts = Counter(match.get("competition_code") for match in matches)
    host_counts = Counter(update.host_advantage_side for update in updates)

    first_date = updates[0].match_date_utc.date() if updates else "N/A"
    last_date = updates[-1].match_date_utc.date() if updates else "N/A"

    sorted_rankings = sorted(final_ratings.items(), key=lambda item: item[1], reverse=True)
    top_rankings = sorted_rankings[:10]

    lines = [
        "OK - Elo national RubyBets calculé.",
        f"Matchs traités : {len(updates)}",
        f"Équipes détectées : {len(final_ratings)}",
        f"Première date : {first_date}",
        f"Dernière date : {last_date}",
        f"Elo initial : {args.initial_elo}",
        f"K factor WC : {args.wc_k_factor}",
        f"K factor WCQ : {args.wcq_k_factor}",
        f"Bonus contexte hôte : {args.host_advantage_elo}",
        f"Anciennes lignes Elo supprimées : {deleted_rows}",
        f"Lignes Elo match insérées/mises à jour : {inserted_match_rows}",
        f"Lignes Elo latest insérées/mises à jour : {inserted_latest_rows}",
        "Table cible : ml_national.team_rankings",
        f"CSV classement final : {final_rankings_path}",
        f"CSV évolutions match : {match_updates_path}",
        "",
        "Répartition par compétition :",
    ]

    for competition_code, count in competition_counts.items():
        lines.append(f"- {competition_code}: {count}")

    lines.extend(["", "Répartition contexte hôte utilisé :"])

    for host_side, count in host_counts.items():
        lines.append(f"- {host_side}: {count}")

    lines.extend(["", "Top 10 Elo final :"])

    for rank_position, (team_name, rating_value) in enumerate(top_rankings, start=1):
        lines.append(f"{rank_position}. {team_name}: {round(rating_value, 3)}")

    lines.extend(
        [
            "",
            "Décision technique :",
            "- Le calcul reste séparé du pipeline club V17.8.",
            "- Le script utilise Team A / Team B et non un domicile/extérieur club classique.",
            "- Le contexte hôte est pris en compte uniquement via host_advantage_side.",
            "- Les valeurs produites préparent la future feature elo_gap dans ml_national.features.",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# Affiche un résumé clair dans le terminal.
def print_summary(
    updates: list[EloMatchUpdate],
    final_ratings: dict[str, float],
    summary_path: Path,
    final_rankings_path: Path,
    match_updates_path: Path,
) -> None:
    first_date = updates[0].match_date_utc.date() if updates else "N/A"
    last_date = updates[-1].match_date_utc.date() if updates else "N/A"

    print("OK - Elo national RubyBets calculé.")
    print(f"Matchs traités : {len(updates)}")
    print(f"Équipes détectées : {len(final_ratings)}")
    print(f"Première date : {first_date}")
    print(f"Dernière date : {last_date}")
    print("Table mise à jour : ml_national.team_rankings")
    print(f"Résumé sauvegardé : {summary_path}")
    print(f"Classement final sauvegardé : {final_rankings_path}")
    print(f"Évolutions match sauvegardées : {match_updates_path}")


# Exécute le calcul Elo national complet.
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
                matches = fetch_clean_matches(
                    connection=connection,
                    competition_codes=competition_codes,
                )

                if not matches:
                    raise ValueError(
                        "Aucun match national terminé trouvé dans ml_national.clean_matches"
                    )

                updates, final_ratings, matches_played_by_team = build_elo_updates(
                    matches=matches,
                    initial_elo=args.initial_elo,
                    wc_k_factor=args.wc_k_factor,
                    wcq_k_factor=args.wcq_k_factor,
                    host_advantage_elo=args.host_advantage_elo,
                )

                deleted_rows = delete_existing_elo_rankings(
                    connection=connection,
                    ranking_source=args.ranking_source,
                )

                inserted_match_rows = insert_match_elo_rankings(
                    connection=connection,
                    updates=updates,
                    ranking_source=args.ranking_source,
                )

                inserted_latest_rows = insert_latest_elo_rankings(
                    connection=connection,
                    final_ratings=final_ratings,
                    matches_played_by_team=matches_played_by_team,
                    ranking_source=args.ranking_source,
                    ranking_date=updates[-1].match_date_utc.date(),
                    initial_elo=args.initial_elo,
                )

        final_rankings_path = export_final_rankings_csv(
            final_ratings=final_ratings,
            matches_played_by_team=matches_played_by_team,
        )

        match_updates_path = export_match_updates_csv(updates=updates)

        summary_path = export_summary_txt(
            matches=matches,
            updates=updates,
            final_ratings=final_ratings,
            deleted_rows=deleted_rows,
            inserted_match_rows=inserted_match_rows,
            inserted_latest_rows=inserted_latest_rows,
            final_rankings_path=final_rankings_path,
            match_updates_path=match_updates_path,
            args=args,
        )

        print_summary(
            updates=updates,
            final_ratings=final_ratings,
            summary_path=summary_path,
            final_rankings_path=final_rankings_path,
            match_updates_path=match_updates_path,
        )

    except Exception as error:
        print("Erreur pendant le calcul Elo national.")
        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication :
# ml_national.clean_matches
#        ↓
# backend/scripts/ml_national/build_national_elo_ratings.py
#        ↓
# ml_national.team_rankings
#        ↓
# reports/evidence/ml_training/
#        ↓
# futur backend/scripts/ml_national/build_national_features.py