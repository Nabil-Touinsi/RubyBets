# Role du fichier :
# Ce script transforme le dataset match-level StatsBomb en features rolling anti-fuite.
# Pour chaque match, il calcule les moyennes historiques des equipes uniquement avec leurs matchs precedents.

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"

INPUT_CSV = EVIDENCE_DIR / "324_statsbomb_national_match_event_features.csv"
SUMMARY_FILE = EVIDENCE_DIR / "325_statsbomb_national_rolling_features_summary.txt"
OUTPUT_CSV = EVIDENCE_DIR / "326_statsbomb_national_rolling_features.csv"

ROLLING_WINDOW = 5


# Cette fonction convertit une valeur en entier de maniere securisee.
def to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# Cette fonction convertit une valeur en float de maniere securisee.
def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# Cette fonction convertit une valeur texte CSV en booleen.
def to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


# Cette fonction charge le CSV match-level StatsBomb.
def load_match_level_rows() -> list[dict[str, Any]]:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Fichier introuvable : {INPUT_CSV}")

    with INPUT_CSV.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("match_date", "")),
            str(row.get("competition_name", "")),
            to_int(row.get("statsbomb_match_id")),
        ),
    )

    return rows


# Cette fonction calcule une moyenne securisee sur une liste de valeurs.
def average(values: list[float]) -> float:
    if not values:
        return 0.0

    return round(sum(values) / len(values), 4)


# Cette fonction extrait les derniers matchs connus d'une equipe.
def get_recent_team_history(
    team_history: dict[str, list[dict[str, float]]],
    team_name: str,
    window: int,
) -> list[dict[str, float]]:
    history = team_history.get(team_name, [])
    return history[-window:]


# Cette fonction calcule les features rolling d'une equipe avant le match courant.
def compute_rolling_features(
    team_history: dict[str, list[dict[str, float]]],
    team_name: str,
    prefix: str,
) -> dict[str, float | int]:
    recent_matches = get_recent_team_history(team_history, team_name, ROLLING_WINDOW)

    xg_for_values = [match["xg_for"] for match in recent_matches]
    xg_against_values = [match["xg_against"] for match in recent_matches]
    shots_for_values = [match["shots_for"] for match in recent_matches]
    shots_against_values = [match["shots_against"] for match in recent_matches]
    shots_on_target_for_values = [match["shots_on_target_for"] for match in recent_matches]
    shots_on_target_against_values = [match["shots_on_target_against"] for match in recent_matches]
    goals_for_values = [match["goals_for"] for match in recent_matches]
    goals_against_values = [match["goals_against"] for match in recent_matches]

    xg_for = average(xg_for_values)
    xg_against = average(xg_against_values)
    shots_for = average(shots_for_values)
    shots_against = average(shots_against_values)
    shots_on_target_for = average(shots_on_target_for_values)
    shots_on_target_against = average(shots_on_target_against_values)
    goals_for = average(goals_for_values)
    goals_against = average(goals_against_values)

    return {
        f"{prefix}_statsbomb_history_count": len(team_history.get(team_name, [])),
        f"{prefix}_statsbomb_matches_used_last_5": len(recent_matches),
        f"{prefix}_xg_for_last_5": xg_for,
        f"{prefix}_xg_against_last_5": xg_against,
        f"{prefix}_xg_diff_last_5": round(xg_for - xg_against, 4),
        f"{prefix}_shots_for_last_5": shots_for,
        f"{prefix}_shots_against_last_5": shots_against,
        f"{prefix}_shots_diff_last_5": round(shots_for - shots_against, 4),
        f"{prefix}_shots_on_target_for_last_5": shots_on_target_for,
        f"{prefix}_shots_on_target_against_last_5": shots_on_target_against,
        f"{prefix}_shots_on_target_diff_last_5": round(
            shots_on_target_for - shots_on_target_against,
            4,
        ),
        f"{prefix}_goals_for_last_5": goals_for,
        f"{prefix}_goals_against_last_5": goals_against,
        f"{prefix}_goals_diff_last_5": round(goals_for - goals_against, 4),
    }


