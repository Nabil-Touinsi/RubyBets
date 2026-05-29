# Rôle du fichier : tester l'extraction DOM des matchs Understat visibles dans le calendrier.
# Ce script produit uniquement des preuves expérimentales CSV/TXT et ne modifie pas la base, l'API, le frontend ou les modèles ML.

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


OUTPUT_DIR = Path("reports/evidence/ml_training")

SUMMARY_PATH = OUTPUT_DIR / "96_1x2_understat_dom_calendar_sample_summary.txt"
CSV_PATH = OUTPUT_DIR / "97_1x2_understat_dom_calendar_sample.csv"
NEXT_ACTION_PATH = OUTPUT_DIR / "98_1x2_understat_dom_calendar_next_action.txt"

DEFAULT_URL = "https://understat.com/league/EPL/2024"
BASE_URL = "https://understat.com/"


@dataclass
class UnderstatCalendarMatch:
    """Représente un match extrait depuis le calendrier DOM Understat."""

    date: str
    raw_date: str
    home_team: str
    away_team: str
    home_goals: str
    away_goals: str
    home_xg: str
    away_xg: str
    understat_match_id: str
    match_url: str
    is_result: str


# Prépare le dossier de sortie des preuves.
def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Nettoie une valeur texte avant de l'écrire dans les preuves.
def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


# Convertit une date Understat lisible en date ISO quand c'est possible.
def normalize_understat_date(raw_date: str) -> str:
    value = safe_text(raw_date)
    if not value:
        return ""

    try:
        return datetime.strptime(value, "%A, %B %d, %Y").date().isoformat()
    except ValueError:
        return value


# Récupère l'identifiant Understat depuis une URL de type match/26965.
def extract_understat_match_id(href: str) -> str:
    match = re.search(r"match/(\d+)", href or "")
    return match.group(1) if match else ""


# Essaie d'importer Playwright et retourne une erreur claire si le module manque.
def import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        return sync_playwright, None
    except Exception as exc:  # pragma: no cover - dépend de l'environnement local
        return None, exc


# Extrait les matchs visibles depuis le DOM rendu par Playwright.
def extract_matches_from_dom(page) -> list[UnderstatCalendarMatch]:
    raw_rows = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('.calendar-date-container')).flatMap((dateBlock) => {
            const rawDate = dateBlock.querySelector('.calendar-date')?.textContent?.trim() || '';
            return Array.from(dateBlock.querySelectorAll('.calendar-game')).map((game) => {
                const matchInfo = game.querySelector('a.match-info');
                const goals = matchInfo
                    ? Array.from(matchInfo.querySelectorAll('.teams-goals span')).map((item) => item.textContent.trim())
                    : [];
                const xgValues = matchInfo
                    ? Array.from(matchInfo.querySelectorAll('.teams-xG span')).map((item) => item.textContent.trim())
                    : [];

                return {
                    raw_date: rawDate,
                    home_team: game.querySelector('.block-home .team-title a')?.textContent?.trim() || '',
                    away_team: game.querySelector('.block-away .team-title a')?.textContent?.trim() || '',
                    home_goals: goals[0] || '',
                    away_goals: goals[1] || '',
                    home_xg: xgValues[0] || '',
                    away_xg: xgValues[1] || '',
                    href: matchInfo?.getAttribute('href') || '',
                    is_result: matchInfo?.getAttribute('data-isresult') || ''
                };
            });
        })
        """
    )

    rows: list[UnderstatCalendarMatch] = []
    for raw_row in raw_rows:
        href = safe_text(raw_row.get("href"))
        match_url = urljoin(BASE_URL, href)
        raw_date = safe_text(raw_row.get("raw_date"))

        rows.append(
            UnderstatCalendarMatch(
                date=normalize_understat_date(raw_date),
                raw_date=raw_date,
                home_team=safe_text(raw_row.get("home_team")),
                away_team=safe_text(raw_row.get("away_team")),
                home_goals=safe_text(raw_row.get("home_goals")),
                away_goals=safe_text(raw_row.get("away_goals")),
                home_xg=safe_text(raw_row.get("home_xg")),
                away_xg=safe_text(raw_row.get("away_xg")),
                understat_match_id=extract_understat_match_id(href),
                match_url=match_url,
                is_result=safe_text(raw_row.get("is_result")),
            )
        )

    return rows


# Évalue si une ligne extraite contient les champs principaux attendus.
def is_complete_match(row: UnderstatCalendarMatch) -> bool:
    required_values = [
        row.date,
        row.home_team,
        row.away_team,
        row.home_goals,
        row.away_goals,
        row.home_xg,
        row.away_xg,
        row.understat_match_id,
    ]
    return all(bool(value) for value in required_values)


# Sauvegarde l'échantillon DOM extrait au format CSV.
def save_matches_csv(rows: list[UnderstatCalendarMatch]) -> None:
    with CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "date",
                "raw_date",
                "home_team",
                "away_team",
                "home_goals",
                "away_goals",
                "home_xg",
                "away_xg",
                "understat_match_id",
                "match_url",
                "is_result",
            ],
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "date": row.date,
                    "raw_date": row.raw_date,
                    "home_team": row.home_team,
                    "away_team": row.away_team,
                    "home_goals": row.home_goals,
                    "away_goals": row.away_goals,
                    "home_xg": row.home_xg,
                    "away_xg": row.away_xg,
                    "understat_match_id": row.understat_match_id,
                    "match_url": row.match_url,
                    "is_result": row.is_result,
                }
            )


# Écrit une synthèse courte du test d'extraction DOM.
def write_summary(
    *,
    url: str,
    playwright_available: bool,
    install_error: str,
    browser_ok: bool,
    status_code: str,
    rendered_length: int,
    extracted_rows: int,
    complete_rows: int,
    incomplete_rows: int,
    error_type: str,
    error_message: str,
    sample_rows: list[UnderstatCalendarMatch],
) -> None:
    status = "V8_DOM_SAMPLE_AVAILABLE" if extracted_rows > 0 else "V8_DOM_SAMPLE_EMPTY"

    sample_text = "\n".join(
        [
            f"- {row.date} | {row.home_team} {row.home_goals}-{row.away_goals} {row.away_team} | xG {row.home_xg}-{row.away_xg} | match_id={row.understat_match_id}"
            for row in sample_rows[:10]
        ]
    )
    if not sample_text:
        sample_text = "Aucune ligne extraite."

    content = f"""RubyBets - ML 1X2 V8 Understat DOM calendar sample
