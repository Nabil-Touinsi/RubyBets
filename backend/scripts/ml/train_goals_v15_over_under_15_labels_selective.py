# Rôle du fichier : tester V15 Over/Under 1.5 en stratégie selective labels-only, à partir des scores réels et des features construites en mémoire.

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


TARGET_COLUMN = "target_over_under_15"
OVER_LABEL = "OVER_1_5"
UNDER_LABEL = "UNDER_1_5"
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

OUTPUT_SUMMARY = "214_goals_v15_over_under_15_labels_summary.txt"
OUTPUT_RESULTS = "215_goals_v15_over_under_15_labels_results.csv"
OUTPUT_BY_LEAGUE_SEASON = "216_goals_v15_over_under_15_labels_by_league_season.csv"
OUTPUT_BY_SIGNAL = "217_goals_v15_over_under_15_labels_by_signal.csv"
OUTPUT_ERROR_PATTERNS = "218_goals_v15_over_under_15_labels_error_patterns.csv"
OUTPUT_DECISION = "219_goals_v15_over_under_15_labels_decision.txt"

VALIDATION_SEASON = "2021_2022"
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]
ROLLING_WINDOW = 10

STRONG_MIN_ACCURACY = 0.78
STRONG_MIN_COVERAGE = 0.50
STRONG_MIN_SELECTED_ROWS = 2500
REVIEW_MIN_ACCURACY = 0.74
REVIEW_MIN_COVERAGE = 0.45
REVIEW_MIN_SELECTED_ROWS = 1800
EXPERIMENTAL_MIN_ACCURACY = 0.70
EXPERIMENTAL_MIN_COVERAGE = 0.30
MIN_MAJOR_SEGMENT_ROWS = 80
MIN_MAJOR_SEGMENT_ACCURACY = 0.68
MIN_UNDER_ROWS_FOR_MIXED = 20
MIN_UNDER_ACCURACY_WARNING = 0.55

OVER_RATE_THRESHOLDS = [0.70, 0.75, 0.80]
UNDER_RATE_THRESHOLDS = [0.40, 0.45, 0.50, 0.55]
MIN_HISTORY_THRESHOLDS = [8, 10]
MIN_OVER_GOALS_AVG_THRESHOLDS: list[float | None] = [None]
MAX_UNDER_GOALS_AVG_THRESHOLDS: list[float | None] = [None]

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class CsvFileInfo:
    path: Path
    league_code: str
    season: str


@dataclass(frozen=True)
class TeamHistoryStats:
    match_count: int
    goals_for_avg: float
    goals_against_avg: float
    total_goals_avg: float
    over_15_rate: float
    over_25_rate: float
    btts_rate: float
    scored_rate: float
    clean_sheet_rate: float
    points_avg: float


@dataclass(frozen=True)
class V15Policy:
    over_rate_threshold: float
    under_rate_threshold: float
    min_history_count: int
    min_over_goals_avg: float | None
    max_under_goals_avg: float | None

    @property
    def name(self) -> str:
        over_avg = "none" if self.min_over_goals_avg is None else f"{self.min_over_goals_avg:.1f}".replace(".", "")
        under_avg = "none" if self.max_under_goals_avg is None else f"{self.max_under_goals_avg:.1f}".replace(".", "")
        return (
            "v15_ou15_labels"
            f"_ot{self.over_rate_threshold:.2f}"
            f"_ut{self.under_rate_threshold:.2f}"
            f"_mh{self.min_history_count}"
            f"_og{over_avg}"
            f"_ug{under_avg}"
        ).replace(".", "")


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


# Arrondit une valeur numérique pour stabiliser les sorties.
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


