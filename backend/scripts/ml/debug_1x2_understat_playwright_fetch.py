# Rôle du fichier : diagnostiquer si Understat devient exploitable via un vrai navigateur Playwright.
# Ce script ne modifie ni la base, ni ml.features, ni l'API, ni le frontend.
# Il ouvre une page Understat, attend le rendu JavaScript, sauvegarde le HTML rendu et les requêtes réseau.

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path("reports/evidence/ml_training")

SUMMARY_PATH = OUTPUT_DIR / "92_1x2_understat_playwright_debug_summary.txt"
RENDERED_HTML_PATH = OUTPUT_DIR / "93_1x2_understat_playwright_rendered_response.html"
NETWORK_CSV_PATH = OUTPUT_DIR / "94_1x2_understat_playwright_network_requests.csv"
EXTRACT_PATH = OUTPUT_DIR / "95_1x2_understat_playwright_extract_sample.txt"

DEFAULT_URL = "https://understat.com/league/EPL/2024"


@dataclass
class NetworkEntry:
    """Stocke une ligne simple de suivi réseau Playwright."""

    method: str
    resource_type: str
    status: str
    content_type: str
    url: str


# Prépare le dossier de sortie des preuves.
def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Nettoie une valeur texte pour l'écriture CSV.
def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


# Essaie d'importer Playwright et retourne une erreur claire si le module manque.
def import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        return sync_playwright, None
    except Exception as exc:  # pragma: no cover - dépend de l'environnement local
        return None, exc


# Extrait un bloc JavaScript Understat si présent dans le HTML rendu.
def extract_understat_json_block(html: str, variable_name: str) -> tuple[bool, int, str]:
    pattern = rf"var\s+{re.escape(variable_name)}\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html, flags=re.DOTALL)

    if not match:
        return False, 0, ""

    raw_payload = match.group(1)
    rows_estimate = raw_payload.count("\\x7B")
    sample = raw_payload[:2500]
    return True, rows_estimate, sample


# Sauvegarde les requêtes réseau observées par Playwright.
def save_network_entries(entries: list[NetworkEntry]) -> None:
    with NETWORK_CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["method", "resource_type", "status", "content_type", "url"],
        )
        writer.writeheader()

        for entry in entries:
            writer.writerow(
                {
                    "method": safe_text(entry.method),
                    "resource_type": safe_text(entry.resource_type),
                    "status": safe_text(entry.status),
                    "content_type": safe_text(entry.content_type),
                    "url": safe_text(entry.url),
                }
            )


# Ecrit une synthèse simple et lisible du diagnostic Playwright.
def write_summary(
    *,
    url: str,
    playwright_available: bool,
    install_error: str,
    browser_ok: bool,
    error_type: str,
    error_message: str,
    status_code: str,
    rendered_length: int,
    title: str,
    dates_found: bool,
    dates_rows: int,
    teams_found: bool,
    teams_rows: int,
    players_found: bool,
    players_rows: int,
    league_table_marker: bool,
    network_entries_count: int,
    recommendation: str,
) -> None:
    content = f"""RubyBets - ML 1X2 V8 Understat Playwright fetch debug
92 - Diagnostic navigateur de recuperation Understat

Objectif :
Verifier si Understat devient exploitable avec un vrai navigateur Playwright, apres echec de la recuperation HTTP simple.

Garde-fous respectes :
- Aucune modification de PostgreSQL.
- Aucune modification de ml.features.
- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.
- Diagnostic limite a une page Understat, au HTML rendu et aux requetes reseau.

Page testee :
- URL : {url}
- Playwright disponible : {playwright_available}
- Erreur installation/import : {install_error}
- Navigateur lance : {browser_ok}
- Error type : {error_type}
- Error message : {error_message}
- Status code : {status_code}
- Title : {title}
- Rendered body length : {rendered_length}

Signaux detectes dans le HTML rendu :
- league_table_marker_detected : {league_table_marker}
- datesData trouve : {dates_found}
- datesData lignes estimees : {dates_rows}
- teamsData trouve : {teams_found}
- teamsData lignes estimees : {teams_rows}
- playersData trouve : {players_found}
- playersData lignes estimees : {players_rows}

Requetes reseau observees :
- Nombre de requetes/reponses capturees : {network_entries_count}
- Fichier reseau : {NETWORK_CSV_PATH}

Diagnostic :
- Recommendation : {recommendation}

Fichiers generes :
{SUMMARY_PATH}
{RENDERED_HTML_PATH}
{NETWORK_CSV_PATH}
{EXTRACT_PATH}

Decision attendue :
- Si datesData ou teamsData est trouve : corriger l'audit Understat pour utiliser Playwright.
- Si aucun bloc data n'est trouve mais que le HTML rendu contient le tableau : parser le DOM rendu.
- Si Playwright ne recupere toujours pas les donnees : abandonner Understat pour une source xG plus stable.

Statut de suivi :
- Tache realisee : diagnostic Playwright de recuperation Understat si les fichiers 92, 93, 94 et 95 sont generes.
- Statut source a mettre a jour : a produire -> realise pour les fichiers reports/evidence/ml_training/92, 93, 94 et 95.
"""
    SUMMARY_PATH.write_text(content, encoding="utf-8")


