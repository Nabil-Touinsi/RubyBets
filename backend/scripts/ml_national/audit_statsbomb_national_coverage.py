# Role du fichier :
# Ce script audite la couverture nationale disponible dans StatsBomb Open Data
# afin de savoir si cette source peut enrichir plus tard les modeles OVER_1_5 et BTTS.

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]

STATSBOMB_DIR = ROOT_DIR / "data" / "external" / "statsbomb_open_data"
COMPETITIONS_FILE = STATSBOMB_DIR / "data" / "competitions.json"
MATCHES_DIR = STATSBOMB_DIR / "data" / "matches"

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"
SUMMARY_FILE = EVIDENCE_DIR / "319_statsbomb_national_coverage_audit.txt"
CSV_FILE = EVIDENCE_DIR / "320_statsbomb_national_coverage_by_competition.csv"


# Cette fonction charge un fichier JSON local.
def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# Cette fonction identifie les competitions susceptibles de concerner les equipes nationales.
def detect_national_candidate(competition: dict[str, Any]) -> tuple[bool, str]:
    competition_name = str(competition.get("competition_name", "")).lower()
    country_name = str(competition.get("country_name", "")).lower()

    national_keywords = [
        "world cup",
        "fifa",
        "euro",
        "uefa euro",
        "copa america",
        "africa cup",
        "afcon",
        "asian cup",
        "concacaf",
        "nations league",
        "international",
    ]

    if country_name == "international":
        return True, "country_name=International"

    for keyword in national_keywords:
        if keyword in competition_name:
            return True, f"competition_keyword={keyword}"

    return False, "not_detected_as_national"


# Cette fonction lit les matchs StatsBomb disponibles pour une competition/saison.
def load_matches_for_competition(competition_id: int, season_id: int) -> list[dict[str, Any]]:
    match_file = MATCHES_DIR / str(competition_id) / f"{season_id}.json"

    if not match_file.exists():
        return []

    matches = load_json(match_file)

    if not isinstance(matches, list):
        return []

    return matches


# Cette fonction extrait les dates disponibles dans les matchs.
def extract_match_dates(matches: list[dict[str, Any]]) -> tuple[str, str]:
    dates = []

    for match in matches:
        match_date = match.get("match_date")
        if match_date:
            dates.append(str(match_date))

    if not dates:
        return "", ""

    dates = sorted(dates)
    return dates[0], dates[-1]


# Cette fonction construit les lignes d'audit par competition/saison.
def build_coverage_rows(competitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []

    for competition in competitions:
        competition_id = int(competition.get("competition_id"))
        season_id = int(competition.get("season_id"))

        matches = load_matches_for_competition(competition_id, season_id)
        first_date, last_date = extract_match_dates(matches)
        is_national, national_reason = detect_national_candidate(competition)

        rows.append(
            {
                "competition_id": competition_id,
                "season_id": season_id,
                "competition_name": competition.get("competition_name", ""),
                "season_name": competition.get("season_name", ""),
                "country_name": competition.get("country_name", ""),
                "match_file_exists": len(matches) > 0,
                "match_count": len(matches),
                "first_match_date": first_date,
                "last_match_date": last_date,
                "is_national_candidate": is_national,
                "national_reason": national_reason,
            }
        )

    return rows


# Cette fonction sauvegarde le CSV detaille de couverture.
def save_coverage_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "competition_id",
        "season_id",
        "competition_name",
        "season_name",
        "country_name",
        "match_file_exists",
        "match_count",
        "first_match_date",
        "last_match_date",
        "is_national_candidate",
        "national_reason",
    ]

    with CSV_FILE.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction cree la synthese texte de l'audit.
def save_summary(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    total_seasons = len(rows)
    seasons_with_matches = sum(1 for row in rows if row["match_file_exists"])
    total_matches = sum(int(row["match_count"]) for row in rows)

    national_rows = [row for row in rows if row["is_national_candidate"]]
    national_seasons = len(national_rows)
    national_seasons_with_matches = sum(1 for row in national_rows if row["match_file_exists"])
    national_matches = sum(int(row["match_count"]) for row in national_rows)

    top_national_rows = sorted(
        national_rows,
        key=lambda row: int(row["match_count"]),
        reverse=True,
    )

    lines = [
        "RubyBets - Audit couverture StatsBomb Open Data nationale",
        "",
        f"Source locale analysee : {STATSBOMB_DIR}",
        f"Fichier competitions : {COMPETITIONS_FILE}",
        f"Dossier matches : {MATCHES_DIR}",
        "",
        "Objectif :",
        "Verifier si StatsBomb Open Data contient assez de matchs d'equipes nationales",
        "pour enrichir plus tard les modeles nationaux OVER_1_5 et BTTS.",
        "",
        "Important :",
        "Cet audit ne telecharge pas encore les events StatsBomb.",
        "Il controle uniquement la couverture competitions + matches.",
        "Les events seront analyses seulement si la couverture nationale est exploitable.",
        "",
        "Resultats globaux :",
        f"- Competition/seasons referencees : {total_seasons}",
        f"- Competition/seasons avec fichier matches : {seasons_with_matches}",
        f"- Total matchs StatsBomb disponibles dans le sparse checkout : {total_matches}",
        "",
        "Resultats candidats nationaux :",
        f"- Competition/seasons detectees comme nationales : {national_seasons}",
        f"- Competition/seasons nationales avec matchs : {national_seasons_with_matches}",
        f"- Matchs nationaux candidats : {national_matches}",
        "",
        "Top competitions nationales candidates :",
    ]

    if top_national_rows:
        for row in top_national_rows[:20]:
            lines.append(
                "- "
                f"{row['competition_name']} | "
                f"{row['season_name']} | "
                f"{row['country_name']} | "
                f"matchs={row['match_count']} | "
                f"{row['first_match_date']} -> {row['last_match_date']} | "
                f"raison={row['national_reason']}"
            )
    else:
        lines.append("- Aucun candidat national detecte.")

    lines.extend(
        [
            "",
            "Decision attendue apres lecture :",
            "- Si le volume national est suffisant, passer a l'audit des events StatsBomb.",
            "- Si le volume est faible, garder StatsBomb comme enrichissement cible mais ne pas en faire le socle principal.",
            "- Ne pas integrer StatsBomb dans les modeles avant d'avoir verifie l'absence de fuite de donnees.",
            "",
            f"CSV detaille genere : {CSV_FILE}",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance l'audit complet.
def main() -> None:
    competitions = load_json(COMPETITIONS_FILE)

    if not isinstance(competitions, list):
        raise ValueError("Le fichier competitions.json ne contient pas une liste exploitable.")

    rows = build_coverage_rows(competitions)
    save_coverage_csv(rows)
    save_summary(rows)

    print("OK - Audit couverture StatsBomb nationale termine.")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"CSV saved: {CSV_FILE}")


if __name__ == "__main__":
    main()


# Schema de communication :
# audit_statsbomb_national_coverage.py
#   -> lit data/external/statsbomb_open_data/data/competitions.json
#   -> lit data/external/statsbomb_open_data/data/matches/
#   -> produit reports/evidence/ml_training/319_statsbomb_national_coverage_audit.txt
#   -> produit reports/evidence/ml_training/320_statsbomb_national_coverage_by_competition.csv