96 - Synthese extraction DOM calendrier Understat

Objectif :
Verifier si les matchs visibles dans le calendrier Understat peuvent etre extraits depuis le DOM rendu par Playwright.

Garde-fous respectes :
- Aucune modification de PostgreSQL.
- Aucune modification de ml.features.
- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.
- Aucune integration produit d'Understat.
- Preuve experimentale interne uniquement.

Page testee :
- URL : {url}
- Playwright disponible : {playwright_available}
- Erreur installation/import : {install_error}
- Navigateur lance : {browser_ok}
- Status code : {status_code}
- Rendered body length : {rendered_length}

Extraction DOM :
- Rows extracted : {extracted_rows}
- Complete rows : {complete_rows}
- Incomplete rows : {incomplete_rows}
- Status : {status}

Erreur eventuelle :
- Error type : {error_type}
- Error message : {error_message}

Echantillon extrait :
{sample_text}

Fichiers generes :
{SUMMARY_PATH}
{CSV_PATH}
{NEXT_ACTION_PATH}

Decision attendue :
- Si Rows extracted > 0 : valider manuellement le CSV 97, puis creer un extracteur saison complet.
- Si Rows extracted = 0 : inspecter les selecteurs DOM, le HTML rendu et les requetes reseau avant de continuer.

Statut de suivi :
- Tache realisee : test d'extraction DOM Understat si les fichiers 96, 97 et 98 sont generes.
- Statut source a mettre a jour : a produire -> realise pour reports/evidence/ml_training/96, 97 et 98.
"""
    SUMMARY_PATH.write_text(content, encoding="utf-8")


# Écrit la prochaine décision technique selon le résultat de l'extraction.
def write_next_action(extracted_rows: int, complete_rows: int) -> None:
    if extracted_rows > 0 and complete_rows > 0:
        content = """RubyBets - ML 1X2 V8 Understat DOM calendar sample
98 - Prochaine action recommandee

Resultat :
L'extraction DOM Playwright a recupere des lignes exploitables depuis le calendrier Understat.

Decision :
Ne pas entrainer de modele maintenant.
La prochaine action technique est de valider manuellement le CSV 97, puis de creer un extracteur plus large pour une saison complete EPL 2024.

Prochaine etape proposee :
1. Controler reports/evidence/ml_training/97_1x2_understat_dom_calendar_sample.csv.
2. Verifier que les champs date, home_team, away_team, goals, xG et understat_match_id sont coherents.
3. Creer ensuite un script de recuperation saison complete si l'echantillon est valide.
4. Apres seulement, travailler sur le matching avec ml.clean_matches.
5. Ne calculer les rolling xG pre-match qu'apres validation du matching.

