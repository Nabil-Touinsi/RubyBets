# Rôle du fichier : construire et auditer les features enrichies V17.1 goals/BTTS en mémoire, sans modifier PostgreSQL, ml.features, l'API ou le produit.

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROLLING_WINDOW = 10
STATUS_READY = "V17_1_ENRICHED_FEATURES_READY"
STATUS_REVIEW = "V17_1_ENRICHED_FEATURES_REVIEW_REQUIRED"

OUTPUT_SUMMARY = "234_multimarket_v17_1_features_summary.txt"
OUTPUT_AUDIT = "235_multimarket_v17_1_features_audit.csv"
OUTPUT_BY_LEAGUE_SEASON = "236_multimarket_v17_1_features_by_league_season.csv"
OUTPUT_DECISION = "237_multimarket_v17_1_features_decision.txt"

OVER_15_LABEL = "OVER_1_5"
UNDER_15_LABEL = "UNDER_1_5"
OVER_25_LABEL = "OVER_2_5"
UNDER_25_LABEL = "UNDER_2_5"
BTTS_YES_LABEL = "BTTS_YES"
BTTS_NO_LABEL = "BTTS_NO"

MIN_READY_ROWS = 40000
MIN_READY_MEAN_FEATURE_COVERAGE = 0.90
MAX_READY_CRITICAL_MISSING_RATE = 0.12

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class CsvFileInfo:
    path: Path
    league_code: str
    season: str


@dataclass(frozen=True)
class RollingStats:
    match_count: int
    goals_for_avg: float
    goals_against_avg: float
    total_goals_avg: float
    scored_rate: float
    conceded_rate: float
    clean_sheet_rate: float
    failed_to_score_rate: float
    over_15_rate: float
    under_15_rate: float
    over_25_rate: float
    under_25_rate: float
    btts_rate: float


@dataclass(frozen=True)
class LeagueSeasonStats:
    match_count: int
    avg_goals: float
    over_15_rate: float
    over_25_rate: float
    btts_rate: float


FEATURE_COLUMNS = [
    "home_history_count_last_10",
    "away_history_count_last_10",
    "min_history_count_last_10",
    "home_scored_at_least_1_rate_last_10",
    "away_scored_at_least_1_rate_last_10",
    "home_goals_scored_avg_last_10",
    "away_goals_scored_avg_last_10",
    "home_conceded_at_least_1_rate_last_10",
    "away_conceded_at_least_1_rate_last_10",
    "home_goals_conceded_avg_last_10",
    "away_goals_conceded_avg_last_10",
    "home_clean_sheet_rate_last_10",
    "away_clean_sheet_rate_last_10",
    "home_failed_to_score_rate_last_10",
    "away_failed_to_score_rate_last_10",
    "home_over_1_5_rate_last_10",
    "away_over_1_5_rate_last_10",
    "combined_over_1_5_rate_last_10",
    "home_under_1_5_rate_last_10",
    "away_under_1_5_rate_last_10",
    "combined_under_1_5_rate_last_10",
    "home_over_2_5_rate_last_10",
    "away_over_2_5_rate_last_10",
    "combined_over_2_5_rate_last_10",
    "home_under_2_5_rate_last_10",
    "away_under_2_5_rate_last_10",
    "combined_under_2_5_rate_last_10",
    "home_btts_rate_last_10",
    "away_btts_rate_last_10",
    "combined_btts_rate_last_10",
    "combined_goals_avg_last_10",
    "home_team_home_history_count_last_10",
    "away_team_away_history_count_last_10",
    "home_team_home_scored_rate_last_10",
    "home_team_home_conceded_rate_last_10",
    "away_team_away_scored_rate_last_10",
    "away_team_away_conceded_rate_last_10",
    "home_team_home_btts_rate_last_10",
    "away_team_away_btts_rate_last_10",
    "home_team_home_goals_scored_avg_last_10",
    "home_team_home_goals_conceded_avg_last_10",
    "away_team_away_goals_scored_avg_last_10",
    "away_team_away_goals_conceded_avg_last_10",
    "league_match_count_season_to_date",
    "league_avg_goals_season_to_date",
    "league_over_1_5_rate_season_to_date",
    "league_over_2_5_rate_season_to_date",
    "league_btts_rate_season_to_date",
    "expected_home_goals_proxy",
    "expected_away_goals_proxy",
    "expected_total_goals_proxy",
    "prob_over_1_5_proxy",
    "prob_over_2_5_proxy",
    "prob_btts_proxy",
]