# Calcule les statistiques rolling d'une équipe avant le match courant.
def calculate_team_stats(team_history: list[tuple[float, float]]) -> TeamHistoryStats:
    recent_history = team_history[-ROLLING_WINDOW:]
    if not recent_history:
        return TeamHistoryStats(
            match_count=0,
            goals_for_avg=0.0,
            goals_against_avg=0.0,
            total_goals_avg=0.0,
            over_15_rate=0.0,
            over_25_rate=0.0,
            btts_rate=0.0,
            scored_rate=0.0,
            clean_sheet_rate=0.0,
            points_avg=0.0,
        )

    goals_for = np.array([row[0] for row in recent_history], dtype="float64")
    goals_against = np.array([row[1] for row in recent_history], dtype="float64")
    total_goals = goals_for + goals_against
    points = np.where(goals_for > goals_against, 3, np.where(goals_for == goals_against, 1, 0))

    return TeamHistoryStats(
        match_count=len(recent_history),
        goals_for_avg=float(goals_for.mean()),
        goals_against_avg=float(goals_against.mean()),
        total_goals_avg=float(total_goals.mean()),
        over_15_rate=float((total_goals >= 2).mean()),
        over_25_rate=float((total_goals >= 3).mean()),
        btts_rate=float(((goals_for > 0) & (goals_against > 0)).mean()),
        scored_rate=float((goals_for > 0).mean()),
        clean_sheet_rate=float((goals_against == 0).mean()),
        points_avg=float(points.mean()),
    )


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
    return raw_matches.sort_values(["season_start_year", "league_code", "source_order", "home_team", "away_team"]).reset_index(drop=True)


# Construit le dataset V15 avec labels O/U 1.5 et features rolling calculées en mémoire.
def build_v15_dataset(project_root: Path) -> tuple[pd.DataFrame, list[CsvFileInfo]]:
    files = list_raw_csv_files(project_root)
    raw_matches = build_raw_matches(files)
    team_history: dict[str, list[tuple[float, float]]] = {}
    rows: list[dict[str, object]] = []

    for match in raw_matches.itertuples(index=False):
        home_stats = calculate_team_stats(team_history.get(match.home_team, []))
        away_stats = calculate_team_stats(team_history.get(match.away_team, []))
        total_goals = float(match.home_goals + match.away_goals)

        row = {
            "source_file": match.source_file,
            "league_code": match.league_code,
            "season": match.season,
            "season_start_year": match.season_start_year,
            "match_date": match.match_date,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "home_goals": match.home_goals,
            "away_goals": match.away_goals,
            "total_goals": total_goals,
            TARGET_COLUMN: OVER_LABEL if total_goals >= 2 else UNDER_LABEL,
            "home_history_count_last10": home_stats.match_count,
            "away_history_count_last10": away_stats.match_count,
            "min_history_count_last10": min(home_stats.match_count, away_stats.match_count),
            "home_goals_for_avg_last10": home_stats.goals_for_avg,
            "away_goals_for_avg_last10": away_stats.goals_for_avg,
            "home_goals_against_avg_last10": home_stats.goals_against_avg,
            "away_goals_against_avg_last10": away_stats.goals_against_avg,
            "home_total_goals_avg_last10": home_stats.total_goals_avg,
            "away_total_goals_avg_last10": away_stats.total_goals_avg,
            "combined_total_goals_avg_last10": home_stats.total_goals_avg + away_stats.total_goals_avg,
            "home_over_15_rate_last10": home_stats.over_15_rate,
            "away_over_15_rate_last10": away_stats.over_15_rate,
            "combined_over_15_rate_last10": (home_stats.over_15_rate + away_stats.over_15_rate) / 2.0,
            "home_over_25_rate_last10": home_stats.over_25_rate,
            "away_over_25_rate_last10": away_stats.over_25_rate,
            "combined_over_25_rate_last10": (home_stats.over_25_rate + away_stats.over_25_rate) / 2.0,
            "home_btts_rate_last10": home_stats.btts_rate,
            "away_btts_rate_last10": away_stats.btts_rate,
            "combined_btts_rate_last10": (home_stats.btts_rate + away_stats.btts_rate) / 2.0,
            "home_scored_rate_last10": home_stats.scored_rate,
            "away_scored_rate_last10": away_stats.scored_rate,
            "scored_rate_sum_last10": home_stats.scored_rate + away_stats.scored_rate,
            "home_clean_sheet_rate_last10": home_stats.clean_sheet_rate,
            "away_clean_sheet_rate_last10": away_stats.clean_sheet_rate,
            "clean_sheet_rate_sum_last10": home_stats.clean_sheet_rate + away_stats.clean_sheet_rate,
            "points_avg_diff_last10": home_stats.points_avg - away_stats.points_avg,
        }
        rows.append(row)

        team_history.setdefault(match.home_team, []).append((float(match.home_goals), float(match.away_goals)))
        team_history.setdefault(match.away_team, []).append((float(match.away_goals), float(match.home_goals)))

    dataset = pd.DataFrame(rows)
    return dataset, files