Garde-fou :
Understat reste une source experimentale interne. Aucune integration produit, API ou frontend pour le moment.
"""
    else:
        content = """RubyBets - ML 1X2 V8 Understat DOM calendar sample
98 - Prochaine action recommandee

Resultat :
L'extraction DOM Playwright n'a pas encore fourni de lignes exploitables.

Decision :
Ne pas creer d'extracteur saison complet et ne pas lancer de travail ML.

Prochaine etape proposee :
1. Ouvrir le HTML rendu 93 et confirmer les classes DOM presentes.
2. Ajuster les selecteurs .calendar-date-container, .calendar-game, .match-info et .teams-xG si Understat a change sa structure.
3. Relancer ce script sur https://understat.com/league/EPL/2024.
4. Si le DOM reste non exploitable, abandonner Understat comme source V8 et chercher une source xG plus stable.

Garde-fou :
Aucune modification de PostgreSQL, ml.features, API, frontend, scoring V1 ou modeles sauvegardes.
"""

    NEXT_ACTION_PATH.write_text(content, encoding="utf-8")


# Lance Playwright, extrait le calendrier DOM et produit les preuves 96, 97 et 98.
def run_dom_calendar_sample(url: str = DEFAULT_URL) -> None:
    ensure_output_dir()

    sync_playwright, import_error = import_playwright()
    if sync_playwright is None:
        install_message = (
            f"{type(import_error).__name__}: {import_error}"
            if import_error
            else "Playwright indisponible"
        )
        save_matches_csv([])
        write_summary(
            url=url,
            playwright_available=False,
            install_error=install_message,
            browser_ok=False,
            status_code="",
            rendered_length=0,
            extracted_rows=0,
            complete_rows=0,
            incomplete_rows=0,
            error_type=type(import_error).__name__ if import_error else "ImportError",
            error_message=str(import_error) if import_error else "Playwright indisponible",
            sample_rows=[],
        )
        write_next_action(0, 0)

        print("ERREUR - Playwright n'est pas disponible.")
        print("Installer puis relancer : pip install playwright ; python -m playwright install chromium")
        print(f"Summary saved: {SUMMARY_PATH}")
        return

    rows: list[UnderstatCalendarMatch] = []
    status_code = ""
    rendered_length = 0
    browser_ok = False
    error_type = "none"
    error_message = "none"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser_ok = True

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                timezone_id="Europe/Paris",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
                    "Upgrade-Insecure-Requests": "1",
                },
            )

            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if response is not None:
                status_code = str(response.status)

            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(3000)
            rendered_length = len(page.content())

            rows = extract_matches_from_dom(page)

            context.close()
            browser.close()

    except Exception as exc:  # pragma: no cover - dépend de l'environnement local
        error_type = type(exc).__name__
        error_message = str(exc)

    complete_rows = sum(1 for row in rows if is_complete_match(row))
    incomplete_rows = len(rows) - complete_rows

    save_matches_csv(rows)
    write_summary(
        url=url,
        playwright_available=True,
        install_error="none",
        browser_ok=browser_ok,
        status_code=status_code,
        rendered_length=rendered_length,
        extracted_rows=len(rows),
        complete_rows=complete_rows,
        incomplete_rows=incomplete_rows,
        error_type=error_type,
        error_message=error_message,
        sample_rows=rows,
    )
    write_next_action(len(rows), complete_rows)

    status = "V8_DOM_SAMPLE_AVAILABLE" if rows else "V8_DOM_SAMPLE_EMPTY"
    print("Extraction DOM Understat V8 terminee.")
    print(f"URL testee : {url}")
    print(f"Browser OK: {browser_ok}")
    print(f"Status code: {status_code}")
    print(f"Rendered body length: {rendered_length}")
    print(f"Rows extracted: {len(rows)}")
    print(f"Complete rows: {complete_rows}")
    print(f"Status: {status}")
    print(f"Summary saved: {SUMMARY_PATH}")
    print(f"CSV saved: {CSV_PATH}")
    print(f"Next action saved: {NEXT_ACTION_PATH}")


# Point d'entree CLI du script.
def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    run_dom_calendar_sample(url)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# extract_1x2_understat_dom_calendar_sample.py
#   -> Understat page via Playwright Chromium
#   -> DOM rendu : .calendar-date-container / .calendar-game / .teams-goals / .teams-xG
#   -> reports/evidence/ml_training/96_...summary.txt
#   -> reports/evidence/ml_training/97_...sample.csv
#   -> reports/evidence/ml_training/98_...next_action.txt
#   X aucune écriture PostgreSQL / ml.features / API / frontend / modèle sauvegardé
