# Rôle du fichier : récupérer en une seule exécution les matchs xG Understat disponibles par DOM Playwright pour les ligues et saisons configurées.
# Ce script produit uniquement des preuves expérimentales CSV/TXT et ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles ML.

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


BASE_URL = "https://understat.com/"
UNDERSTAT_LEAGUE_URL = "https://understat.com/league/{league_slug}/{season_year}"

# Ligues du périmètre RubyBets à tester côté Understat.
# Important : Understat peut ne pas exposer certaines compétitions, par exemple la Champions League.
# Le script ne bloque pas : une ligue indisponible est enregistrée dans le résumé et le fichier d'erreurs.
DEFAULT_PROJECT_LEAGUES: list[tuple[str, str]] = [
    ("EPL", "Premier League"),
    ("La_liga", "La Liga"),
    ("Bundesliga", "Bundesliga"),
    ("Serie_A", "Serie A"),
    ("Ligue_1", "Ligue 1"),
    ("Champions_League", "Champions League"),
]

# Saisons disponibles historiques à tester pour l'enrichissement ML RubyBets.
DEFAULT_START_SEASON = 2014
DEFAULT_END_SEASON = 2024

MAX_WEEKS_PER_SEASON = 80
WAIT_AFTER_CLICK_MS = 700
PAGE_TIMEOUT_MS = 60_000


@dataclass(frozen=True)
class LeagueConfig:
    """Représente une ligue à extraire depuis Understat."""

    slug: str
    label: str


@dataclass
class UnderstatCalendarMatch:
    """Représente un match extrait depuis le calendrier DOM Understat."""

    league_slug: str
    league_name: str
    season_year: int
    calendar_year: str
    calendar_week: str
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
    source_url: str


@dataclass
class SeasonExtractionResult:
    """Stocke le résultat d'extraction pour une ligue et une saison."""

    league_slug: str
    league_name: str
    season_year: int
    source_url: str
    status_code: str
    browser_ok: bool
    rendered_body_length: int
    weeks_visited: int
    rows_extracted: int
    complete_rows: int
    incomplete_rows: int
    unique_match_ids: int
    status: str
    error_type: str
    error_message: str


# Retrouve automatiquement la racine du projet afin d'écrire les preuves dans /reports et non dans /backend/reports.
def get_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "backend").exists() and (parent / "frontend").exists():
            return parent
    return current.parents[3]


PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
SUMMARY_PATH = OUTPUT_DIR / "99_1x2_understat_dom_all_leagues_seasons_summary.txt"
MATCHES_CSV_PATH = OUTPUT_DIR / "100_1x2_understat_dom_all_leagues_seasons_matches.csv"
BY_SEASON_CSV_PATH = OUTPUT_DIR / "101_1x2_understat_dom_all_leagues_seasons_by_league_season.csv"
ERRORS_CSV_PATH = OUTPUT_DIR / "102_1x2_understat_dom_all_leagues_seasons_errors.csv"
NEXT_ACTION_PATH = OUTPUT_DIR / "103_1x2_understat_dom_all_leagues_seasons_next_action.txt"


# Crée le dossier de sortie des preuves si nécessaire.
def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Nettoie une valeur texte avant écriture dans les preuves.
def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


# Convertit une date Understat lisible en date ISO quand c'est possible.
def normalize_understat_date(raw_date: str) -> str:
    value = safe_text(raw_date)
    if not value:
        return ""

    for pattern in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return value


# Récupère l'identifiant Understat depuis une URL de type match/26965.
def extract_understat_match_id(href: str) -> str:
    match = re.search(r"match/(\d+)", href or "")
    return match.group(1) if match else ""


# Essaie d'importer Playwright et retourne une erreur claire si le module manque.
def import_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
        from playwright.sync_api import sync_playwright  # type: ignore

        return sync_playwright, PlaywrightTimeoutError, None
    except Exception as exc:  # pragma: no cover - dépend de l'environnement local
        return None, None, exc


