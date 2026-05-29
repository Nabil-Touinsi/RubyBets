# Rôle du fichier : extraire en masse les matchs xG Understat depuis le DOM Playwright pour plusieurs ligues et saisons RubyBets.
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

DEFAULT_PROJECT_LEAGUES: list[tuple[str, str]] = [
    ("EPL", "Premier League"),
    ("La_liga", "La Liga"),
    ("Bundesliga", "Bundesliga"),
    ("Serie_A", "Serie A"),
    ("Ligue_1", "Ligue 1"),
    ("Champions_League", "Champions League"),
]

DEFAULT_START_SEASON = 2014
DEFAULT_END_SEASON = 2024
DEFAULT_MAX_WEEKS_PER_SEASON = 90
DEFAULT_CLICK_DELAY_MS = 450
PAGE_TIMEOUT_MS = 45_000
CALENDAR_TIMEOUT_MS = 20_000

EXPECTED_MIN_ROWS_BY_LEAGUE: dict[str, int] = {
    "EPL": 300,
    "La_liga": 300,
    "Bundesliga": 250,
    "Serie_A": 300,
    "Ligue_1": 250,
    "Champions_League": 80,
}


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
    """Stocke le bilan d'extraction pour une ligue et une saison."""

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
    expected_min_rows: int
    status: str
    error_type: str
    error_message: str


# Retrouve la racine RubyBets pour écrire dans /reports et non dans /backend/reports.
def get_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "backend").exists() and (parent / "frontend").exists():
            return parent
    return current.parents[3]


PROJECT_ROOT = get_project_root()
OUTPUT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
SUMMARY_PATH = OUTPUT_DIR / "109_1x2_understat_dom_all_leagues_seasons_v3_summary.txt"
MATCHES_CSV_PATH = OUTPUT_DIR / "110_1x2_understat_dom_all_leagues_seasons_v3_matches.csv"
BY_SEASON_CSV_PATH = OUTPUT_DIR / "111_1x2_understat_dom_all_leagues_seasons_v3_by_league_season.csv"
ERRORS_CSV_PATH = OUTPUT_DIR / "112_1x2_understat_dom_all_leagues_seasons_v3_errors.csv"
NEXT_ACTION_PATH = OUTPUT_DIR / "113_1x2_understat_dom_all_leagues_seasons_v3_next_action.txt"


# Crée le dossier de preuves si nécessaire.
def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Nettoie une valeur texte avant exploitation ou sauvegarde.
def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


# Convertit une date Understat lisible en date ISO quand le format est reconnu.
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


# Récupère l'identifiant Understat depuis une URL de match.
def extract_understat_match_id(href: str) -> str:
    match = re.search(r"match/(\d+)", href or "")
    return match.group(1) if match else ""


# Importe Playwright avec une erreur explicite si l'environnement n'est pas prêt.
def import_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
        from playwright.sync_api import sync_playwright  # type: ignore

        return sync_playwright, PlaywrightTimeoutError, None
    except Exception as exc:  # pragma: no cover - dépend de l'environnement local
        return None, None, exc


# Prépare la liste de saisons demandées.
def build_season_range(start_season: int, end_season: int) -> list[int]:
    if start_season > end_season:
        raise ValueError("La saison de début doit être inférieure ou égale à la saison de fin.")
    return list(range(start_season, end_season + 1))


# Prépare la liste de ligues demandées.
def build_league_configs(raw_leagues: str | None) -> list[LeagueConfig]:
    if not raw_leagues:
        return [LeagueConfig(slug=slug, label=label) for slug, label in DEFAULT_PROJECT_LEAGUES]

    requested_slugs = [item.strip() for item in raw_leagues.split(",") if item.strip()]
    known_labels = {slug: label for slug, label in DEFAULT_PROJECT_LEAGUES}
    return [LeagueConfig(slug=slug, label=known_labels.get(slug, slug)) for slug in requested_slugs]


# Lit la semaine/année actuellement affichée dans le calendrier Understat.
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


# Extrait les matchs visibles dans le calendrier actuellement affiché.
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
                match_url=urljoin(BASE_URL, href),
                is_result=safe_text(raw_row.get("is_result")),
                source_url=source_url,
            )
        )
    return rows


# Vérifie si une ligne contient les champs principaux nécessaires au futur matching.
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