# Crée toutes les politiques V15 à tester sur validation.
def build_policies() -> list[V15Policy]:
    policies: list[V15Policy] = []
    for over_threshold in OVER_RATE_THRESHOLDS:
        for under_threshold in UNDER_RATE_THRESHOLDS:
            for min_history in MIN_HISTORY_THRESHOLDS:
                for over_goals_avg in MIN_OVER_GOALS_AVG_THRESHOLDS:
                    for under_goals_avg in MAX_UNDER_GOALS_AVG_THRESHOLDS:
                        policies.append(
                            V15Policy(
                                over_rate_threshold=over_threshold,
                                under_rate_threshold=under_threshold,
                                min_history_count=min_history,
                                min_over_goals_avg=over_goals_avg,
                                max_under_goals_avg=under_goals_avg,
                            )
                        )
    return policies


# Applique une politique V15 : Over si signal buts fort, Under si signal buts faible, sinon abstention.
def apply_policy(dataframe: pd.DataFrame, policy: V15Policy) -> pd.DataFrame:
    output = dataframe.copy()
    numeric_columns = [
        "combined_over_15_rate_last10",
        "combined_total_goals_avg_last10",
        "min_history_count_last10",
        "combined_over_25_rate_last10",
        "combined_btts_rate_last10",
        "clean_sheet_rate_sum_last10",
    ]
    for column in numeric_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0.0)

    over_mask = (
        (output["combined_over_15_rate_last10"] >= policy.over_rate_threshold)
        & (output["min_history_count_last10"] >= policy.min_history_count)
    )
    under_mask = (
        (output["combined_over_15_rate_last10"] <= policy.under_rate_threshold)
        & (output["min_history_count_last10"] >= policy.min_history_count)
    )

    if policy.min_over_goals_avg is not None:
        over_mask = over_mask & (output["combined_total_goals_avg_last10"] >= policy.min_over_goals_avg)
    if policy.max_under_goals_avg is not None:
        under_mask = under_mask & (output["combined_total_goals_avg_last10"] <= policy.max_under_goals_avg)

    selected_mask = over_mask | under_mask
    recommendation = np.where(over_mask, OVER_LABEL, np.where(under_mask, UNDER_LABEL, "ABSTAIN"))

    output["v15_strategy"] = policy.name
    output["v15_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v15_recommendation"] = recommendation
    output["v15_is_correct"] = (output[TARGET_COLUMN].astype(str) == output["v15_recommendation"].astype(str)) & selected_mask
    output["v15_signal_strength"] = pd.cut(
        output["combined_over_15_rate_last10"],
        bins=[-0.01, 0.45, 0.65, 0.80, 1.01],
        labels=["LOW_GOALS_SIGNAL", "MEDIUM_GOALS_SIGNAL", "HIGH_GOALS_SIGNAL", "VERY_HIGH_GOALS_SIGNAL"],
        include_lowest=True,
    ).astype(str)
    return output


# Calcule les métriques principales d'une politique.
def evaluate_policy(dataframe: pd.DataFrame, policy: V15Policy, split_name: str) -> dict[str, object]:
    predictions = apply_policy(dataframe, policy)
    selected = predictions[predictions["v15_recommendation_status"] == RECOMMEND_STATUS]
    selected_rows = len(selected)
    total_rows = len(predictions)
    over_selected = selected[selected["v15_recommendation"] == OVER_LABEL]
    under_selected = selected[selected["v15_recommendation"] == UNDER_LABEL]

    return {
        "strategy": policy.name,
        "split": split_name,
        "accuracy": rounded(safe_rate(int(selected["v15_is_correct"].sum()), selected_rows)),
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "selected_rows": selected_rows,
        "total_rows": total_rows,
        "over_rows": len(over_selected),
        "under_rows": len(under_selected),
        "over_accuracy": rounded(safe_rate(int(over_selected["v15_is_correct"].sum()), len(over_selected))),
        "under_accuracy": rounded(safe_rate(int(under_selected["v15_is_correct"].sum()), len(under_selected))),
        "over_rate_threshold": policy.over_rate_threshold,
        "under_rate_threshold": policy.under_rate_threshold,
        "min_history_count": policy.min_history_count,
        "min_over_goals_avg": "none" if policy.min_over_goals_avg is None else policy.min_over_goals_avg,
        "max_under_goals_avg": "none" if policy.max_under_goals_avg is None else policy.max_under_goals_avg,
    }