# Prépare la liste des saisons à parcourir.
def build_season_range(start_season: int, end_season: int) -> list[int]:
    if start_season > end_season:
        raise ValueError("La saison de début doit être inférieure ou égale à la saison de fin.")
    return list(range(start_season, end_season + 1))


# Prépare la liste des ligues à parcourir.
def build_league_configs(raw_leagues: str | None) -> list[LeagueConfig]:
    if not raw_leagues:
        return [LeagueConfig(slug=slug, label=label) for slug, label in DEFAULT_PROJECT_LEAGUES]

    requested_slugs = [item.strip() for item in raw_leagues.split(",") if item.strip()]
    known_labels = {slug: label for slug, label in DEFAULT_PROJECT_LEAGUES}
    return [LeagueConfig(slug=slug, label=known_labels.get(slug, slug)) for slug in requested_slugs]


# Lit la clé semaine/année actuellement affichée dans le calendrier Understat.
def get_current_calendar_key(page) -> tuple[str, str, str]:
    values = page.evaluate(
        """
        () => {
            const calendar = document.querySelector('.calendar');
            return {
                year: calendar?.getAttribute('data-current-year') || '',
                week: calendar?.getAttribute('data-current-week') || ''
            };
        }
        """
    )
    year = safe_text(values.get("year"))
    week = safe_text(values.get("week"))
    return year, week, f"{year}-W{week}"


# Extrait les matchs visibles dans la semaine actuellement affichée du calendrier DOM.
def extract_matches_from_current_calendar(
    page,
    *,
    league: LeagueConfig,
    season_year: int,
    source_url: str,
) -> list[UnderstatCalendarMatch]:
    calendar_year, calendar_week, _ = get_current_calendar_key(page)
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
                league_slug=league.slug,
                league_name=league.label,
                season_year=season_year,
                calendar_year=calendar_year,
                calendar_week=calendar_week,
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
                source_url=source_url,
            )
        )

    return rows


# Vérifie si une ligne extraite contient les champs principaux attendus.
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


# Détermine si le bouton semaine précédente est encore cliquable.
def can_click_previous_week(page) -> bool:
    return bool(
        page.evaluate(
            """
            () => {
                const button = document.querySelector('button.calendar-prev');
                return Boolean(button && !button.disabled);
            }
            """
        )
    )


# Clique sur la semaine précédente et attend que le calendrier se mette à jour.
def go_to_previous_week(page, previous_key: str, PlaywrightTimeoutError) -> bool:
    if not can_click_previous_week(page):
        return False

    page.locator("button.calendar-prev").first.click()
    try:
        page.wait_for_function(
            """
            (oldKey) => {
                const calendar = document.querySelector('.calendar');
                if (!calendar) return false;
                const newKey = `${calendar.getAttribute('data-current-year') || ''}-W${calendar.getAttribute('data-current-week') || ''}`;
                return newKey !== oldKey;
            }
            """,
            previous_key,
            timeout=15_000,
        )
    except PlaywrightTimeoutError:
        page.wait_for_timeout(WAIT_AFTER_CLICK_MS)

    page.wait_for_timeout(WAIT_AFTER_CLICK_MS)
    return True