# Détermine si la saison contient un volume crédible de matchs.
def classify_season_status(
    *,
    complete_rows: int,
    expected_min_rows: int,
    error_type: str,
) -> str:
    if complete_rows <= 0 and error_type != "none":
        return "ERROR"
    if complete_rows <= 0:
        return "EMPTY"
    if complete_rows < expected_min_rows:
        return "TOO_FEW_ROWS"
    if error_type != "none":
        return "AVAILABLE_WITH_WARNING"
    return "AVAILABLE"


# Vérifie côté DOM si le bouton semaine précédente peut encore être déclenché.
def can_trigger_previous_week(page) -> bool:
    return bool(
        page.evaluate(
            """
            () => {
                const button = document.querySelector('button.calendar-prev, .calendar-prev');
                if (!button) return false;
                const className = button.className || '';
                const ariaDisabled = button.getAttribute('aria-disabled') || '';
                return !button.disabled && !className.includes('disabled') && ariaDisabled !== 'true';
            }
            """
        )
    )


# Clique sur la semaine précédente via JavaScript pour éviter les TimeoutError Playwright liés à l'actionability check.
def trigger_previous_week(page, previous_key: str, *, click_delay_ms: int, PlaywrightTimeoutError) -> bool:
    if not can_trigger_previous_week(page):
        return False

    clicked = bool(
        page.evaluate(
            """
            () => {
                const button = document.querySelector('button.calendar-prev, .calendar-prev');
                if (!button) return false;
                button.click();
                return true;
            }
            """
        )
    )
    if not clicked:
        return False

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
            arg=previous_key,
            timeout=7_000,
        )
    except PlaywrightTimeoutError:
        # Understat peut mettre à jour la liste sans modifier immédiatement les attributs calendrier.
        # On laisse quand même une pause courte puis on vérifiera les doublons côté Python.
        page.wait_for_timeout(click_delay_ms)

    page.wait_for_timeout(click_delay_ms)
    return True


