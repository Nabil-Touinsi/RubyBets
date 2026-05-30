# Role du fichier :
# Ce script audite les events StatsBomb telecharges pour verifier si les donnees event-level
# peuvent enrichir les futurs modeles nationaux OVER_1_5, OVER_2_5 et BTTS.

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]

STATSBOMB_DIR = ROOT_DIR / "data" / "external" / "statsbomb_open_data"
COMPETITIONS_FILE = STATSBOMB_DIR / "data" / "competitions.json"
MATCHES_DIR = STATSBOMB_DIR / "data" / "matches"
EVENTS_DIR = STATSBOMB_DIR / "data" / "events"

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"
SUMMARY_FILE = EVIDENCE_DIR / "321_statsbomb_national_events_audit.txt"
CSV_FILE = EVIDENCE_DIR / "322_statsbomb_national_events_features_preview.csv"


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


# Cette fonction recupere les competitions ciblees.
def get_target_competitions(competitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [competition for competition in competitions if is_target_competition(competition)]


# Cette fonction lit les matchs d'une competition/saison StatsBomb.
def load_matches_for_competition(competition_id: int, season_id: int) -> list[dict[str, Any]]:
    match_file = MATCHES_DIR / str(competition_id) / f"{season_id}.json"

    if not match_file.exists():
        return []

    matches = load_json(match_file)

    if not isinstance(matches, list):
        return []

    return matches


# Cette fonction lit les events StatsBomb d'un match.
def load_events_for_match(match_id: int) -> list[dict[str, Any]]:
    event_file = EVENTS_DIR / f"{match_id}.json"

    if not event_file.exists():
        return []

    events = load_json(event_file)

    if not isinstance(events, list):
        return []

    return events


# Cette fonction recupere proprement le nom d'une equipe depuis un match StatsBomb.
def get_team_name(match: dict[str, Any], side: str) -> str:
    team = match.get(side)

    if isinstance(team, dict):
        return str(team.get(f"{side}_name", team.get("name", "")))

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

    return (
        outcome_name == "goal"
        or "saved" in outcome_name
        or outcome_name == "saved to post"
    )


# Cette fonction extrait le xG d'un tir StatsBomb.
def get_shot_xg(shot_event: dict[str, Any]) -> float:
    shot = shot_event.get("shot", {})

    if not isinstance(shot, dict):
        return 0.0

    raw_xg = shot.get("statsbomb_xg", 0.0)

    try:
        return float(raw_xg)
    except (TypeError, ValueError):
        return 0.0


# Cette fonction compte les tirs, tirs cadres et xG d'une equipe dans un match.
def compute_team_event_stats(events: list[dict[str, Any]], team_name: str) -> dict[str, float | int]:
    shots = 0
    shots_on_target = 0
    xg = 0.0

    for event in events:
        event_type = event.get("type", {})
        event_team = event.get("team", {})

        if not isinstance(event_type, dict) or not isinstance(event_team, dict):
            continue

        event_type_name = event_type.get("name")
        event_team_name = event_team.get("name")

        if event_type_name != "Shot":
            continue

        if event_team_name != team_name:
            continue

        shots += 1
        xg += get_shot_xg(event)

        if is_shot_on_target(event):
            shots_on_target += 1

    return {
        "shots": shots,
        "shots_on_target": shots_on_target,
        "xg": round(xg, 4),
    }


# Cette fonction compte les types d'events presents dans les fichiers audites.
def count_event_types(events: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()

    for event in events:
        event_type = event.get("type", {})

        if isinstance(event_type, dict):
            event_type_name = str(event_type.get("name", "UNKNOWN"))
            counter[event_type_name] += 1

    return counter


# Cette fonction construit les lignes de preview par match.
def build_event_feature_rows(target_competitions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    global_event_type_counter: Counter[str] = Counter()

    total_matches = 0
    matches_with_events = 0
    missing_event_files = 0
    total_events = 0
    total_shots = 0
    shots_with_xg = 0

    for competition in target_competitions:
        competition_id = int(competition.get("competition_id"))
        season_id = int(competition.get("season_id"))
        competition_name = str(competition.get("competition_name", ""))
        season_name = str(competition.get("season_name", ""))

        matches = load_matches_for_competition(competition_id, season_id)

        for match in matches:
            total_matches += 1

            match_id = int(match.get("match_id"))
            match_date = str(match.get("match_date", ""))

            team_a_name = get_team_name(match, "home_team")
            team_b_name = get_team_name(match, "away_team")

            team_a_score = match.get("home_score")
            team_b_score = match.get("away_score")

            events = load_events_for_match(match_id)

            if not events:
                missing_event_files += 1
                continue

            matches_with_events += 1
            total_events += len(events)

            event_type_counter = count_event_types(events)
            global_event_type_counter.update(event_type_counter)

            shot_events = [
                event for event in events
                if isinstance(event.get("type"), dict)
                and event.get("type", {}).get("name") == "Shot"
            ]

            total_shots += len(shot_events)

            for shot_event in shot_events:
                shot = shot_event.get("shot", {})
                if isinstance(shot, dict) and shot.get("statsbomb_xg") is not None:
                    shots_with_xg += 1

            team_a_stats = compute_team_event_stats(events, team_a_name)
            team_b_stats = compute_team_event_stats(events, team_b_name)

            total_goals = int(team_a_score) + int(team_b_score)
            target_over_1_5 = total_goals >= 2
            target_over_2_5 = total_goals >= 3
            target_btts = int(team_a_score) > 0 and int(team_b_score) > 0

            rows.append(
                {
                    "match_id": match_id,
                    "competition_name": competition_name,
                    "season_name": season_name,
                    "match_date": match_date,
                    "team_a_name": team_a_name,
                    "team_b_name": team_b_name,
                    "team_a_score": team_a_score,
                    "team_b_score": team_b_score,
                    "target_over_1_5": target_over_1_5,
                    "target_over_2_5": target_over_2_5,
                    "target_btts": target_btts,
                    "team_a_shots": team_a_stats["shots"],
                    "team_b_shots": team_b_stats["shots"],
                    "team_a_shots_on_target": team_a_stats["shots_on_target"],
                    "team_b_shots_on_target": team_b_stats["shots_on_target"],
                    "team_a_xg": team_a_stats["xg"],
                    "team_b_xg": team_b_stats["xg"],
                    "event_count": len(events),
                    "shot_event_count": len(shot_events),
                }
            )

    audit_stats = {
        "total_matches": total_matches,
        "matches_with_events": matches_with_events,
        "missing_event_files": missing_event_files,
        "total_events": total_events,
        "total_shots": total_shots,
        "shots_with_xg": shots_with_xg,
        "global_event_type_counter": global_event_type_counter,
    }

    return rows, audit_stats


# Cette fonction sauvegarde le CSV de preview des features event-level.
def save_features_preview_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "match_id",
        "competition_name",
        "season_name",
        "match_date",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "target_over_1_5",
        "target_over_2_5",
        "target_btts",
        "team_a_shots",
        "team_b_shots",
        "team_a_shots_on_target",
        "team_b_shots_on_target",
        "team_a_xg",
        "team_b_xg",
        "event_count",
        "shot_event_count",
    ]

    with CSV_FILE.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction sauvegarde la synthese texte de l'audit events.
def save_summary(
    target_competitions: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    audit_stats: dict[str, Any],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    total_rows = len(rows)
    over_1_5_count = sum(1 for row in rows if row["target_over_1_5"] is True)
    over_2_5_count = sum(1 for row in rows if row["target_over_2_5"] is True)
    btts_count = sum(1 for row in rows if row["target_btts"] is True)

    total_shots = int(audit_stats["total_shots"])
    shots_with_xg = int(audit_stats["shots_with_xg"])
    xg_coverage = round(shots_with_xg / total_shots, 4) if total_shots else 0.0

    event_type_counter: Counter[str] = audit_stats["global_event_type_counter"]

    lines = [
        "RubyBets - Audit events StatsBomb nationaux",
        "",
        f"Source locale analysee : {STATSBOMB_DIR}",
        f"Dossier events : {EVENTS_DIR}",
        "",
        "Objectif :",
        "Verifier si les events StatsBomb telecharges permettent de creer des features utiles",
        "pour enrichir les futurs modeles nationaux OVER_1_5, OVER_2_5 et BTTS.",
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
            "Resultats globaux :",
            f"- Matchs cibles attendus : {audit_stats['total_matches']}",
            f"- Matchs avec events disponibles : {audit_stats['matches_with_events']}",
            f"- Matchs sans fichier events : {audit_stats['missing_event_files']}",
            f"- Lignes de preview generees : {total_rows}",
            f"- Total events lus : {audit_stats['total_events']}",
            f"- Total tirs detectes : {total_shots}",
            f"- Tirs avec xG StatsBomb : {shots_with_xg}",
            f"- Couverture xG sur les tirs : {xg_coverage}",
            "",
            "Distribution des targets sur les matchs audites :",
            f"- OVER_1_5 : {over_1_5_count} / {total_rows}",
            f"- OVER_2_5 : {over_2_5_count} / {total_rows}",
            f"- BTTS : {btts_count} / {total_rows}",
            "",
            "Top types d'events detectes :",
        ]
    )

    for event_name, count in event_type_counter.most_common(20):
        lines.append(f"- {event_name}: {count}")

    lines.extend(
        [
            "",
            "Decision attendue apres lecture :",
            "- Si xG, tirs et tirs cadres sont bien disponibles, on pourra creer une table de features StatsBomb.",
            "- Les features ne devront jamais utiliser les events du match a predire.",
            "- Les variables event-level devront etre transformeées en moyennes historiques avant-match.",
            "- StatsBomb restera un enrichissement qualitatif sur un sous-ensemble, pas le socle principal.",
            "",
            f"CSV preview genere : {CSV_FILE}",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance l'audit complet des events StatsBomb.
def main() -> None:
    competitions = load_json(COMPETITIONS_FILE)

    if not isinstance(competitions, list):
        raise ValueError("Le fichier competitions.json ne contient pas une liste exploitable.")

    target_competitions = get_target_competitions(competitions)
    rows, audit_stats = build_event_feature_rows(target_competitions)

    save_features_preview_csv(rows)
    save_summary(target_competitions, rows, audit_stats)

    print("OK - Audit events StatsBomb nationaux termine.")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"CSV saved: {CSV_FILE}")


if __name__ == "__main__":
    main()


# Schema de communication :
# audit_statsbomb_national_events.py
#   -> lit data/external/statsbomb_open_data/data/competitions.json
#   -> lit data/external/statsbomb_open_data/data/matches/
#   -> lit data/external/statsbomb_open_data/data/events/
#   -> produit reports/evidence/ml_training/321_statsbomb_national_events_audit.txt
#   -> produit reports/evidence/ml_training/322_statsbomb_national_events_features_preview.csv