# Extrait une saison complète en parcourant les semaines du calendrier Understat.
def extract_one_league_season(
    page,
    *,
    league: LeagueConfig,
    season_year: int,
    PlaywrightTimeoutError,
) -> tuple[list[UnderstatCalendarMatch], SeasonExtractionResult]:
    source_url = UNDERSTAT_LEAGUE_URL.format(league_slug=league.slug, season_year=season_year)
    rows_by_match_id: dict[str, UnderstatCalendarMatch] = {}
    seen_week_keys: set[str] = set()
    status_code = ""
    rendered_body_length = 0
    browser_ok = True
    error_type = "none"
    error_message = "none"

    try:
        response = page.goto(source_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        status_code = str(response.status) if response is not None else ""
        page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
        page.wait_for_timeout(1_500)
        rendered_body_length = len(page.content())

        if status_code and status_code != "200":
            raise RuntimeError(f"HTTP status {status_code}")

        for _ in range(MAX_WEEKS_PER_SEASON):
            calendar_year, calendar_week, current_key = get_current_calendar_key(page)
            if not calendar_year and not calendar_week:
                raise RuntimeError("Calendrier Understat introuvable dans le DOM rendu")

            if current_key in seen_week_keys:
                break

            seen_week_keys.add(current_key)
            week_rows = extract_matches_from_current_calendar(
                page,
                league=league,
                season_year=season_year,
                source_url=source_url,
            )

            for row in week_rows:
                dedupe_key = row.understat_match_id or f"{row.league_slug}-{row.season_year}-{row.date}-{row.home_team}-{row.away_team}"
                rows_by_match_id[dedupe_key] = row

            if not go_to_previous_week(page, current_key, PlaywrightTimeoutError):
                break

        rows = list(rows_by_match_id.values())
        complete_rows = sum(1 for row in rows if is_complete_match(row))
        incomplete_rows = len(rows) - complete_rows
        status = "AVAILABLE" if complete_rows > 0 else "EMPTY"

    except Exception as exc:  # pragma: no cover - dépend d'Understat et du réseau local
        rows = list(rows_by_match_id.values())
        complete_rows = sum(1 for row in rows if is_complete_match(row))
        incomplete_rows = len(rows) - complete_rows
        error_type = type(exc).__name__
        error_message = str(exc)
        status = "ERROR_WITH_PARTIAL_ROWS" if rows else "ERROR"

    result = SeasonExtractionResult(
        league_slug=league.slug,
        league_name=league.label,
        season_year=season_year,
        source_url=source_url,
        status_code=status_code,
        browser_ok=browser_ok,
        rendered_body_length=rendered_body_length,
        weeks_visited=len(seen_week_keys),
        rows_extracted=len(rows),
        complete_rows=complete_rows,
        incomplete_rows=incomplete_rows,
        unique_match_ids=len({row.understat_match_id for row in rows if row.understat_match_id}),
        status=status,
        error_type=error_type,
        error_message=error_message,
    )
    return rows, result


# Sauvegarde toutes les lignes match extraites dans un CSV unique.
def save_matches_csv(rows: list[UnderstatCalendarMatch]) -> None:
    with MATCHES_CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "league_slug",
                "league_name",
                "season_year",
                "calendar_year",
                "calendar_week",
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
                "source_url",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


# Sauvegarde le bilan par ligue et saison.
def save_by_season_csv(results: list[SeasonExtractionResult]) -> None:
    with BY_SEASON_CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "league_slug",
                "league_name",
                "season_year",
                "source_url",
                "status_code",
                "browser_ok",
                "rendered_body_length",
                "weeks_visited",
                "rows_extracted",
                "complete_rows",
                "incomplete_rows",
                "unique_match_ids",
                "status",
                "error_type",
                "error_message",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


# Sauvegarde uniquement les erreurs ou saisons vides pour faciliter le diagnostic.
def save_errors_csv(results: list[SeasonExtractionResult]) -> None:
    with ERRORS_CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "league_slug",
                "league_name",
                "season_year",
                "source_url",
                "status_code",
                "status",
                "rows_extracted",
                "complete_rows",
                "error_type",
                "error_message",
            ],
        )
        writer.writeheader()
        for result in results:
            if result.status != "AVAILABLE":
                writer.writerow(
                    {
                        "league_slug": result.league_slug,
                        "league_name": result.league_name,
                        "season_year": result.season_year,
                        "source_url": result.source_url,
                        "status_code": result.status_code,
                        "status": result.status,
                        "rows_extracted": result.rows_extracted,
                        "complete_rows": result.complete_rows,
                        "error_type": result.error_type,
                        "error_message": result.error_message,
                    }
                )