# Ouvre une page ligue/saison et attend uniquement le calendrier, sans networkidle bloquant.
def open_league_season_page(page, source_url: str) -> tuple[str, int]:
    response = page.goto(source_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    status_code = str(response.status) if response is not None else ""
    page.wait_for_selector(".calendar", timeout=CALENDAR_TIMEOUT_MS)
    page.wait_for_timeout(1_000)
    return status_code, len(page.content())


# Extrait une ligue/saison en parcourant les semaines disponibles du calendrier.
def extract_one_league_season(
    page,
    *,
    league: LeagueConfig,
    season_year: int,
    max_weeks: int,
    click_delay_ms: int,
    PlaywrightTimeoutError,
) -> tuple[list[UnderstatCalendarMatch], SeasonExtractionResult]:
    source_url = UNDERSTAT_LEAGUE_URL.format(league_slug=league.slug, season_year=season_year)
    rows_by_match_id: dict[str, UnderstatCalendarMatch] = {}
    seen_week_keys: set[str] = set()
    weeks_without_new_rows = 0
    status_code = ""
    rendered_body_length = 0
    error_type = "none"
    error_message = "none"

    try:
        status_code, rendered_body_length = open_league_season_page(page, source_url)
        if status_code and status_code != "200":
            raise RuntimeError(f"HTTP status {status_code}")

        for _ in range(max_weeks):
            _, _, current_key = get_current_calendar_key(page)
            if not current_key or current_key == "-W":
                raise RuntimeError("Calendrier Understat introuvable ou semaine non lisible")
            if current_key in seen_week_keys:
                break

            seen_week_keys.add(current_key)
            before_count = len(rows_by_match_id)
            week_rows = extract_matches_from_current_calendar(
                page,
                league=league,
                season_year=season_year,
                source_url=source_url,
            )

            for row in week_rows:
                dedupe_key = row.understat_match_id or f"{row.league_slug}-{row.season_year}-{row.date}-{row.home_team}-{row.away_team}"
                rows_by_match_id[dedupe_key] = row

            new_rows_count = len(rows_by_match_id) - before_count
            weeks_without_new_rows = weeks_without_new_rows + 1 if new_rows_count == 0 else 0
            if weeks_without_new_rows >= 4:
                break

            if not trigger_previous_week(
                page,
                current_key,
                click_delay_ms=click_delay_ms,
                PlaywrightTimeoutError=PlaywrightTimeoutError,
            ):
                break

    except Exception as exc:  # pragma: no cover - dépend d'Understat et du réseau local
        error_type = type(exc).__name__
        error_message = str(exc)

    rows = list(rows_by_match_id.values())
    complete_rows = sum(1 for row in rows if is_complete_match(row))
    incomplete_rows = len(rows) - complete_rows
    expected_min_rows = EXPECTED_MIN_ROWS_BY_LEAGUE.get(league.slug, 200)
    status = classify_season_status(
        complete_rows=complete_rows,
        expected_min_rows=expected_min_rows,
        error_type=error_type,
    )

    result = SeasonExtractionResult(
        league_slug=league.slug,
        league_name=league.label,
        season_year=season_year,
        source_url=source_url,
        status_code=status_code,
        browser_ok=True,
        rendered_body_length=rendered_body_length,
        weeks_visited=len(seen_week_keys),
        rows_extracted=len(rows),
        complete_rows=complete_rows,
        incomplete_rows=incomplete_rows,
        unique_match_ids=len({row.understat_match_id for row in rows if row.understat_match_id}),
        expected_min_rows=expected_min_rows,
        status=status,
        error_type=error_type,
        error_message=error_message,
    )
    return rows, result


# Sauvegarde le CSV unique contenant toutes les lignes match extraites.
def save_matches_csv(rows: list[UnderstatCalendarMatch]) -> None:
    with MATCHES_CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(UnderstatCalendarMatch.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


# Sauvegarde le bilan par ligue/saison.
def save_by_season_csv(results: list[SeasonExtractionResult]) -> None:
    with BY_SEASON_CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(SeasonExtractionResult.__dataclass_fields__.keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


# Sauvegarde les saisons vides, incomplètes ou en erreur pour diagnostic rapide.
def save_errors_csv(results: list[SeasonExtractionResult]) -> None:
    warning_statuses = {"ERROR", "EMPTY", "TOO_FEW_ROWS", "AVAILABLE_WITH_WARNING"}
    with ERRORS_CSV_PATH.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(SeasonExtractionResult.__dataclass_fields__.keys()))
        writer.writeheader()
        for result in results:
            if result.status in warning_statuses:
                writer.writerow(result.__dict__)


# Écrit la synthèse globale de l'extraction V3.
def write_summary(
    *,
    leagues: list[LeagueConfig],
    seasons: list[int],
    rows: list[UnderstatCalendarMatch],
    results: list[SeasonExtractionResult],
    elapsed_seconds: float,
) -> None:
    complete_rows = sum(1 for row in rows if is_complete_match(row))
    incomplete_rows = len(rows) - complete_rows
    available_results = [result for result in results if result.status == "AVAILABLE"]
    warning_results = [result for result in results if result.status != "AVAILABLE"]
    global_status = "V8_DOM_ALL_V3_EMPTY" if not rows else "V8_DOM_ALL_V3_PARTIAL"
    if rows and not warning_results:
        global_status = "V8_DOM_ALL_V3_AVAILABLE"

    league_lines = "\n".join([f"- {league.slug} : {league.label}" for league in leagues])
    season_text = f"{min(seasons)} -> {max(seasons)}" if seasons else "none"

    by_league_lines = []
    for league in leagues:
        league_rows = [row for row in rows if row.league_slug == league.slug]
        league_results = [result for result in results if result.league_slug == league.slug]
        by_league_lines.append(
            f"- {league.slug} : rows={len(league_rows)}, available={sum(1 for item in league_results if item.status == 'AVAILABLE')}, warnings={sum(1 for item in league_results if item.status != 'AVAILABLE')}"
        )

    sample_text = "\n".join(
        [
            f"- {row.league_slug} {row.season_year} | {row.date} | {row.home_team} {row.home_goals}-{row.away_goals} {row.away_team} | xG {row.home_xg}-{row.away_xg} | match_id={row.understat_match_id}"
            for row in rows[:20]
        ]
    ) or "Aucune ligne extraite."

    content = f"""RubyBets - ML 1X2 V8 Understat DOM all leagues/seasons V3
109 - Synthese extraction DOM multi-ligues multi-saisons Understat V3

Objectif :
Extraire en une seule execution les matchs xG Understat disponibles pour les ligues et saisons RubyBets, avec une navigation calendrier plus robuste que la V1.

Correction V3 :
- Suppression de l'attente networkidle trop fragile.
- Clic semaine precedente declenche via JavaScript pour eviter les TimeoutError Playwright sur locator.click().
- Statut TOO_FEW_ROWS si le volume extrait n'est pas coherent avec une saison complete.
- Sauvegarde progressive apres chaque ligue/saison.

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
- Warning/empty/error league-seasons : {len(warning_results)}
- Rows extracted : {len(rows)}
- Complete rows : {complete_rows}
- Incomplete rows : {incomplete_rows}
- Unique Understat match IDs : {len({row.understat_match_id for row in rows if row.understat_match_id})}
- Elapsed seconds : {elapsed_seconds:.2f}
- Status : {global_status}

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
- Si le CSV 105 contient un volume coherent : valider les lignes par ligue/saison puis creer un script de matching avec ml.clean_matches.
- Si des saisons sont TOO_FEW_ROWS : ne pas les utiliser pour calculer des rolling xG avant diagnostic.
- Ne pas entrainer de modele maintenant.

Statut de suivi :
- Tache realisee si les fichiers 104, 105, 106, 107 et 108 sont generes.
- Statut source a mettre a jour : a produire -> realise pour l'extraction DOM Understat multi-ligues multi-saisons V3.
"""
    SUMMARY_PATH.write_text(content, encoding="utf-8")


# Écrit la prochaine action recommandée après extraction V3.
def write_next_action(rows: list[UnderstatCalendarMatch], results: list[SeasonExtractionResult]) -> None:
    warning_results = [result for result in results if result.status != "AVAILABLE"]
    if rows:
        content = f"""RubyBets - ML 1X2 V8 Understat DOM all leagues/seasons V3
108 - Prochaine action recommandee

Resultat :
L'extraction DOM Playwright V3 a recupere {len(rows)} lignes Understat.

Decision :
Ne pas entrainer de modele maintenant.
La prochaine action technique est de valider les volumes par ligue/saison, puis de creer un script de matching Understat -> ml.clean_matches.

Prochaine etape proposee :
1. Controler reports/evidence/ml_training/111_1x2_understat_dom_all_leagues_seasons_v3_by_league_season.csv.
2. Identifier les saisons en TOO_FEW_ROWS, EMPTY ou ERROR dans le fichier 107.
3. Controler un echantillon du fichier 105 : date, home_team, away_team, goals, xG, understat_match_id.
4. Ne garder que les ligues/saisons avec volume coherent pour le matching.
5. Creer ensuite le script de matching, sans modifier PostgreSQL au premier test.

Attention :
League-seasons avec avertissement : {len(warning_results)}.

Garde-fou :
Understat reste une source experimentale interne. Aucune integration produit, API ou frontend pour le moment.
"""
    else:
        content = """RubyBets - ML 1X2 V8 Understat DOM all leagues/seasons V3
108 - Prochaine action recommandee

Resultat :
Aucune ligne exploitable n'a ete recuperee.

Decision :
Ne pas creer de matching et ne pas lancer de travail ML.

Prochaine etape proposee :
1. Relancer uniquement EPL 2024 avec --show-browser.
2. Observer si le bouton semaine precedente change bien le calendrier.
3. Inspecter les selecteurs DOM si le calendrier ne se met pas a jour.

Garde-fou :
Aucune modification de PostgreSQL, ml.features, API, frontend, scoring V1 ou modeles sauvegardes.
"""
    NEXT_ACTION_PATH.write_text(content, encoding="utf-8")


# Sauvegarde toutes les preuves après chaque ligue/saison pour éviter de perdre l'avancement.
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
    write_summary(leagues=leagues, seasons=seasons, rows=rows, results=results, elapsed_seconds=time.time() - started_at)
    write_next_action(rows, results)


# Lance l'extraction globale V3 avec Playwright.
def run_all_leagues_seasons_extraction(
    *,
    leagues: list[LeagueConfig],
    seasons: list[int],
    headless: bool,
    max_weeks: int,
    click_delay_ms: int,
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
            expected_min_rows=0,
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

    try:
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
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9,fr;q=0.8"},
            )
            page = context.new_page()
            page.set_default_timeout(10_000)

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
                        max_weeks=max_weeks,
                        click_delay_ms=click_delay_ms,
                        PlaywrightTimeoutError=PlaywrightTimeoutError,
                    )
                    results.append(result)

                    for row in season_rows:
                        dedupe_key = row.understat_match_id or f"{row.league_slug}-{row.season_year}-{row.date}-{row.home_team}-{row.away_team}"
                        if dedupe_key not in seen_global_match_ids:
                            seen_global_match_ids.add(dedupe_key)
                            all_rows.append(row)

                    print(
                        f"    status={result.status} rows={result.rows_extracted} complete={result.complete_rows} "
                        f"weeks={result.weeks_visited} expected_min={result.expected_min_rows} error={result.error_type}"
                    )
                    persist_outputs(leagues=leagues, seasons=seasons, rows=all_rows, results=results, started_at=started_at)

            context.close()
            browser.close()

    except KeyboardInterrupt:
        print("\nExtraction interrompue manuellement. Les preuves partielles deja traitees ont ete sauvegardees.")
        persist_outputs(leagues=leagues, seasons=seasons, rows=all_rows, results=results, started_at=started_at)
        return

    complete_rows = sum(1 for row in all_rows if is_complete_match(row))
    warnings = sum(1 for result in results if result.status != "AVAILABLE")
    status = "V8_DOM_ALL_V3_AVAILABLE" if all_rows and warnings == 0 else "V8_DOM_ALL_V3_PARTIAL"
    if not all_rows:
        status = "V8_DOM_ALL_V3_EMPTY"

    print("Extraction DOM Understat V3 multi-ligues multi-saisons terminee.")
    print(f"League-season attempts: {len(results)}")
    print(f"Rows extracted: {len(all_rows)}")
    print(f"Complete rows: {complete_rows}")
    print(f"Warnings: {warnings}")
    print(f"Status: {status}")
    print(f"Summary saved: {SUMMARY_PATH}")
    print(f"Matches CSV saved: {MATCHES_CSV_PATH}")
    print(f"By season CSV saved: {BY_SEASON_CSV_PATH}")
    print(f"Errors CSV saved: {ERRORS_CSV_PATH}")
    print(f"Next action saved: {NEXT_ACTION_PATH}")


# Prépare les arguments CLI pour lancer une extraction totale ou ciblée.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extraction DOM Understat V3 multi-ligues multi-saisons pour RubyBets.")
    parser.add_argument("--start-season", type=int, default=DEFAULT_START_SEASON)
    parser.add_argument("--end-season", type=int, default=DEFAULT_END_SEASON)
    parser.add_argument("--leagues", type=str, default=None, help="Exemple : EPL,La_liga,Bundesliga")
    parser.add_argument("--max-weeks", type=int, default=DEFAULT_MAX_WEEKS_PER_SEASON)
    parser.add_argument("--click-delay-ms", type=int, default=DEFAULT_CLICK_DELAY_MS)
    parser.add_argument("--show-browser", action="store_true", help="Affiche Chromium pendant l'extraction pour debug visuel.")
    return parser.parse_args()


# Point d'entrée CLI du script.
def main() -> None:
    args = parse_args()
    seasons = build_season_range(args.start_season, args.end_season)
    leagues = build_league_configs(args.leagues)
    run_all_leagues_seasons_extraction(
        leagues=leagues,
        seasons=seasons,
        headless=not args.show_browser,
        max_weeks=args.max_weeks,
        click_delay_ms=args.click_delay_ms,
    )


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# extract_1x2_understat_dom_all_leagues_seasons_v2.py
#   -> Understat via Playwright Chromium : /league/{league_slug}/{season_year}
#   -> DOM rendu : .calendar / .calendar-prev / .calendar-date-container / .calendar-game / .teams-goals / .teams-xG
#   -> reports/evidence/ml_training/104_...summary.txt
#   -> reports/evidence/ml_training/105_...matches.csv
#   -> reports/evidence/ml_training/106_...by_league_season.csv
#   -> reports/evidence/ml_training/107_...errors.csv
#   -> reports/evidence/ml_training/108_...next_action.txt
#   X aucune écriture PostgreSQL / ml.features / API / frontend / modèle sauvegardé