# Lance le diagnostic avec Playwright sur une page Understat.
def run_playwright_debug(url: str = DEFAULT_URL) -> None:
    ensure_output_dir()

    sync_playwright, import_error = import_playwright()

    if sync_playwright is None:
        install_message = (
            f"{type(import_error).__name__}: {import_error}"
            if import_error
            else "Playwright indisponible"
        )
        recommendation = (
            "Installer Playwright puis relancer : "
            "pip install playwright ; python -m playwright install chromium"
        )

        write_summary(
            url=url,
            playwright_available=False,
            install_error=install_message,
            browser_ok=False,
            error_type=type(import_error).__name__ if import_error else "ImportError",
            error_message=str(import_error) if import_error else "Playwright indisponible",
            status_code="",
            rendered_length=0,
            title="",
            dates_found=False,
            dates_rows=0,
            teams_found=False,
            teams_rows=0,
            players_found=False,
            players_rows=0,
            league_table_marker=False,
            network_entries_count=0,
            recommendation=recommendation,
        )
        RENDERED_HTML_PATH.write_text("", encoding="utf-8")
        EXTRACT_PATH.write_text("Playwright indisponible.\n", encoding="utf-8")
        save_network_entries([])

        print("ERREUR - Playwright n'est pas disponible.")
        print(recommendation)
        print(f"Summary saved: {SUMMARY_PATH}")
        return

    network_entries: list[NetworkEntry] = []
    rendered_html = ""
    title = ""
    status_code = ""
    error_type = "none"
    error_message = "none"
    browser_ok = False

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

            # Capture les réponses réseau utiles pour comprendre d'où viennent les données.
            def on_response(response):
                try:
                    request = response.request
                    network_entries.append(
                        NetworkEntry(
                            method=request.method,
                            resource_type=request.resource_type,
                            status=str(response.status),
                            content_type=response.headers.get("content-type", ""),
                            url=response.url,
                        )
                    )
                except Exception:
                    pass

            page.on("response", on_response)

            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if response is not None:
                status_code = str(response.status)

            # Attend que les scripts et les appels réseau aient une chance de charger les blocs.
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            title = page.title()
            rendered_html = page.content()

            context.close()
            browser.close()

    except Exception as exc:  # pragma: no cover - dépend de l'environnement local
        error_type = type(exc).__name__
        error_message = str(exc)

    RENDERED_HTML_PATH.write_text(rendered_html, encoding="utf-8")

    dates_found, dates_rows, dates_sample = extract_understat_json_block(rendered_html, "datesData")
    teams_found, teams_rows, teams_sample = extract_understat_json_block(rendered_html, "teamsData")
    players_found, players_rows, players_sample = extract_understat_json_block(rendered_html, "playersData")

    league_table_marker = (
        "league-chemp" in rendered_html
        or "xG" in rendered_html
        or "xGA" in rendered_html
    )

    extract_content = f"""RubyBets - Understat Playwright extract sample

URL testee : {url}

datesData trouve : {dates_found}
datesData lignes estimees : {dates_rows}
Echantillon datesData :
{dates_sample if dates_sample else "Aucun echantillon datesData disponible."}

teamsData trouve : {teams_found}
teamsData lignes estimees : {teams_rows}
Echantillon teamsData :
{teams_sample if teams_sample else "Aucun echantillon teamsData disponible."}

playersData trouve : {players_found}
playersData lignes estimees : {players_rows}
Echantillon playersData :
{players_sample if players_sample else "Aucun echantillon playersData disponible."}
"""
    EXTRACT_PATH.write_text(extract_content, encoding="utf-8")
    save_network_entries(network_entries)

    if dates_found or teams_found:
        recommendation = "Understat semble exploitable avec Playwright. Corriger l'audit V8 pour utiliser le HTML rendu navigateur."
    elif rendered_html and league_table_marker:
        recommendation = "Le HTML rendu existe mais les blocs JSON ne sont pas exposes. Inspecter le DOM rendu ou les requetes reseau."
    elif rendered_html:
        recommendation = "La page est rendue mais les donnees restent absentes. Tester les requetes reseau ou une source alternative."
    else:
        recommendation = "Playwright n'a pas recupere de HTML exploitable. Tester installation navigateur ou source alternative."

    write_summary(
        url=url,
        playwright_available=True,
        install_error="none",
        browser_ok=browser_ok,
        error_type=error_type,
        error_message=error_message,
        status_code=status_code,
        rendered_length=len(rendered_html),
        title=title,
        dates_found=dates_found,
        dates_rows=dates_rows,
        teams_found=teams_found,
        teams_rows=teams_rows,
        players_found=players_found,
        players_rows=players_rows,
        league_table_marker=league_table_marker,
        network_entries_count=len(network_entries),
        recommendation=recommendation,
    )

    print("Diagnostic Playwright Understat V8 termine.")
    print(f"URL testee : {url}")
    print(f"Browser OK: {browser_ok}")
    print(f"Status code: {status_code}")
    print(f"Rendered body length: {len(rendered_html)}")
    print(f"datesData found: {dates_found}")
    print(f"datesData rows: {dates_rows}")
    print(f"teamsData found: {teams_found}")
    print(f"teamsData rows: {teams_rows}")
    print(f"Recommendation: {recommendation}")
    print(f"Summary saved: {SUMMARY_PATH}")
    print(f"Rendered HTML saved: {RENDERED_HTML_PATH}")
    print(f"Network CSV saved: {NETWORK_CSV_PATH}")
    print(f"Extract saved: {EXTRACT_PATH}")


# Point d'entree CLI du script.
def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    run_playwright_debug(url)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# debug_1x2_understat_playwright_fetch.py
#   -> Understat page via Playwright Chromium
#   -> reports/evidence/ml_training/92_...summary.txt
#   -> reports/evidence/ml_training/93_...rendered_response.html
#   -> reports/evidence/ml_training/94_...network_requests.csv
#   -> reports/evidence/ml_training/95_...extract_sample.txt
#   X aucune écriture PostgreSQL / ml.features / API / frontend / modèle sauvegardé