# Écrit la synthèse globale d'extraction multi-ligues et multi-saisons.
def write_summary(
    *,
    leagues: list[LeagueConfig],
    seasons: list[int],
    rows: list[UnderstatCalendarMatch],
    results: list[SeasonExtractionResult],
    elapsed_seconds: float,
) -> None:
    available_results = [result for result in results if result.status == "AVAILABLE"]
    unavailable_results = [result for result in results if result.status != "AVAILABLE"]
    complete_rows = sum(1 for row in rows if is_complete_match(row))
    incomplete_rows = len(rows) - complete_rows

    status = "V8_DOM_ALL_AVAILABLE_PARTIAL" if unavailable_results else "V8_DOM_ALL_AVAILABLE_FULL"
    if not rows:
        status = "V8_DOM_ALL_AVAILABLE_EMPTY"

    league_lines = "\n".join([f"- {league.slug} : {league.label}" for league in leagues])
    season_text = f"{min(seasons)} -> {max(seasons)}" if seasons else "none"

    by_league_lines = []
    for league in leagues:
        league_rows = [row for row in rows if row.league_slug == league.slug]
        league_results = [result for result in results if result.league_slug == league.slug]
        by_league_lines.append(
            f"- {league.slug} : rows={len(league_rows)}, available_seasons={sum(1 for result in league_results if result.status == 'AVAILABLE')}, unavailable_or_empty={sum(1 for result in league_results if result.status != 'AVAILABLE')}"
        )

    sample_text = "\n".join(
        [
            f"- {row.league_slug} {row.season_year} | {row.date} | {row.home_team} {row.home_goals}-{row.away_goals} {row.away_team} | xG {row.home_xg}-{row.away_xg} | match_id={row.understat_match_id}"
            for row in rows[:15]
        ]
    )
    if not sample_text:
        sample_text = "Aucune ligne extraite."

    content = f"""RubyBets - ML 1X2 V8 Understat DOM all leagues/seasons
99 - Synthese extraction DOM multi-ligues multi-saisons Understat

Objectif :
Recuperer en une seule execution les matchs xG Understat disponibles pour les ligues et saisons configurees, afin de preparer plus tard le matching avec ml.clean_matches.

Garde-fous respectes :
- Aucune modification de PostgreSQL.
- Aucune modification de ml.features.
- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.
- Aucune integration produit d'Understat.
- Preuve experimentale interne uniquement.

Ligues demandees :
{league_lines}

Saisons testees :
- {season_text}

Resultat global :
- League-season attempts : {len(results)}
- Available league-seasons : {len(available_results)}
- Unavailable or empty league-seasons : {len(unavailable_results)}
- Rows extracted : {len(rows)}
- Complete rows : {complete_rows}
- Incomplete rows : {incomplete_rows}
- Unique Understat match IDs : {len({row.understat_match_id for row in rows if row.understat_match_id})}
- Elapsed seconds : {elapsed_seconds:.2f}
- Status : {status}

Bilan par ligue :
{chr(10).join(by_league_lines)}

Echantillon extrait :
{sample_text}

Fichiers generes :
{SUMMARY_PATH}
{MATCHES_CSV_PATH}
{BY_SEASON_CSV_PATH}
{ERRORS_CSV_PATH}
{NEXT_ACTION_PATH}

Decision attendue :
- Si le CSV 100 contient un volume coherent : valider les lignes par ligue/saison puis creer un script de matching avec ml.clean_matches.
- Si une ligue est vide ou en erreur : verifier si Understat couvre reellement cette competition avant de forcer son integration.
- Ne pas calculer de rolling xG pre-match avant validation du matching.

Statut de suivi :
- Tache realisee si les fichiers 99, 100, 101, 102 et 103 sont generes.
- Statut source a mettre a jour : a produire -> realise pour l'extraction DOM Understat multi-ligues multi-saisons.
"""
    SUMMARY_PATH.write_text(content, encoding="utf-8")