# Cette fonction ajoute le match courant dans l'historique d'une equipe apres calcul des features.
def update_team_history(
    team_history: dict[str, list[dict[str, float]]],
    team_name: str,
    xg_for: float,
    xg_against: float,
    shots_for: int,
    shots_against: int,
    shots_on_target_for: int,
    shots_on_target_against: int,
    goals_for: int,
    goals_against: int,
) -> None:
    if team_name not in team_history:
        team_history[team_name] = []

    team_history[team_name].append(
        {
            "xg_for": xg_for,
            "xg_against": xg_against,
            "shots_for": float(shots_for),
            "shots_against": float(shots_against),
            "shots_on_target_for": float(shots_on_target_for),
            "shots_on_target_against": float(shots_on_target_against),
            "goals_for": float(goals_for),
            "goals_against": float(goals_against),
        }
    )


# Cette fonction construit les features rolling anti-fuite pour tous les matchs.
def build_rolling_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    team_history: dict[str, list[dict[str, float]]] = {}
    rolling_rows = []

    for row in rows:
        team_a_name = str(row.get("team_a_name", ""))
        team_b_name = str(row.get("team_b_name", ""))

        team_a_features = compute_rolling_features(team_history, team_a_name, "team_a")
        team_b_features = compute_rolling_features(team_history, team_b_name, "team_b")

        team_a_xg = to_float(row.get("team_a_xg"))
        team_b_xg = to_float(row.get("team_b_xg"))

        team_a_shots = to_int(row.get("team_a_shots"))
        team_b_shots = to_int(row.get("team_b_shots"))

        team_a_shots_on_target = to_int(row.get("team_a_shots_on_target"))
        team_b_shots_on_target = to_int(row.get("team_b_shots_on_target"))

        team_a_score = to_int(row.get("team_a_score"))
        team_b_score = to_int(row.get("team_b_score"))

        rolling_row = {
            "statsbomb_match_id": row.get("statsbomb_match_id"),
            "competition_name": row.get("competition_name"),
            "season_name": row.get("season_name"),
            "country_name": row.get("country_name"),
            "match_date": row.get("match_date"),
            "team_a_name": team_a_name,
            "team_b_name": team_b_name,
            "team_a_score": team_a_score,
            "team_b_score": team_b_score,
            "total_goals": to_int(row.get("total_goals")),
            "target_over_1_5": to_bool(row.get("target_over_1_5")),
            "target_over_2_5": to_bool(row.get("target_over_2_5")),
            "target_btts": to_bool(row.get("target_btts")),
            **team_a_features,
            **team_b_features,
        }

        rolling_rows.append(rolling_row)

        update_team_history(
            team_history=team_history,
            team_name=team_a_name,
            xg_for=team_a_xg,
            xg_against=team_b_xg,
            shots_for=team_a_shots,
            shots_against=team_b_shots,
            shots_on_target_for=team_a_shots_on_target,
            shots_on_target_against=team_b_shots_on_target,
            goals_for=team_a_score,
            goals_against=team_b_score,
        )

        update_team_history(
            team_history=team_history,
            team_name=team_b_name,
            xg_for=team_b_xg,
            xg_against=team_a_xg,
            shots_for=team_b_shots,
            shots_against=team_a_shots,
            shots_on_target_for=team_b_shots_on_target,
            shots_on_target_against=team_a_shots_on_target,
            goals_for=team_b_score,
            goals_against=team_a_score,
        )

    return rolling_rows


# Cette fonction sauvegarde le CSV des features rolling anti-fuite.
def save_rolling_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "statsbomb_match_id",
        "competition_name",
        "season_name",
        "country_name",
        "match_date",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "total_goals",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "team_a_statsbomb_history_count",
        "team_a_statsbomb_matches_used_last_5",
        "team_a_xg_for_last_5",
        "team_a_xg_against_last_5",
        "team_a_xg_diff_last_5",
        "team_a_shots_for_last_5",
        "team_a_shots_against_last_5",
        "team_a_shots_diff_last_5",
        "team_a_shots_on_target_for_last_5",
        "team_a_shots_on_target_against_last_5",
        "team_a_shots_on_target_diff_last_5",
        "team_a_goals_for_last_5",
        "team_a_goals_against_last_5",
        "team_a_goals_diff_last_5",
        "team_b_statsbomb_history_count",
        "team_b_statsbomb_matches_used_last_5",
        "team_b_xg_for_last_5",
        "team_b_xg_against_last_5",
        "team_b_xg_diff_last_5",
        "team_b_shots_for_last_5",
        "team_b_shots_against_last_5",
        "team_b_shots_diff_last_5",
        "team_b_shots_on_target_for_last_5",
        "team_b_shots_on_target_against_last_5",
        "team_b_shots_on_target_diff_last_5",
        "team_b_goals_for_last_5",
        "team_b_goals_against_last_5",
        "team_b_goals_diff_last_5",
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