# Sélectionne la meilleure stratégie V15 sur validation en conservant un minimum de vrais signaux Under.
def select_best_policy(validation: pd.DataFrame, policies: list[V15Policy]) -> tuple[V15Policy, pd.DataFrame]:
    rows = [evaluate_policy(validation, policy, "validation") for policy in policies]
    results = pd.DataFrame(rows)

    candidates = results[
        (results["coverage"] >= REVIEW_MIN_COVERAGE)
        & (results["selected_rows"] >= 800)
        & (results["under_rows"] >= MIN_UNDER_ROWS_FOR_MIXED)
    ].copy()
    if candidates.empty:
        candidates = results[(results["coverage"] >= EXPERIMENTAL_MIN_COVERAGE) & (results["selected_rows"] >= 500)].copy()
    if candidates.empty:
        candidates = results.copy()

    candidates = candidates.sort_values(
        by=["accuracy", "coverage", "selected_rows"],
        ascending=[False, False, False],
    )
    best_row = candidates.iloc[0]

    for policy in policies:
        if policy.name == best_row["strategy"]:
            return policy, results

    raise RuntimeError("Impossible de retrouver la meilleure politique V15 sélectionnée.")


# Construit les métriques par ligue et saison sur le test final.
def build_by_league_season(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v15_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    grouped = selected.groupby(["league_code", "season"], dropna=False)
    rows: list[dict[str, object]] = []
    for (league_code, season), group in grouped:
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v15_is_correct"].sum()), len(group))),
                "over_rows": int((group["v15_recommendation"] == OVER_LABEL).sum()),
                "under_rows": int((group["v15_recommendation"] == UNDER_LABEL).sum()),
                "avg_combined_over_15_rate": rounded(group["combined_over_15_rate_last10"].mean()),
                "is_major_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS,
            }
        )

    return pd.DataFrame(rows).sort_values(["accuracy", "selected_rows"], ascending=[True, False])