# Écrit la prochaine action recommandée après l'extraction globale.
def write_next_action(rows: list[UnderstatCalendarMatch], results: list[SeasonExtractionResult]) -> None:
    available_rows = len(rows)
    unavailable_results = [result for result in results if result.status != "AVAILABLE"]

    if available_rows > 0:
        content = f"""RubyBets - ML 1X2 V8 Understat DOM all leagues/seasons
103 - Prochaine action recommandee

Resultat :
L'extraction DOM Playwright a recupere {available_rows} lignes de matchs xG Understat sur les ligues/saisons disponibles.

Decision :
Ne pas entrainer de modele maintenant.
La prochaine action technique est de valider le CSV 100, puis de creer un script de matching avec ml.clean_matches.

Prochaine etape proposee :
1. Controler reports/evidence/ml_training/100_1x2_understat_dom_all_leagues_seasons_matches.csv.
2. Controler reports/evidence/ml_training/101_1x2_understat_dom_all_leagues_seasons_by_league_season.csv.
3. Verifier les ligues/saisons vides ou en erreur dans reports/evidence/ml_training/102_1x2_understat_dom_all_leagues_seasons_errors.csv.
4. Valider que les champs date, home_team, away_team, goals, xG et understat_match_id sont coherents.
5. Creer ensuite un script de matching Understat -> ml.clean_matches.
6. Ne calculer les rolling xG pre-match qu'apres validation du matching.

Attention :
League-seasons indisponibles ou vides : {len(unavailable_results)}.
Cela peut etre normal si Understat ne couvre pas certaines competitions du perimetre RubyBets.

Garde-fou :
Understat reste une source experimentale interne. Aucune integration produit, API ou frontend pour le moment.
"""
    else:
        content = """RubyBets - ML 1X2 V8 Understat DOM all leagues/seasons
103 - Prochaine action recommandee

Resultat :
L'extraction DOM Playwright globale n'a pas recupere de lignes exploitables.

Decision :
Ne pas creer de matching avec ml.clean_matches et ne pas lancer de travail ML.

Prochaine etape proposee :
1. Verifier le fichier 102 des erreurs.
2. Relancer sur une seule ligue et une seule saison deja validee : EPL 2024.
3. Inspecter les selecteurs DOM si le resultat differe du test 96-98.
4. Abandonner l'extraction globale si Understat bloque ou change la structure de ses pages.

Garde-fou :
Aucune modification de PostgreSQL, ml.features, API, frontend, scoring V1 ou modeles sauvegardes.
"""

    NEXT_ACTION_PATH.write_text(content, encoding="utf-8")


# Sauvegarde les preuves à chaque fin de saison pour éviter de perdre le travail en cas d'arrêt.
def persist_outputs(
    *,
    leagues: list[LeagueConfig],
    seasons: list[int],
    rows: list[UnderstatCalendarMatch],
    results: list[SeasonExtractionResult],
    started_at: float,
) -> None:
    save_matches_csv(rows)
    save_by_season_csv(results)
    save_errors_csv(results)
    write_summary(
        leagues=leagues,
        seasons=seasons,
        rows=rows,
        results=results,
        elapsed_seconds=time.time() - started_at,
    )
    write_next_action(rows, results)


