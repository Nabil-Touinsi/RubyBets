# Role du fichier :
# Ce script construit un dataset match-level StatsBomb pour les competitions nationales ciblees.
# Il extrait les tirs, tirs cadres, xG et targets OVER/BTTS afin de preparer l'enrichissement V18.0.

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]

STATSBOMB_DIR = ROOT_DIR / "data" / "external" / "statsbomb_open_data"
COMPETITIONS_FILE = STATSBOMB_DIR / "data" / "competitions.json"
MATCHES_DIR = STATSBOMB_DIR / "data" / "matches"
EVENTS_DIR = STATSBOMB_DIR / "data" / "events"

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"
SUMMARY_FILE = EVIDENCE_DIR / "323_statsbomb_national_match_event_features_summary.txt"
CSV_FILE = EVIDENCE_DIR / "324_statsbomb_national_match_event_features.csv"


TARGET_COMPETITIONS = [
    ("FIFA World Cup", "2018"),
    ("FIFA World Cup", "2022"),
    ("UEFA Euro", "2020"),
    ("UEFA Euro", "2024"),
    ("Copa America", "2024"),
]


# Cette fonction charge un fichier JSON local.
def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# Cette fonction verifie si une competition StatsBomb fait partie du perimetre cible.
def is_target_competition(competition: dict[str, Any]) -> bool:
    competition_name = str(competition.get("competition_name", ""))
    season_name = str(competition.get("season_name", ""))

    return (competition_name, season_name) in TARGET_COMPETITIONS