# Construit les métriques par recommandation et force de signal.
def build_by_signal(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v15_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    grouped = selected.groupby(["v15_recommendation", "v15_signal_strength"], dropna=False)
    rows: list[dict[str, object]] = []
    for (recommendation, signal_strength), group in grouped:
        rows.append(
            {
                "recommendation": recommendation,
                "signal_strength": signal_strength,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v15_is_correct"].sum()), len(group))),
                "avg_combined_over_15_rate": rounded(group["combined_over_15_rate_last10"].mean()),
                "avg_combined_total_goals": rounded(group["combined_total_goals_avg_last10"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["recommendation", "signal_strength"])


# Construit un extrait des erreurs restantes sur le test final.
def build_error_patterns(final_predictions: pd.DataFrame) -> pd.DataFrame:
    errors = final_predictions[
        (final_predictions["v15_recommendation_status"] == RECOMMEND_STATUS)
        & (~final_predictions["v15_is_correct"])
    ].copy()
    if errors.empty:
        return pd.DataFrame()

    keep_columns = [
        "league_code",
        "season",
        "match_date",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "total_goals",
        TARGET_COLUMN,
        "v15_recommendation",
        "combined_over_15_rate_last10",
        "combined_total_goals_avg_last10",
        "combined_over_25_rate_last10",
        "combined_btts_rate_last10",
        "min_history_count_last10",
    ]
    return errors[keep_columns].sort_values(["season", "league_code", "match_date"]).head(500)


# Détermine le statut V15 selon les résultats de test final.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    coverage = float(metrics.get("coverage", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))
    under_rows = int(metrics.get("under_rows", 0))
    under_accuracy = float(metrics.get("under_accuracy", 0.0))

    major_fragile_segments = 0
    if not by_league_season.empty:
        major_segments = by_league_season[by_league_season["is_major_segment"] == True]  # noqa: E712 - lisible pour DataFrame
        major_fragile_segments = len(major_segments[major_segments["accuracy"] < MIN_MAJOR_SEGMENT_ACCURACY])

    blocking_reasons: list[str] = []
    warnings_list: list[str] = []

    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) ligue/saison majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")
    if under_rows < 100:
        warnings_list.append("Volume UNDER_1_5 faible : le signal principal reste surtout OVER_1_5.")
    if under_rows > 0 and under_accuracy < MIN_UNDER_ACCURACY_WARNING:
        warnings_list.append("Accuracy UNDER_1_5 faible : ne pas présenter V15 comme un vrai modèle équilibré Over/Under.")

    if accuracy >= STRONG_MIN_ACCURACY and coverage >= STRONG_MIN_COVERAGE and selected_rows >= STRONG_MIN_SELECTED_ROWS:
        if under_rows >= 100 and under_accuracy >= MIN_UNDER_ACCURACY_WARNING and major_fragile_segments == 0:
            return "V15_OVER_UNDER_15_STRONG_REVIEW", blocking_reasons, warnings_list
        return "V15_OVER_15_SIGNAL_REVIEW_WITH_UNDER_WARNING", blocking_reasons, warnings_list

    if accuracy >= REVIEW_MIN_ACCURACY and coverage >= REVIEW_MIN_COVERAGE and selected_rows >= REVIEW_MIN_SELECTED_ROWS:
        return "V15_OVER_UNDER_15_REVIEW", blocking_reasons, warnings_list

    if accuracy >= EXPERIMENTAL_MIN_ACCURACY and coverage >= EXPERIMENTAL_MIN_COVERAGE:
        warnings_list.append("Le signal est exploitable comme expérience, mais trop faible pour une validation forte.")
        return "V15_OVER_UNDER_15_EXPERIMENTAL_ONLY", blocking_reasons, warnings_list

    blocking_reasons.append("Accuracy ou couverture insuffisante pour conserver V15 comme candidat fiable.")
    return "V15_OVER_UNDER_15_REJECTED", blocking_reasons, warnings_list


# Écrit la synthèse texte V15.
def write_summary(
    evidence_dir: Path,
    dataset: pd.DataFrame,
    files: list[CsvFileInfo],
    best_policy: V15Policy,
    validation_metrics: dict[str, object],
    test_metrics: dict[str, object],
    by_league_season: pd.DataFrame,
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    seasons = sorted(dataset["season"].astype(str).unique())
    leagues = sorted(dataset["league_code"].astype(str).unique())
    selected_rows = int(test_metrics.get("selected_rows", 0))
    over_rows = int(test_metrics.get("over_rows", 0))
    under_rows = int(test_metrics.get("under_rows", 0))
    lowest_segment = "Aucun"
    if not by_league_season.empty:
        first = by_league_season.iloc[0]
        lowest_segment = f"{first['league_code']} {first['season']} avec accuracy {first['accuracy']} sur {first['selected_rows']} matchs sélectionnés"

    lines = [
        "RubyBets - ML Goals V15 Over/Under 1.5 labels-only selective",
        "214 - Synthèse expérience V15",
        "",
        "Objectif :",
        "Tester une stratégie selective sur le marché Over/Under 1.5 à partir des scores réels et de features rolling construites en mémoire, sans cotes O/U 1.5.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "",
        "Périmètre data :",
        f"- CSV analysés : {len(files)}",
        f"- Lignes dataset V15 O/U 1.5 : {len(dataset)}",
        f"- Ligues : {', '.join(leagues)}",
        f"- Saisons : {min(seasons)} -> {max(seasons)}",
        f"- Validation seasons : {VALIDATION_SEASON}",
        f"- Test seasons : {', '.join(TEST_SEASONS)}",
        "",
        "Distribution des labels :",
        f"- OVER_1_5 rows : {int((dataset[TARGET_COLUMN] == OVER_LABEL).sum())}",
        f"- UNDER_1_5 rows : {int((dataset[TARGET_COLUMN] == UNDER_LABEL).sum())}",
        "",
        "Meilleure stratégie V15 sélectionnée sur validation :",
        f"- Strategy : {best_policy.name}",
        f"- Validation accuracy : {validation_metrics.get('accuracy')}",
        f"- Validation coverage : {validation_metrics.get('coverage')}",
        f"- Validation selected rows : {validation_metrics.get('selected_rows')}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {selected_rows}",
        f"- OVER_1_5 rows : {over_rows}",
        f"- UNDER_1_5 rows : {under_rows}",
        f"- OVER_1_5 accuracy : {test_metrics.get('over_accuracy')}",
        f"- UNDER_1_5 accuracy : {test_metrics.get('under_accuracy')}",
        f"- OVER_1_5 share : {rounded(safe_rate(over_rows, selected_rows))}",
        f"- UNDER_1_5 share : {rounded(safe_rate(under_rows, selected_rows))}",
        "",
        "Stabilité rapide :",
        f"- Segments ligue/saison analysés : {len(by_league_season)}",
        f"- Segment le plus bas : {lowest_segment}",
        "",
        "Raisons bloquantes :",
        f"- {'Aucune.' if not blocking_reasons else '; '.join(blocking_reasons)}",
        "",
        "Points de vigilance :",
        f"- {'Aucun.' if not warnings_list else '; '.join(warnings_list)}",
        "",
        "Décision produit :",
        "Ne pas intégrer V15 au produit à ce stade. V15 documente surtout un signal OVER_1_5 fréquent ; le scoring explicable V1 reste le socle officiel.",
        "",
        "Statut de suivi :",
        "- V14 Over/Under 2.5 selective : réalisée en REVIEW.",
        "- V15 Over/Under 1.5 labels-only selective : réalisée si les fichiers 214 à 219 sont générés.",
        "- Prochaine étape : tester V16 BTTS labels-only avant de construire un éventuel sélecteur V17.",
    ]
    (evidence_dir / OUTPUT_SUMMARY).write_text("\n".join(lines), encoding="utf-8")


# Écrit la décision opérationnelle V15.
def write_decision(
    evidence_dir: Path,
    best_policy: V15Policy,
    test_metrics: dict[str, object],
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V15 Over/Under 1.5 labels-only selective",
        "219 - Décision expérience V15",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_policy.name}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {test_metrics.get('selected_rows')}",
        f"- OVER_1_5 rows : {test_metrics.get('over_rows')}",
        f"- UNDER_1_5 rows : {test_metrics.get('under_rows')}",
        f"- OVER_1_5 accuracy : {test_metrics.get('over_accuracy')}",
        f"- UNDER_1_5 accuracy : {test_metrics.get('under_accuracy')}",
        "",
        "Gates appliqués :",
        f"- Strong accuracy >= {STRONG_MIN_ACCURACY}",
        f"- Strong coverage >= {STRONG_MIN_COVERAGE}",
        f"- Strong selected rows >= {STRONG_MIN_SELECTED_ROWS}",
        f"- Mixed UNDER rows souhaités >= 100 avec accuracy >= {MIN_UNDER_ACCURACY_WARNING}",
        "- Pas de sauvegarde de modèle officiel.",
        "- Pas d'intégration API/frontend/scoring V1.",
        "",
        "Raisons bloquantes :",
        f"- {'Aucune.' if not blocking_reasons else '; '.join(blocking_reasons)}",
        "",
        "Points de vigilance :",
        f"- {'Aucun.' if not warnings_list else '; '.join(warnings_list)}",
        "",
        "Décision opérationnelle :",
    ]

    if "STRONG" in status:
        lines.extend(
            [
                "- V15 peut être conservée comme expérimentation forte sur Over/Under 1.5.",
                "- Une analyse de stabilité dédiée serait justifiée avant comparaison multi-marchés.",
            ]
        )
    elif "UNDER_WARNING" in status:
        lines.extend(
            [
                "- V15 est intéressante comme signal OVER_1_5 selective, mais pas comme vrai modèle équilibré Over/Under.",
                "- Le faible volume et la faible précision UNDER_1_5 doivent être explicitement documentés.",
                "- V15 peut rester utile dans V17 uniquement comme recommandation OVER_1_5 prudente, pas comme marché complet O/U 1.5.",
            ]
        )
    elif "REVIEW" in status:
        lines.extend(
            [
                "- V15 peut être conservée en REVIEW comme expérimentation utile.",
                "- La comparaison avec V16 reste nécessaire avant de construire le sélecteur multi-marchés V17.",
            ]
        )
    elif "EXPERIMENTAL" in status:
        lines.extend(
            [
                "- V15 doit rester documentée comme expérimentation limitée.",
                "- Ne pas la promouvoir comme marché fiable tant qu'une meilleure stratégie n'est pas trouvée.",
            ]
        )
    else:
        lines.extend(
            [
                "- V15 est rejetée comme candidat fiable dans son état actuel.",
                "- Conserver les fichiers comme preuve de test et passer à V16.",
            ]
        )

    lines.extend(
        [
            "- V15 ne remplace pas V13.1 mixed selective.",
            "- V15 ne remplace pas le scoring explicable V1.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V15 Over/Under 1.5 labels-only selective : réalisée.",
            "- Fichiers concernés : 214, 215, 216, 217, 218, 219.",
        ]
    )
    (evidence_dir / OUTPUT_DECISION).write_text("\n".join(lines), encoding="utf-8")


# Orchestre l'expérience V15 et génère les preuves 214 à 219.
def main() -> None:
    print("Chargement des CSV bruts et construction du dataset V15 Over/Under 1.5 labels-only...")
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)
    dataset, files = build_v15_dataset(project_root)

    validation = dataset[dataset["season"] == VALIDATION_SEASON].copy()
    test = dataset[dataset["season"].isin(TEST_SEASONS)].copy()
    if validation.empty or test.empty:
        raise RuntimeError("Split temporel V15 impossible : validation ou test vide.")

    print("Recherche de la meilleure stratégie selective V15 sur validation...")
    policies = build_policies()
    best_policy, validation_results = select_best_policy(validation, policies)
    validation_metrics = evaluate_policy(validation, best_policy, "validation")
    test_metrics = evaluate_policy(test, best_policy, "test")

    print("Application de la meilleure stratégie V15 sur test final...")
    final_predictions = apply_policy(test, best_policy)
    by_league_season = build_by_league_season(final_predictions)
    by_signal = build_by_signal(final_predictions)
    error_patterns = build_error_patterns(final_predictions)
    status, blocking_reasons, warnings_list = determine_status(test_metrics, by_league_season)

    combined_results = pd.concat([validation_results, pd.DataFrame([test_metrics])], ignore_index=True)
    combined_results.to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    by_signal.to_csv(evidence_dir / OUTPUT_BY_SIGNAL, index=False, encoding="utf-8-sig")
    error_patterns.to_csv(evidence_dir / OUTPUT_ERROR_PATTERNS, index=False, encoding="utf-8-sig")

    write_summary(
        evidence_dir=evidence_dir,
        dataset=dataset,
        files=files,
        best_policy=best_policy,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        by_league_season=by_league_season,
        status=status,
        blocking_reasons=blocking_reasons,
        warnings_list=warnings_list,
    )
    write_decision(
        evidence_dir=evidence_dir,
        best_policy=best_policy,
        test_metrics=test_metrics,
        status=status,
        blocking_reasons=blocking_reasons,
        warnings_list=warnings_list,
    )

    print("OK - Expérience V15 Over/Under 1.5 labels-only selective terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {best_policy.name}")
    print(f"Test accuracy: {test_metrics.get('accuracy')}")
    print(f"Test coverage: {test_metrics.get('coverage')}")
    print(f"Test abstention rate: {test_metrics.get('abstention_rate')}")
    print(f"Selected rows: {test_metrics.get('selected_rows')}")
    print(f"OVER_1_5 rows: {test_metrics.get('over_rows')}")
    print(f"UNDER_1_5 rows: {test_metrics.get('under_rows')}")
    print(f"OVER_1_5 accuracy: {test_metrics.get('over_accuracy')}")
    print(f"UNDER_1_5 accuracy: {test_metrics.get('under_accuracy')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"By signal CSV saved: {evidence_dir / OUTPUT_BY_SIGNAL}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# data/ml/raw/*.csv -> train_goals_v15_over_under_15_labels_selective.py -> reports/evidence/ml_training/214-219
# Ce script lit uniquement les CSV bruts et écrit uniquement des preuves d'expérimentation ML.