# Lance l'extraction multi-ligues et multi-saisons avec Playwright.
def run_all_leagues_seasons_extraction(
    *,
    leagues: list[LeagueConfig],
    seasons: list[int],
    headless: bool,
) -> None:
    ensure_output_dir()
    started_at = time.time()

    sync_playwright, PlaywrightTimeoutError, import_error = import_playwright()
    if sync_playwright is None or PlaywrightTimeoutError is None:
        error_result = SeasonExtractionResult(
            league_slug="all",
            league_name="all",
            season_year=0,
            source_url="",
            status_code="",
            browser_ok=False,
            rendered_body_length=0,
            weeks_visited=0,
            rows_extracted=0,
            complete_rows=0,
            incomplete_rows=0,
            unique_match_ids=0,
            status="PLAYWRIGHT_UNAVAILABLE",
            error_type=type(import_error).__name__ if import_error else "ImportError",
            error_message=str(import_error) if import_error else "Playwright indisponible",
        )
        persist_outputs(leagues=leagues, seasons=seasons, rows=[], results=[error_result], started_at=started_at)
        print("ERREUR - Playwright n'est pas disponible.")
        print("Installer puis relancer : pip install playwright ; python -m playwright install chromium")
        return

    all_rows: list[UnderstatCalendarMatch] = []
    results: list[SeasonExtractionResult] = []
    seen_global_match_ids: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
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

        total_attempts = len(leagues) * len(seasons)
        current_attempt = 0

        for league in leagues:
            for season_year in seasons:
                current_attempt += 1
                print(f"[{current_attempt}/{total_attempts}] Extraction {league.slug} {season_year}...")

                season_rows, result = extract_one_league_season(
                    page,
                    league=league,
                    season_year=season_year,
                    PlaywrightTimeoutError=PlaywrightTimeoutError,
                )
                results.append(result)

                for row in season_rows:
                    dedupe_key = row.understat_match_id or f"{row.league_slug}-{row.season_year}-{row.date}-{row.home_team}-{row.away_team}"
                    if dedupe_key not in seen_global_match_ids:
                        seen_global_match_ids.add(dedupe_key)
                        all_rows.append(row)

                print(
                    f"    status={result.status} rows={result.rows_extracted} complete={result.complete_rows} weeks={result.weeks_visited} error={result.error_type}"
                )
                persist_outputs(
                    leagues=leagues,
                    seasons=seasons,
                    rows=all_rows,
                    results=results,
                    started_at=started_at,
                )

        context.close()
        browser.close()

    complete_rows = sum(1 for row in all_rows if is_complete_match(row))
    status = "V8_DOM_ALL_AVAILABLE_PARTIAL" if all_rows else "V8_DOM_ALL_AVAILABLE_EMPTY"
    if all_rows and all(result.status == "AVAILABLE" for result in results):
        status = "V8_DOM_ALL_AVAILABLE_FULL"

    print("Extraction DOM Understat multi-ligues multi-saisons terminee.")
    print(f"League-season attempts: {len(results)}")
    print(f"Rows extracted: {len(all_rows)}")
    print(f"Complete rows: {complete_rows}")
    print(f"Status: {status}")
    print(f"Summary saved: {SUMMARY_PATH}")
    print(f"Matches CSV saved: {MATCHES_CSV_PATH}")
    print(f"By season CSV saved: {BY_SEASON_CSV_PATH}")
    print(f"Errors CSV saved: {ERRORS_CSV_PATH}")
    print(f"Next action saved: {NEXT_ACTION_PATH}")


# Prépare les arguments CLI pour limiter ou élargir le périmètre sans modifier le code.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extraction DOM Understat multi-ligues multi-saisons pour RubyBets V8."
    )
    parser.add_argument("--start-season", type=int, default=DEFAULT_START_SEASON)
    parser.add_argument("--end-season", type=int, default=DEFAULT_END_SEASON)
    parser.add_argument(
        "--leagues",
        type=str,
        default=None,
        help="Liste de slugs Understat separes par virgule. Exemple : EPL,La_liga,Bundesliga",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Affiche Chromium pendant l'extraction pour debug visuel.",
    )
    return parser.parse_args()


# Point d'entrée CLI du script.
def main() -> None:
    args = parse_args()
    seasons = build_season_range(args.start_season, args.end_season)
    leagues = build_league_configs(args.leagues)
    run_all_leagues_seasons_extraction(leagues=leagues, seasons=seasons, headless=not args.show_browser)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# extract_1x2_understat_dom_all_leagues_seasons.py
#   -> Understat pages via Playwright Chromium : /league/{league_slug}/{season_year}
#   -> DOM rendu : .calendar / .calendar-prev / .calendar-date-container / .calendar-game / .teams-goals / .teams-xG
#   -> reports/evidence/ml_training/99_...summary.txt
#   -> reports/evidence/ml_training/100_...matches.csv
#   -> reports/evidence/ml_training/101_...by_league_season.csv
#   -> reports/evidence/ml_training/102_...errors.csv
#   -> reports/evidence/ml_training/103_...next_action.txt
#   X aucune écriture PostgreSQL / ml.features / API / frontend / modèle sauvegardé