# Cette fonction sauvegarde la synthese texte des features rolling produites.
def save_summary(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    total_rows = len(rows)

    both_teams_with_history = sum(
        1
        for row in rows
        if to_int(row["team_a_statsbomb_history_count"]) > 0
        and to_int(row["team_b_statsbomb_history_count"]) > 0
    )

    both_teams_with_full_last_5 = sum(
        1
        for row in rows
        if to_int(row["team_a_statsbomb_matches_used_last_5"]) == ROLLING_WINDOW
        and to_int(row["team_b_statsbomb_matches_used_last_5"]) == ROLLING_WINDOW
    )

    over_1_5_count = sum(1 for row in rows if row["target_over_1_5"] is True)
    over_2_5_count = sum(1 for row in rows if row["target_over_2_5"] is True)
    btts_count = sum(1 for row in rows if row["target_btts"] is True)

    competition_counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['competition_name']} {row['season_name']}"
        competition_counts[key] = competition_counts.get(key, 0) + 1

    lines = [
        "RubyBets - Features rolling StatsBomb nationales anti-fuite",
        "",
        f"Source input : {INPUT_CSV}",
        f"Fichier genere : {OUTPUT_CSV}",
        "",
        "Objectif :",
        "Transformer les statistiques event-level StatsBomb en variables historiques avant-match.",
        "Chaque ligne utilise uniquement les matchs precedents de chaque equipe.",
        "",
        "Regle anti-fuite :",
        "Les statistiques du match courant sont ajoutees a l'historique uniquement apres calcul des features.",
        "Le match a predire n'est donc jamais utilise pour construire ses propres variables.",
        "",
        "Resultats generaux :",
        f"- Lignes input : {total_rows}",
        f"- Lignes rolling generees : {total_rows}",
        f"- Fenetre rolling : last_{ROLLING_WINDOW}",
        f"- Matchs avec historique StatsBomb pour les deux equipes : {both_teams_with_history} / {total_rows} ({safe_ratio(both_teams_with_history, total_rows)})",
        f"- Matchs avec 5 matchs precedents pour les deux equipes : {both_teams_with_full_last_5} / {total_rows} ({safe_ratio(both_teams_with_full_last_5, total_rows)})",
        "",
        "Distribution des targets conservees :",
        f"- OVER_1_5 : {over_1_5_count} / {total_rows} ({safe_ratio(over_1_5_count, total_rows)})",
        f"- OVER_2_5 : {over_2_5_count} / {total_rows} ({safe_ratio(over_2_5_count, total_rows)})",
        f"- BTTS : {btts_count} / {total_rows} ({safe_ratio(btts_count, total_rows)})",
        "",
        "Repartition par competition :",
    ]

    for competition_key, count in sorted(competition_counts.items()):
        lines.append(f"- {competition_key}: {count}")

    lines.extend(
        [
            "",
            "Features creees :",
            "- xG for/against last_5",
            "- shots for/against last_5",
            "- shots on target for/against last_5",
            "- goals for/against last_5",
            "- differentiels xG, tirs, tirs cadres et buts",
            "- compte d'historique disponible par equipe",
            "",
            "Decision :",
            "- Les features rolling sont pretes pour un premier test V18.0 StatsBomb.",
            "- Ces features doivent etre utilisees comme enrichissement qualitatif sur sous-ensemble.",
            "- Le socle principal reste Kaggle + Elo car StatsBomb ne couvre que 262 matchs cibles.",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance la construction complete des features rolling.
def main() -> None:
    match_level_rows = load_match_level_rows()
    rolling_rows = build_rolling_rows(match_level_rows)

    save_rolling_csv(rolling_rows)
    save_summary(rolling_rows)

    print("OK - Features rolling StatsBomb nationales generees.")
    print(f"Rows: {len(rolling_rows)}")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"CSV saved: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()


# Schema de communication :
# build_statsbomb_national_rolling_features.py
#   -> lit reports/evidence/ml_training/324_statsbomb_national_match_event_features.csv
#   -> calcule des features rolling anti-fuite avec uniquement les matchs precedents
#   -> produit reports/evidence/ml_training/325_statsbomb_national_rolling_features_summary.txt
#   -> produit reports/evidence/ml_training/326_statsbomb_national_rolling_features.csv