CRITICAL_FEATURE_COLUMNS = [
    "min_history_count_last_10",
    "combined_over_1_5_rate_last_10",
    "combined_over_2_5_rate_last_10",
    "combined_btts_rate_last_10",
    "league_avg_goals_season_to_date",
    "expected_total_goals_proxy",
    "prob_over_1_5_proxy",
    "prob_over_2_5_proxy",
    "prob_btts_proxy",
]

LABEL_COLUMNS = [
    "target_over_under_15",
    "target_over_under_25",
    "target_btts",
]


# Retrouve la racine RubyBets depuis l'emplacement du script ou le dossier courant.
def find_project_root() -> Path:
    candidates: list[Path] = []
    current = Path(__file__).resolve()
    candidates.extend([current.parent, *current.parents])
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    for parent in candidates:
        if (parent / "data" / "ml" / "raw").exists():
            return parent
    raise FileNotFoundError("Impossible de trouver la racine projet : data/ml/raw est introuvable.")


# Retourne le dossier de preuves ML et le crée si nécessaire.
def get_evidence_dir(project_root: Path) -> Path:
    output_dir = project_root / "reports" / "evidence" / "ml_training"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# Extrait la saison depuis un nom de fichier comme E0_2024_2025.csv.
def infer_season_from_filename(path: Path) -> str:
    parts = path.stem.split("_")
    if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
        return f"{parts[-2]}_{parts[-1]}"
    return "UNKNOWN"


# Extrait le code ligue depuis le nom du fichier CSV brut.
def infer_league_code(path: Path) -> str:
    stem = path.stem
    if "_" in stem:
        return stem.split("_")[0]
    return "UNKNOWN"


# Transforme une saison 2024_2025 en année de début 2024.
def season_start_year(season: object) -> int:
    try:
        return int(str(season).split("_")[0])
    except Exception:  # noqa: BLE001 - fallback robuste pour fichiers historiques hétérogènes
        return -1


# Arrondit une valeur numérique pour stabiliser les exports.
def rounded(value: object, digits: int = 4) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return round(result, digits)
    except (TypeError, ValueError):
        return 0.0


# Calcule un ratio sans risque de division par zéro.
def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# Calcule une moyenne en ignorant les valeurs manquantes.
def safe_mean(values: Iterable[object]) -> float:
    numeric_values: list[float] = []
    for value in values:
        try:
            number = float(value)
            if not math.isnan(number) and not math.isinf(number):
                numeric_values.append(number)
        except (TypeError, ValueError):
            continue
    if not numeric_values:
        return float("nan")
    return float(np.mean(numeric_values))


# Liste les fichiers CSV bruts disponibles dans data/ml/raw.
def list_raw_csv_files(project_root: Path) -> list[CsvFileInfo]:
    raw_dir = project_root / "data" / "ml" / "raw"
    return [
        CsvFileInfo(path=path, league_code=infer_league_code(path), season=infer_season_from_filename(path))
        for path in sorted(raw_dir.rglob("*.csv"))
    ]


# Lit un CSV Football-Data avec des fallbacks d'encodage et de lignes mal formées.
def read_csv_safely(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding, engine="python", on_bad_lines="skip")
        except Exception as error:  # noqa: BLE001 - fallback volontaire sur données historiques
            last_error = error

    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            with path.open("r", encoding=encoding, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader)
                expected_columns = len(header)
                rows: list[list[str]] = []

                for row in reader:
                    if not row or all(str(value).strip() == "" for value in row):
                        continue
                    if len(row) > expected_columns:
                        continue
                    if len(row) < expected_columns:
                        row = row + [""] * (expected_columns - len(row))
                    rows.append(row)

            return pd.DataFrame(rows, columns=[str(column).strip().replace("\ufeff", "") for column in header])
        except Exception as error:  # noqa: BLE001 - fallback volontaire sur données historiques
            last_error = error

    raise RuntimeError(f"Lecture impossible du fichier {path}: {last_error}")


# Nettoie les noms de colonnes pour éviter les espaces invisibles ou BOM.
def clean_columns(columns: Iterable[object]) -> list[str]:
    return [str(column).strip().replace("\ufeff", "") for column in columns]