# Cette fonction retourne uniquement les competitions ciblees.
def get_target_competitions(competitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [competition for competition in competitions if is_target_competition(competition)]


# Cette fonction charge les matchs d'une competition/saison.
def load_matches_for_competition(competition_id: int, season_id: int) -> list[dict[str, Any]]:
    match_file = MATCHES_DIR / str(competition_id) / f"{season_id}.json"

    if not match_file.exists():
        return []

    matches = load_json(match_file)

    if not isinstance(matches, list):
        return []

    return matches


# Cette fonction charge les events d'un match.
def load_events_for_match(match_id: int) -> list[dict[str, Any]]:
    event_file = EVENTS_DIR / f"{match_id}.json"

    if not event_file.exists():
        return []

    events = load_json(event_file)

    if not isinstance(events, list):
        return []

    return events


# Cette fonction recupere le nom d'une equipe depuis un objet match StatsBomb.
def get_team_name(match: dict[str, Any], side: str) -> str:
    team = match.get(side)

    if isinstance(team, dict):
        return str(team.get(f"{side}_name", team.get("name", "")))

    return ""


# Cette fonction extrait le nom du stade si disponible.
def get_stadium_name(match: dict[str, Any]) -> str:
    stadium = match.get("stadium")

    if isinstance(stadium, dict):
        return str(stadium.get("name", ""))

    return ""


# Cette fonction extrait le pays du stade si disponible.
def get_stadium_country(match: dict[str, Any]) -> str:
    stadium = match.get("stadium")

    if isinstance(stadium, dict):
        country = stadium.get("country")
        if isinstance(country, dict):
            return str(country.get("name", ""))

    return ""


# Cette fonction determine si un tir est cadre selon l'outcome StatsBomb.
def is_shot_on_target(shot_event: dict[str, Any]) -> bool:
    shot = shot_event.get("shot", {})

    if not isinstance(shot, dict):
        return False

    outcome = shot.get("outcome", {})

    if not isinstance(outcome, dict):
        return False

    outcome_name = str(outcome.get("name", "")).lower()

    return outcome_name == "goal" or "saved" in outcome_name


# Cette fonction determine si un tir est un but selon l'outcome StatsBomb.
def is_goal_shot(shot_event: dict[str, Any]) -> bool:
    shot = shot_event.get("shot", {})

    if not isinstance(shot, dict):
        return False

    outcome = shot.get("outcome", {})

    if not isinstance(outcome, dict):
        return False

    return str(outcome.get("name", "")).lower() == "goal"


# Cette fonction extrait le xG StatsBomb d'un tir.
def get_shot_xg(shot_event: dict[str, Any]) -> float:
    shot = shot_event.get("shot", {})

    if not isinstance(shot, dict):
        return 0.0

    raw_xg = shot.get("statsbomb_xg", 0.0)

    try:
        return float(raw_xg)
    except (TypeError, ValueError):
        return 0.0


# Cette fonction calcule les stats offensives d'une equipe sur un match.
def compute_team_stats(events: list[dict[str, Any]], team_name: str) -> dict[str, float | int]:
    shots = 0
    shots_on_target = 0
    goals_from_shots = 0
    xg = 0.0

    for event in events:
        event_type = event.get("type", {})
        event_team = event.get("team", {})

        if not isinstance(event_type, dict) or not isinstance(event_team, dict):
            continue

        if event_type.get("name") != "Shot":
            continue

        if event_team.get("name") != team_name:
            continue

        shots += 1
        xg += get_shot_xg(event)

        if is_shot_on_target(event):
            shots_on_target += 1

        if is_goal_shot(event):
            goals_from_shots += 1

    shot_accuracy = round(shots_on_target / shots, 4) if shots else 0.0
    xg_per_shot = round(xg / shots, 4) if shots else 0.0

    return {
        "shots": shots,
        "shots_on_target": shots_on_target,
        "goals_from_shots": goals_from_shots,
        "xg": round(xg, 4),
        "shot_accuracy": shot_accuracy,
        "xg_per_shot": xg_per_shot,
    }


# Cette fonction construit une ligne match-level exploitable.
def build_match_row(
    competition: dict[str, Any],
    match: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    match_id = int(match.get("match_id"))
    match_date = str(match.get("match_date", ""))

    team_a_name = get_team_name(match, "home_team")
    team_b_name = get_team_name(match, "away_team")

    team_a_score = int(match.get("home_score", 0))
    team_b_score = int(match.get("away_score", 0))
    total_goals = team_a_score + team_b_score

    team_a_stats = compute_team_stats(events, team_a_name)
    team_b_stats = compute_team_stats(events, team_b_name)

    return {
        "statsbomb_match_id": match_id,
        "competition_id": competition.get("competition_id"),
        "season_id": competition.get("season_id"),
        "competition_name": competition.get("competition_name", ""),
        "season_name": competition.get("season_name", ""),
        "country_name": competition.get("country_name", ""),
        "match_date": match_date,
        "stadium_name": get_stadium_name(match),
        "stadium_country": get_stadium_country(match),
        "team_a_name": team_a_name,
        "team_b_name": team_b_name,
        "team_a_score": team_a_score,
        "team_b_score": team_b_score,
        "total_goals": total_goals,
        "target_over_1_5": total_goals >= 2,
        "target_over_2_5": total_goals >= 3,
        "target_btts": team_a_score > 0 and team_b_score > 0,
        "team_a_shots": team_a_stats["shots"],
        "team_b_shots": team_b_stats["shots"],
        "team_a_shots_on_target": team_a_stats["shots_on_target"],
        "team_b_shots_on_target": team_b_stats["shots_on_target"],
        "team_a_goals_from_shots": team_a_stats["goals_from_shots"],
        "team_b_goals_from_shots": team_b_stats["goals_from_shots"],
        "team_a_xg": team_a_stats["xg"],
        "team_b_xg": team_b_stats["xg"],
        "team_a_shot_accuracy": team_a_stats["shot_accuracy"],
        "team_b_shot_accuracy": team_b_stats["shot_accuracy"],
        "team_a_xg_per_shot": team_a_stats["xg_per_shot"],
        "team_b_xg_per_shot": team_b_stats["xg_per_shot"],
        "match_shots_total": int(team_a_stats["shots"]) + int(team_b_stats["shots"]),
        "match_xg_total": round(float(team_a_stats["xg"]) + float(team_b_stats["xg"]), 4),
        "event_count": len(events),
    }


# Cette fonction construit toutes les lignes match-level.
def build_match_event_features(target_competitions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    rows = []
    missing_events = 0

    for competition in target_competitions:
        competition_id = int(competition.get("competition_id"))
        season_id = int(competition.get("season_id"))

        matches = load_matches_for_competition(competition_id, season_id)

        for match in matches:
            match_id = int(match.get("match_id"))
            events = load_events_for_match(match_id)

            if not events:
                missing_events += 1
                continue

            rows.append(build_match_row(competition, match, events))

    rows = sorted(
        rows,
        key=lambda row: (
            str(row["match_date"]),
            str(row["competition_name"]),
            int(row["statsbomb_match_id"]),
        ),
    )

    return rows, missing_events


# Cette fonction sauvegarde le CSV match-level.
def save_features_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "statsbomb_match_id",
        "competition_id",
        "season_id",
        "competition_name",
        "season_name",
        "country_name",
        "match_date",
        "stadium_name",
        "stadium_country",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "total_goals",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "team_a_shots",
        "team_b_shots",
        "team_a_shots_on_target",
        "team_b_shots_on_target",
        "team_a_goals_from_shots",
        "team_b_goals_from_shots",
        "team_a_xg",
        "team_b_xg",
        "team_a_shot_accuracy",
        "team_b_shot_accuracy",
        "team_a_xg_per_shot",
        "team_b_xg_per_shot",
        "match_shots_total",
        "match_xg_total",
        "event_count",
    ]

    with CSV_FILE.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction calcule un ratio securise.
def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0

    return round(float(numerator) / float(denominator), 4)


# Cette fonction sauvegarde la synthese texte du dataset produit.
def save_summary(
    target_competitions: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    missing_events: int,
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    total_rows = len(rows)
    over_1_5_count = sum(1 for row in rows if row["target_over_1_5"] is True)
    over_2_5_count = sum(1 for row in rows if row["target_over_2_5"] is True)
    btts_count = sum(1 for row in rows if row["target_btts"] is True)

    total_shots = sum(int(row["match_shots_total"]) for row in rows)
    total_xg = round(sum(float(row["match_xg_total"]) for row in rows), 4)

    competition_counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['competition_name']} {row['season_name']}"
        competition_counts[key] = competition_counts.get(key, 0) + 1

    lines = [
        "RubyBets - Construction dataset match-level StatsBomb national",
        "",
        f"Source locale : {STATSBOMB_DIR}",
        f"Fichier genere : {CSV_FILE}",
        "",
        "Objectif :",
        "Construire un dataset match-level propre a partir des events StatsBomb",
        "pour preparer l'enrichissement des futurs modeles nationaux OVER_1_5, OVER_2_5 et BTTS.",
        "",
        "Important :",
        "Ce fichier contient les statistiques du match lui-meme.",
        "Il ne doit pas etre utilise directement pour predire ce meme match.",
        "La prochaine etape devra transformer ces valeurs en moyennes historiques avant-match.",
        "",
        "Competitions ciblees :",
    ]

    for competition in target_competitions:
        lines.append(
            "- "
            f"{competition.get('competition_name')} | "
            f"{competition.get('season_name')} | "
            f"competition_id={competition.get('competition_id')} | "
            f"season_id={competition.get('season_id')}"
        )

    lines.extend(
        [
            "",
            "Resultats generaux :",
            f"- Lignes match-level generees : {total_rows}",
            f"- Matchs sans events ignores : {missing_events}",
            f"- Total tirs : {total_shots}",
            f"- Total xG : {total_xg}",
            "",
            "Distribution des targets :",
            f"- OVER_1_5 : {over_1_5_count} / {total_rows} ({safe_ratio(over_1_5_count, total_rows)})",
            f"- OVER_2_5 : {over_2_5_count} / {total_rows} ({safe_ratio(over_2_5_count, total_rows)})",
            f"- BTTS : {btts_count} / {total_rows} ({safe_ratio(btts_count, total_rows)})",
            "",
            "Repartition par competition :",
        ]
    )

    for competition_key, count in sorted(competition_counts.items()):
        lines.append(f"- {competition_key}: {count}")

    lines.extend(
        [
            "",
            "Decision :",
            "- Dataset match-level StatsBomb pret pour la phase suivante.",
            "- Prochaine etape : creer des features rolling anti-fuite.",
            "- Exemple : team_a_xg_for_last_5 doit utiliser uniquement les matchs precedents de Team A.",
            "- StatsBomb reste un enrichissement qualitatif sur sous-ensemble, pas le socle principal Kaggle.",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance la construction complete du dataset match-level.
def main() -> None:
    competitions = load_json(COMPETITIONS_FILE)

    if not isinstance(competitions, list):
        raise ValueError("Le fichier competitions.json ne contient pas une liste exploitable.")

    target_competitions = get_target_competitions(competitions)
    rows, missing_events = build_match_event_features(target_competitions)

    save_features_csv(rows)
    save_summary(target_competitions, rows, missing_events)

    print("OK - Dataset match-level StatsBomb national genere.")
    print(f"Rows: {len(rows)}")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"CSV saved: {CSV_FILE}")


if __name__ == "__main__":
    main()


# Schema de communication :
# build_statsbomb_national_match_event_features.py
#   -> lit data/external/statsbomb_open_data/data/competitions.json
#   -> lit data/external/statsbomb_open_data/data/matches/
#   -> lit data/external/statsbomb_open_data/data/events/
#   -> produit reports/evidence/ml_training/323_statsbomb_national_match_event_features_summary.txt
#   -> produit reports/evidence/ml_training/324_statsbomb_national_match_event_features.csv