# Convertit une colonne en série numérique exploitable.
def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([math.nan] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


# Prépare un fichier CSV brut en ajoutant des métadonnées sans modifier le fichier original.
def prepare_raw_frame(file_info: CsvFileInfo) -> pd.DataFrame:
    frame = read_csv_safely(file_info.path)
    frame.columns = clean_columns(frame.columns)
    frame["source_file"] = file_info.path.name
    frame["league_code"] = file_info.league_code
    frame["season"] = file_info.season
    frame["season_start_year"] = season_start_year(file_info.season)
    frame["source_order"] = np.arange(len(frame))
    return frame


# Transforme tous les CSV bruts en table de matchs joués avec scores réels.
def build_raw_matches(files: list[CsvFileInfo]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for file_info in files:
        frame = prepare_raw_frame(file_info)
        required_columns = {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not required_columns.issubset(set(frame.columns)):
            continue

        home_goals = numeric_series(frame, "FTHG")
        away_goals = numeric_series(frame, "FTAG")
        valid_score = home_goals.notna() & away_goals.notna() & (home_goals >= 0) & (away_goals >= 0)
        if not valid_score.any():
            continue

        output = pd.DataFrame(
            {
                "source_file": frame["source_file"],
                "league_code": frame["league_code"],
                "season": frame["season"],
                "season_start_year": frame["season_start_year"],
                "source_order": frame["source_order"],
                "match_date": frame["Date"] if "Date" in frame.columns else "",
                "home_team": frame["HomeTeam"].astype(str),
                "away_team": frame["AwayTeam"].astype(str),
                "home_goals": home_goals,
                "away_goals": away_goals,
            }
        )
        frames.append(output[valid_score].copy())

    if not frames:
        raise RuntimeError("Aucun score réel exploitable n'a été trouvé dans data/ml/raw.")

    raw_matches = pd.concat(frames, ignore_index=True)
    return raw_matches.sort_values(
        ["season_start_year", "league_code", "source_order", "home_team", "away_team"]
    ).reset_index(drop=True)


# Calcule les statistiques rolling d'une équipe avant le match courant.
def calculate_rolling_stats(team_history: list[tuple[float, float]]) -> RollingStats:
    recent_history = team_history[-ROLLING_WINDOW:]
    if not recent_history:
        nan_value = float("nan")
        return RollingStats(
            match_count=0,
            goals_for_avg=nan_value,
            goals_against_avg=nan_value,
            total_goals_avg=nan_value,
            scored_rate=nan_value,
            conceded_rate=nan_value,
            clean_sheet_rate=nan_value,
            failed_to_score_rate=nan_value,
            over_15_rate=nan_value,
            under_15_rate=nan_value,
            over_25_rate=nan_value,
            under_25_rate=nan_value,
            btts_rate=nan_value,
        )

    goals_for = np.array([row[0] for row in recent_history], dtype="float64")
    goals_against = np.array([row[1] for row in recent_history], dtype="float64")
    total_goals = goals_for + goals_against

    return RollingStats(
        match_count=len(recent_history),
        goals_for_avg=float(goals_for.mean()),
        goals_against_avg=float(goals_against.mean()),
        total_goals_avg=float(total_goals.mean()),
        scored_rate=float((goals_for > 0).mean()),
        conceded_rate=float((goals_against > 0).mean()),
        clean_sheet_rate=float((goals_against == 0).mean()),
        failed_to_score_rate=float((goals_for == 0).mean()),
        over_15_rate=float((total_goals >= 2).mean()),
        under_15_rate=float((total_goals < 2).mean()),
        over_25_rate=float((total_goals >= 3).mean()),
        under_25_rate=float((total_goals < 3).mean()),
        btts_rate=float(((goals_for > 0) & (goals_against > 0)).mean()),
    )


# Calcule les statistiques de ligue/saison disponibles avant le match courant.
def calculate_league_season_stats(history: list[tuple[float, float]]) -> LeagueSeasonStats:
    if not history:
        nan_value = float("nan")
        return LeagueSeasonStats(
            match_count=0,
            avg_goals=nan_value,
            over_15_rate=nan_value,
            over_25_rate=nan_value,
            btts_rate=nan_value,
        )

    home_goals = np.array([row[0] for row in history], dtype="float64")
    away_goals = np.array([row[1] for row in history], dtype="float64")
    total_goals = home_goals + away_goals

    return LeagueSeasonStats(
        match_count=len(history),
        avg_goals=float(total_goals.mean()),
        over_15_rate=float((total_goals >= 2).mean()),
        over_25_rate=float((total_goals >= 3).mean()),
        btts_rate=float(((home_goals > 0) & (away_goals > 0)).mean()),
    )


# Convertit une moyenne de buts attendus en probabilité Over via une approximation Poisson simple.
def poisson_over_probability(expected_total_goals: float, threshold: int) -> float:
    try:
        lambda_value = float(expected_total_goals)
        if math.isnan(lambda_value) or math.isinf(lambda_value) or lambda_value < 0:
            return float("nan")
        probability_under_or_equal = sum(
            math.exp(-lambda_value) * (lambda_value**goals) / math.factorial(goals)
            for goals in range(threshold + 1)
        )
        return float(max(0.0, min(1.0, 1.0 - probability_under_or_equal)))
    except Exception:  # noqa: BLE001 - proxy non bloquant pour audit expérimental
        return float("nan")


# Convertit les proxies de buts attendus en probabilité BTTS via une approximation Poisson indépendante.
def poisson_btts_probability(expected_home_goals: float, expected_away_goals: float) -> float:
    try:
        home_lambda = float(expected_home_goals)
        away_lambda = float(expected_away_goals)
        if any(math.isnan(value) or math.isinf(value) or value < 0 for value in (home_lambda, away_lambda)):
            return float("nan")
        return float(max(0.0, min(1.0, (1.0 - math.exp(-home_lambda)) * (1.0 - math.exp(-away_lambda)))))
    except Exception:  # noqa: BLE001 - proxy non bloquant pour audit expérimental
        return float("nan")


# Construit les proxies de buts attendus à partir des signaux rolling, venue et ligue.
def build_expected_goal_proxies(
    home_stats: RollingStats,
    away_stats: RollingStats,
    home_venue_stats: RollingStats,
    away_venue_stats: RollingStats,
    league_stats: LeagueSeasonStats,
) -> tuple[float, float, float, float, float, float]:
    league_half_goals = league_stats.avg_goals / 2.0 if not math.isnan(float(league_stats.avg_goals)) else float("nan")

    expected_home_goals = safe_mean(
        [
            home_stats.goals_for_avg,
            away_stats.goals_against_avg,
            home_venue_stats.goals_for_avg,
            away_venue_stats.goals_against_avg,
            league_half_goals,
        ]
    )
    expected_away_goals = safe_mean(
        [
            away_stats.goals_for_avg,
            home_stats.goals_against_avg,
            away_venue_stats.goals_for_avg,
            home_venue_stats.goals_against_avg,
            league_half_goals,
        ]
    )
    expected_total_goals = safe_mean([expected_home_goals + expected_away_goals])
    prob_over_15 = poisson_over_probability(expected_total_goals, threshold=1)
    prob_over_25 = poisson_over_probability(expected_total_goals, threshold=2)
    prob_btts = poisson_btts_probability(expected_home_goals, expected_away_goals)

    return (
        expected_home_goals,
        expected_away_goals,
        expected_total_goals,
        prob_over_15,
        prob_over_25,
        prob_btts,
    )


# Construit le dataset V17.1 enrichi en mémoire à partir des scores historiques.
def build_enriched_dataset(raw_matches: pd.DataFrame) -> pd.DataFrame:
    team_history: dict[tuple[str, str], list[tuple[float, float]]] = {}
    home_venue_history: dict[tuple[str, str], list[tuple[float, float]]] = {}
    away_venue_history: dict[tuple[str, str], list[tuple[float, float]]] = {}
    league_season_history: dict[tuple[str, str], list[tuple[float, float]]] = {}
    rows: list[dict[str, object]] = []

    for match in raw_matches.itertuples(index=False):
        home_key = (str(match.league_code), str(match.home_team))
        away_key = (str(match.league_code), str(match.away_team))
        league_season_key = (str(match.league_code), str(match.season))

        home_stats = calculate_rolling_stats(team_history.get(home_key, []))
        away_stats = calculate_rolling_stats(team_history.get(away_key, []))
        home_venue_stats = calculate_rolling_stats(home_venue_history.get(home_key, []))
        away_venue_stats = calculate_rolling_stats(away_venue_history.get(away_key, []))
        league_stats = calculate_league_season_stats(league_season_history.get(league_season_key, []))

        total_goals = float(match.home_goals + match.away_goals)
        expected_home, expected_away, expected_total, prob_over_15, prob_over_25, prob_btts = build_expected_goal_proxies(
            home_stats,
            away_stats,
            home_venue_stats,
            away_venue_stats,
            league_stats,
        )

        row = {
            "source_file": match.source_file,
            "league_code": match.league_code,
            "season": match.season,
            "season_start_year": match.season_start_year,
            "source_order": match.source_order,
            "match_date": match.match_date,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "home_goals": float(match.home_goals),
            "away_goals": float(match.away_goals),
            "total_goals": total_goals,
            "target_over_under_15": OVER_15_LABEL if total_goals >= 2 else UNDER_15_LABEL,
            "target_over_under_25": OVER_25_LABEL if total_goals >= 3 else UNDER_25_LABEL,
            "target_btts": BTTS_YES_LABEL if float(match.home_goals) > 0 and float(match.away_goals) > 0 else BTTS_NO_LABEL,
            "home_history_count_last_10": home_stats.match_count,
            "away_history_count_last_10": away_stats.match_count,
            "min_history_count_last_10": min(home_stats.match_count, away_stats.match_count),
            "home_scored_at_least_1_rate_last_10": home_stats.scored_rate,
            "away_scored_at_least_1_rate_last_10": away_stats.scored_rate,
            "home_goals_scored_avg_last_10": home_stats.goals_for_avg,
            "away_goals_scored_avg_last_10": away_stats.goals_for_avg,
            "home_conceded_at_least_1_rate_last_10": home_stats.conceded_rate,
            "away_conceded_at_least_1_rate_last_10": away_stats.conceded_rate,
            "home_goals_conceded_avg_last_10": home_stats.goals_against_avg,
            "away_goals_conceded_avg_last_10": away_stats.goals_against_avg,
            "home_clean_sheet_rate_last_10": home_stats.clean_sheet_rate,
            "away_clean_sheet_rate_last_10": away_stats.clean_sheet_rate,
            "home_failed_to_score_rate_last_10": home_stats.failed_to_score_rate,
            "away_failed_to_score_rate_last_10": away_stats.failed_to_score_rate,
            "home_over_1_5_rate_last_10": home_stats.over_15_rate,
            "away_over_1_5_rate_last_10": away_stats.over_15_rate,
            "combined_over_1_5_rate_last_10": safe_mean([home_stats.over_15_rate, away_stats.over_15_rate]),
            "home_under_1_5_rate_last_10": home_stats.under_15_rate,
            "away_under_1_5_rate_last_10": away_stats.under_15_rate,
            "combined_under_1_5_rate_last_10": safe_mean([home_stats.under_15_rate, away_stats.under_15_rate]),
            "home_over_2_5_rate_last_10": home_stats.over_25_rate,
            "away_over_2_5_rate_last_10": away_stats.over_25_rate,
            "combined_over_2_5_rate_last_10": safe_mean([home_stats.over_25_rate, away_stats.over_25_rate]),
            "home_under_2_5_rate_last_10": home_stats.under_25_rate,
            "away_under_2_5_rate_last_10": away_stats.under_25_rate,
            "combined_under_2_5_rate_last_10": safe_mean([home_stats.under_25_rate, away_stats.under_25_rate]),
            "home_btts_rate_last_10": home_stats.btts_rate,
            "away_btts_rate_last_10": away_stats.btts_rate,
            "combined_btts_rate_last_10": safe_mean([home_stats.btts_rate, away_stats.btts_rate]),
            "combined_goals_avg_last_10": safe_mean([home_stats.total_goals_avg, away_stats.total_goals_avg]),
            "home_team_home_history_count_last_10": home_venue_stats.match_count,
            "away_team_away_history_count_last_10": away_venue_stats.match_count,
            "home_team_home_scored_rate_last_10": home_venue_stats.scored_rate,
            "home_team_home_conceded_rate_last_10": home_venue_stats.conceded_rate,
            "away_team_away_scored_rate_last_10": away_venue_stats.scored_rate,
            "away_team_away_conceded_rate_last_10": away_venue_stats.conceded_rate,
            "home_team_home_btts_rate_last_10": home_venue_stats.btts_rate,
            "away_team_away_btts_rate_last_10": away_venue_stats.btts_rate,
            "home_team_home_goals_scored_avg_last_10": home_venue_stats.goals_for_avg,
            "home_team_home_goals_conceded_avg_last_10": home_venue_stats.goals_against_avg,
            "away_team_away_goals_scored_avg_last_10": away_venue_stats.goals_for_avg,
            "away_team_away_goals_conceded_avg_last_10": away_venue_stats.goals_against_avg,
            "league_match_count_season_to_date": league_stats.match_count,
            "league_avg_goals_season_to_date": league_stats.avg_goals,
            "league_over_1_5_rate_season_to_date": league_stats.over_15_rate,
            "league_over_2_5_rate_season_to_date": league_stats.over_25_rate,
            "league_btts_rate_season_to_date": league_stats.btts_rate,
            "expected_home_goals_proxy": expected_home,
            "expected_away_goals_proxy": expected_away,
            "expected_total_goals_proxy": expected_total,
            "prob_over_1_5_proxy": prob_over_15,
            "prob_over_2_5_proxy": prob_over_25,
            "prob_btts_proxy": prob_btts,
        }
        rows.append(row)

        team_history.setdefault(home_key, []).append((float(match.home_goals), float(match.away_goals)))
        team_history.setdefault(away_key, []).append((float(match.away_goals), float(match.home_goals)))
        home_venue_history.setdefault(home_key, []).append((float(match.home_goals), float(match.away_goals)))
        away_venue_history.setdefault(away_key, []).append((float(match.away_goals), float(match.home_goals)))
        league_season_history.setdefault(league_season_key, []).append((float(match.home_goals), float(match.away_goals)))

    return pd.DataFrame(rows)


# Calcule l'audit détaillé des features enrichies.
def build_feature_audit(dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total_rows = len(dataset)

    for feature in FEATURE_COLUMNS:
        series = pd.to_numeric(dataset[feature], errors="coerce") if feature in dataset.columns else pd.Series(dtype="float64")
        missing_count = int(series.isna().sum()) if len(series) else total_rows
        available_count = int(series.notna().sum()) if len(series) else 0
        quantiles = series.dropna().quantile([0.05, 0.25, 0.50, 0.75, 0.95]) if available_count else pd.Series(dtype="float64")
        rows.append(
            {
                "feature": feature,
                "is_critical": feature in CRITICAL_FEATURE_COLUMNS,
                "missing_count": missing_count,
                "missing_rate": rounded(safe_rate(missing_count, total_rows)),
                "available_count": available_count,
                "coverage_rate": rounded(safe_rate(available_count, total_rows)),
                "mean": rounded(series.mean()) if available_count else 0.0,
                "std": rounded(series.std()) if available_count > 1 else 0.0,
                "min": rounded(series.min()) if available_count else 0.0,
                "p05": rounded(quantiles.loc[0.05]) if available_count else 0.0,
                "p25": rounded(quantiles.loc[0.25]) if available_count else 0.0,
                "p50": rounded(quantiles.loc[0.50]) if available_count else 0.0,
                "p75": rounded(quantiles.loc[0.75]) if available_count else 0.0,
                "p95": rounded(quantiles.loc[0.95]) if available_count else 0.0,
                "max": rounded(series.max()) if available_count else 0.0,
                "zero_count": int((series.fillna(999999) == 0).sum()) if len(series) else 0,
                "zero_rate": rounded(safe_rate(int((series.fillna(999999) == 0).sum()), total_rows)) if len(series) else 0.0,
            }
        )

    return pd.DataFrame(rows).sort_values(["is_critical", "missing_rate", "feature"], ascending=[False, False, True])


# Calcule la couverture et les distributions par ligue/saison.
def build_by_league_season(dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = dataset.groupby(["league_code", "season"], dropna=False)

    for (league_code, season), group in grouped:
        critical_missing = group[CRITICAL_FEATURE_COLUMNS].isna().any(axis=1)
        feature_coverage_rates = [safe_rate(int(group[column].notna().sum()), len(group)) for column in FEATURE_COLUMNS]
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "rows": len(group),
                "over_1_5_rows": int((group["target_over_under_15"] == OVER_15_LABEL).sum()),
                "under_1_5_rows": int((group["target_over_under_15"] == UNDER_15_LABEL).sum()),
                "over_1_5_rate": rounded(safe_rate(int((group["target_over_under_15"] == OVER_15_LABEL).sum()), len(group))),
                "over_2_5_rows": int((group["target_over_under_25"] == OVER_25_LABEL).sum()),
                "under_2_5_rows": int((group["target_over_under_25"] == UNDER_25_LABEL).sum()),
                "over_2_5_rate": rounded(safe_rate(int((group["target_over_under_25"] == OVER_25_LABEL).sum()), len(group))),
                "btts_yes_rows": int((group["target_btts"] == BTTS_YES_LABEL).sum()),
                "btts_no_rows": int((group["target_btts"] == BTTS_NO_LABEL).sum()),
                "btts_yes_rate": rounded(safe_rate(int((group["target_btts"] == BTTS_YES_LABEL).sum()), len(group))),
                "avg_total_goals": rounded(group["total_goals"].mean()),
                "mean_feature_coverage_rate": rounded(float(np.mean(feature_coverage_rates)) if feature_coverage_rates else 0.0),
                "critical_missing_rows": int(critical_missing.sum()),
                "critical_missing_rate": rounded(safe_rate(int(critical_missing.sum()), len(group))),
                "avg_expected_total_goals_proxy": rounded(group["expected_total_goals_proxy"].mean()),
                "avg_prob_over_1_5_proxy": rounded(group["prob_over_1_5_proxy"].mean()),
                "avg_prob_over_2_5_proxy": rounded(group["prob_over_2_5_proxy"].mean()),
                "avg_prob_btts_proxy": rounded(group["prob_btts_proxy"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["season", "league_code"]).reset_index(drop=True)


# Résume les distributions globales des labels de marché.
def build_label_summary(dataset: pd.DataFrame) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    total_rows = len(dataset)
    for column in LABEL_COLUMNS:
        counts = dataset[column].value_counts(dropna=False).to_dict()
        summary[column] = {
            "counts": {str(key): int(value) for key, value in counts.items()},
            "rates": {str(key): rounded(safe_rate(int(value), total_rows)) for key, value in counts.items()},
        }
    return summary


# Détermine si le dataset enrichi est suffisamment couvert pour préparer V17.2 à V17.4.
def decide_status(dataset: pd.DataFrame, audit: pd.DataFrame) -> tuple[str, dict[str, object]]:
    critical_audit = audit[audit["is_critical"] == True].copy()  # noqa: E712 - comparaison explicite lisible en CSV
    mean_critical_coverage = float(critical_audit["coverage_rate"].mean()) if not critical_audit.empty else 0.0
    max_critical_missing_rate = float(critical_audit["missing_rate"].max()) if not critical_audit.empty else 1.0
    critical_missing_rows = int(dataset[CRITICAL_FEATURE_COLUMNS].isna().any(axis=1).sum())
    critical_missing_rate = safe_rate(critical_missing_rows, len(dataset))

    checks = {
        "dataset_rows": len(dataset),
        "mean_critical_coverage": rounded(mean_critical_coverage),
        "max_critical_missing_rate": rounded(max_critical_missing_rate),
        "critical_missing_rows": critical_missing_rows,
        "critical_missing_rate": rounded(critical_missing_rate),
        "ready_rows_check": len(dataset) >= MIN_READY_ROWS,
        "ready_mean_coverage_check": mean_critical_coverage >= MIN_READY_MEAN_FEATURE_COVERAGE,
        "ready_missing_rate_check": critical_missing_rate <= MAX_READY_CRITICAL_MISSING_RATE,
    }
    ready = bool(
        checks["ready_rows_check"]
        and checks["ready_mean_coverage_check"]
        and checks["ready_missing_rate_check"]
    )
    return STATUS_READY if ready else STATUS_REVIEW, checks


# Génère la synthèse texte V17.1.
def write_summary(
    output_path: Path,
    status: str,
    files: list[CsvFileInfo],
    raw_matches: pd.DataFrame,
    dataset: pd.DataFrame,
    audit: pd.DataFrame,
    by_league_season: pd.DataFrame,
    decision_checks: dict[str, object],
) -> None:
    label_summary = build_label_summary(dataset)
    critical_audit = audit[audit["is_critical"] == True].copy()  # noqa: E712 - comparaison explicite lisible en CSV
    lines = [
        "RubyBets - V17.1 enriched goals/BTTS features audit",
        "Scope: experimental ML only, no product integration.",
        f"Status: {status}",
        "",
        f"CSV analysés: {len(files)}",
        f"Lignes avec score exploitable: {len(raw_matches)}",
        f"Lignes dataset enrichi: {len(dataset)}",
        f"Ligues: {', '.join(sorted(dataset['league_code'].astype(str).unique()))}",
        f"Saisons: {dataset['season'].nunique()}",
        f"Features enrichies créées: {len(FEATURE_COLUMNS)}",
        f"Features critiques auditées: {len(CRITICAL_FEATURE_COLUMNS)}",
        "",
        "Labels construits:",
    ]
    for column, values in label_summary.items():
        lines.append(f"- {column}: counts={values['counts']} rates={values['rates']}")

    lines.extend(
        [
            "",
            "Audit couverture critique:",
            f"- Mean critical feature coverage: {decision_checks['mean_critical_coverage']}",
            f"- Max critical missing rate by feature: {decision_checks['max_critical_missing_rate']}",
            f"- Rows with at least one critical missing value: {decision_checks['critical_missing_rows']}",
            f"- Critical missing row rate: {decision_checks['critical_missing_rate']}",
            "",
            "Top features critiques les plus manquantes:",
        ]
    )
    for row in critical_audit.sort_values("missing_rate", ascending=False).head(10).itertuples(index=False):
        lines.append(f"- {row.feature}: missing_rate={row.missing_rate} missing_count={row.missing_count}")

    weakest_segments = by_league_season.sort_values(["critical_missing_rate", "rows"], ascending=[False, False]).head(8)
    lines.extend(["", "Segments ligue/saison à surveiller:"])
    for row in weakest_segments.itertuples(index=False):
        lines.append(
            f"- {row.league_code} {row.season}: rows={row.rows}, "
            f"critical_missing_rate={row.critical_missing_rate}, avg_total_goals={row.avg_total_goals}"
        )

    lines.extend(
        [
            "",
            "Décision:",
            "- Dataset prêt pour V17.2/V17.3/V17.4 si le statut est V17_1_ENRICHED_FEATURES_READY.",
            "- Le script ne sauvegarde aucun modèle et ne modifie ni PostgreSQL, ni ml.features, ni l'API, ni le frontend.",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


# Génère le fichier de décision V17.1.
def write_decision(output_path: Path, status: str, decision_checks: dict[str, object]) -> None:
    if status == STATUS_READY:
        decision = "READY_FOR_V17_2_TO_V17_4"
        explanation = (
            "Les features enrichies goals/BTTS sont suffisamment couvertes pour préparer les retests "
            "Over/Under 1.5, O/U 2.5 et BTTS en mémoire."
        )
    else:
        decision = "REVIEW_BEFORE_V17_2"
        explanation = (
            "Le dataset enrichi existe, mais la couverture des features critiques doit être revue avant "
            "de lancer les versions V17.2 à V17.4."
        )

    lines = [
        "RubyBets - Décision V17.1 features enrichies goals/BTTS",
        f"Status: {status}",
        f"Decision: {decision}",
        "",
        "Critères contrôlés:",
        f"- Dataset rows >= {MIN_READY_ROWS}: {decision_checks['ready_rows_check']} ({decision_checks['dataset_rows']})",
        (
            f"- Mean critical coverage >= {MIN_READY_MEAN_FEATURE_COVERAGE}: "
            f"{decision_checks['ready_mean_coverage_check']} ({decision_checks['mean_critical_coverage']})"
        ),
        (
            f"- Critical missing row rate <= {MAX_READY_CRITICAL_MISSING_RATE}: "
            f"{decision_checks['ready_missing_rate_check']} ({decision_checks['critical_missing_rate']})"
        ),
        "",
        "Décision opérationnelle:",
        f"- {explanation}",
        "- Aucune intégration produit n'est autorisée à cette étape.",
        "- Aucun marché UNDER_1_5, O/U 2.5 ou BTTS ne doit entrer dans V17.5 sans passer les gates prévues.",
        "- Le scoring explicable V1 reste le socle officiel de RubyBets.",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


# Lance toute la construction V17.1 et écrit les preuves dans reports/evidence/ml_training/.
def main() -> None:
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)

    print("Construction des features enrichies V17.1 goals / BTTS en mémoire...")
    files = list_raw_csv_files(project_root)
    raw_matches = build_raw_matches(files)
    dataset = build_enriched_dataset(raw_matches)
    audit = build_feature_audit(dataset)
    by_league_season = build_by_league_season(dataset)
    status, decision_checks = decide_status(dataset, audit)

    audit.to_csv(evidence_dir / OUTPUT_AUDIT, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    write_summary(evidence_dir / OUTPUT_SUMMARY, status, files, raw_matches, dataset, audit, by_league_season, decision_checks)
    write_decision(evidence_dir / OUTPUT_DECISION, status, decision_checks)

    print("OK - Construction features enrichies V17.1 terminée.")
    print(f"Status: {status}")
    print(f"CSV analysés: {len(files)}")
    print(f"Lignes dataset: {len(dataset)}")
    print(f"Features enrichies créées: {len(FEATURE_COLUMNS)}")
    print(f"Missing values critiques: {decision_checks['critical_missing_rows']}")
    print("Décision: prêt pour V17.2 si les features sont suffisamment couvertes.")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Audit CSV saved: {evidence_dir / OUTPUT_AUDIT}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# data/ml/raw/*.csv
#        │
#        ▼
# backend/scripts/ml/build_multimarket_v17_1_enriched_features.py
#        │
#        ▼
# reports/evidence/ml_training/234 à 237
#
# Ne communique pas avec PostgreSQL, ml.features, models/, l'API, le frontend ou le scoring explicable V1.
