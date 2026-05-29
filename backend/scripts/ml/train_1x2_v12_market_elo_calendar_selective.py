# Rôle du fichier : tester une V12 ML expérimentale combinant consensus de cotes, Elo pré-match et calendrier/fatigue, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from __future__ import annotations

import csv
import math
import sys
import warnings
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


TARGET_COLUMN = "target_result"
TARGET_CLASSES = ["HOME_WIN", "DRAW", "AWAY_WIN"]
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

OUTPUT_SUMMARY = "179_1x2_v12_market_elo_calendar_summary.txt"
OUTPUT_RESULTS = "180_1x2_v12_market_elo_calendar_results.csv"
OUTPUT_BEST_STRATEGY = "181_1x2_v12_market_elo_calendar_best_strategy.csv"
OUTPUT_BY_CLASS = "182_1x2_v12_market_elo_calendar_by_class.csv"
OUTPUT_BY_LEAGUE_SEASON = "183_1x2_v12_market_elo_calendar_by_league_season.csv"
OUTPUT_ERROR_PATTERNS = "184_1x2_v12_market_elo_calendar_error_patterns.csv"
OUTPUT_DECISION = "185_1x2_v12_market_elo_calendar_decision.txt"

RECENT_TEST_START_YEAR = 2022
VALIDATION_START_YEAR = 2021
RECENT_COVERAGE_START_YEAR = 2020
MIN_RECENT_TRIPLET_COVERAGE = 0.80
MIN_RECENT_TRIPLET_ROWS = 1000

STATIC_V9_SELECTED_ACCURACY = 0.7874
STATIC_V9_COVERAGE = 0.1492
STATIC_V9_SELECTED_ROWS = 795
STATIC_V9_CORRECT_ROWS = int(round(STATIC_V9_SELECTED_ACCURACY * STATIC_V9_SELECTED_ROWS))
STATIC_V11_SELECTED_ACCURACY = 0.7363
STATIC_V11_COVERAGE = 0.2326
STATIC_V11_SELECTED_ROWS = 1240
STATIC_V11_CORRECT_ROWS = int(round(STATIC_V11_SELECTED_ACCURACY * STATIC_V11_SELECTED_ROWS))

ACCEPT_MIN_ACCURACY = 0.76
ACCEPT_MIN_COVERAGE = 0.20
ACCEPT_MIN_SELECTED_ROWS = 1000
ACCEPT_MIN_NET_DELTA_VS_V9 = 1

REVIEW_MIN_ACCURACY = 0.73
REVIEW_MIN_COVERAGE = 0.18
REVIEW_MIN_SELECTED_ROWS = 850
REVIEW_MIN_NET_DELTA_VS_V9 = 0

MODEL_VARIANTS = [
    "v12_direct_market_consensus",
    "v12_logistic_market_elo_calendar_balanced",
    "v12_random_forest_market_elo_calendar_balanced",
]

MAX_PROBABILITY_THRESHOLDS = [0.55, 0.60, 0.62, 0.63, 0.64, 0.65, 0.66, 0.68, 0.70, 0.72]
MIN_MARGIN_THRESHOLDS = [0.00, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20]
MIN_AGREEMENT_THRESHOLDS = [0.00, 0.60, 0.80, 1.00]
DRAW_POLICIES = ["exclude_draw", "allow_draw_if_strong"]

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class CsvFileInfo:
    path: Path
    league_code: str
    season: str


@dataclass(frozen=True)
class OddsTriplet:
    market_type: str
    bookmaker_prefix: str
    home_col: str
    draw_col: str
    away_col: str

    @property
    def key(self) -> str:
        return f"{self.market_type}_{self.bookmaker_prefix}"


@dataclass(frozen=True)
class V12Policy:
    model_variant: str
    max_probability_threshold: float
    min_margin_threshold: float
    min_agreement_threshold: float
    draw_policy: str

    @property
    def name(self) -> str:
        return (
            f"{self.model_variant}"
            f"_p{self.max_probability_threshold:.2f}"
            f"_m{self.min_margin_threshold:.2f}"
            f"_agr{self.min_agreement_threshold:.2f}"
            f"_{self.draw_policy}"
        ).replace(".", "")


# Retrouve la racine RubyBets depuis l'emplacement du script.
def find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "data" / "ml" / "raw").exists():
            return parent
    raise FileNotFoundError("Impossible de trouver la racine projet : data/ml/raw est introuvable.")


# Retourne le dossier de preuves ML et le crée si nécessaire.
def get_evidence_dir(project_root: Path) -> Path:
    output_dir = project_root / "reports" / "evidence" / "ml_training"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# Arrondit une valeur numérique pour stabiliser les fichiers de preuve.
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


# Indique si une saison appartient au périmètre récent utilisé pour sélectionner les triplets de cotes.
def is_recent_for_triplet_selection(season: object) -> bool:
    return season_start_year(season) >= RECENT_COVERAGE_START_YEAR


# Liste les fichiers CSV bruts disponibles pour V12.
def list_raw_csv_files(project_root: Path) -> list[CsvFileInfo]:
    raw_dir = project_root / "data" / "ml" / "raw"
    return [
        CsvFileInfo(path=path, league_code=infer_league_code(path), season=infer_season_from_filename(path))
        for path in sorted(raw_dir.rglob("*.csv"))
    ]


# Lit un CSV Football-Data avec un mode tolérant pour les anciens fichiers mal formés.
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


# Prépare un fichier CSV brut en ajoutant ses métadonnées de source sans modifier le fichier original.
def prepare_raw_frame(file_info: CsvFileInfo) -> pd.DataFrame:
    frame = read_csv_safely(file_info.path)
    frame.columns = [str(column).strip().replace("\ufeff", "") for column in frame.columns]
    metadata = pd.DataFrame(
        {
            "__source_file": [str(file_info.path)] * len(frame),
            "__league_code": [file_info.league_code] * len(frame),
            "__season": [file_info.season] * len(frame),
        },
        index=frame.index,
    )
    return pd.concat([frame, metadata], axis=1)


# Détecte les triplets de cotes Home / Draw / Away présents dans les CSV.
def detect_odds_triplets(columns: Iterable[str]) -> list[OddsTriplet]:
    column_set = {str(column).strip().replace("\ufeff", "") for column in columns}
    triplets: dict[tuple[str, str], OddsTriplet] = {}

    for column in column_set:
        if column.endswith("CH"):
            prefix = column[:-2]
            draw_col = f"{prefix}CD"
            away_col = f"{prefix}CA"
            if draw_col in column_set and away_col in column_set:
                triplets[("closing", prefix)] = OddsTriplet("closing", prefix, column, draw_col, away_col)

        if column.endswith("H") and not column.endswith("CH"):
            prefix = column[:-1]
            draw_col = f"{prefix}D"
            away_col = f"{prefix}A"
            if draw_col in column_set and away_col in column_set:
                if "AH" not in prefix.upper() and ">" not in prefix and "<" not in prefix:
                    triplets[("opening_or_standard", prefix)] = OddsTriplet(
                        "opening_or_standard", prefix, column, draw_col, away_col
                    )

    return sorted(triplets.values(), key=lambda item: (item.market_type, item.bookmaker_prefix))


# Convertit une colonne de cotes en série numérique exploitable.
def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([math.nan] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


# Convertit FTR en cible ML 1X2 lisible.
def map_target_result(value: object) -> str | None:
    mapping = {"H": "HOME_WIN", "D": "DRAW", "A": "AWAY_WIN"}
    return mapping.get(str(value).strip())


# Charge tous les CSV bruts et construit le DataFrame source V12.
def load_raw_match_dataframe(project_root: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    files = list_raw_csv_files(project_root)
    if not files:
        raise FileNotFoundError("Aucun CSV brut trouvé dans data/ml/raw.")

    frames = [prepare_raw_frame(file_info) for file_info in files]
    dataframe = pd.concat(frames, ignore_index=True, sort=False)
    dataframe["__season_start_year"] = dataframe["__season"].map(season_start_year)
    dataframe[TARGET_COLUMN] = dataframe.get("FTR", pd.Series(index=dataframe.index, dtype=object)).map(map_target_result)

    metadata = {
        "csv_files": len(files),
        "raw_rows": len(dataframe),
        "leagues": ", ".join(sorted(dataframe["__league_code"].dropna().astype(str).unique().tolist())),
        "first_season": str(dataframe["__season"].dropna().astype(str).min()),
        "last_season": str(dataframe["__season"].dropna().astype(str).max()),
    }
    return dataframe, metadata


# Calcule la couverture récente d'un triplet de cotes afin de sélectionner les sources fiables.
def compute_triplet_recent_coverage(dataframe: pd.DataFrame, triplet: OddsTriplet) -> dict[str, object]:
    recent_mask = dataframe["__season"].map(is_recent_for_triplet_selection)
    recent_rows = int(recent_mask.sum())
    home = numeric_series(dataframe, triplet.home_col)
    draw = numeric_series(dataframe, triplet.draw_col)
    away = numeric_series(dataframe, triplet.away_col)
    complete = (home > 1.0) & (draw > 1.0) & (away > 1.0)
    recent_complete = complete & recent_mask
    recent_complete_rows = int(recent_complete.sum())

    return {
        "triplet_key": triplet.key,
        "market_type": triplet.market_type,
        "bookmaker_prefix": triplet.bookmaker_prefix,
        "home_col": triplet.home_col,
        "draw_col": triplet.draw_col,
        "away_col": triplet.away_col,
        "recent_rows": recent_rows,
        "recent_complete_rows": recent_complete_rows,
        "recent_coverage_rate": safe_rate(recent_complete_rows, recent_rows),
    }


# Sélectionne les triplets de cotes suffisamment complets pour la V12.
def select_usable_triplets(dataframe: pd.DataFrame, triplets: list[OddsTriplet]) -> tuple[list[OddsTriplet], pd.DataFrame]:
    coverage_rows = [compute_triplet_recent_coverage(dataframe, triplet) for triplet in triplets]
    coverage_dataframe = pd.DataFrame(coverage_rows).sort_values(
        by=["recent_coverage_rate", "recent_complete_rows"], ascending=[False, False]
    )

    usable_keys = set(
        coverage_dataframe[
            (coverage_dataframe["recent_coverage_rate"] >= MIN_RECENT_TRIPLET_COVERAGE)
            & (coverage_dataframe["recent_complete_rows"] >= MIN_RECENT_TRIPLET_ROWS)
        ]["triplet_key"].tolist()
    )
    usable_triplets = [triplet for triplet in triplets if triplet.key in usable_keys]

    if not usable_triplets:
        usable_triplets = triplets[:]

    return usable_triplets, coverage_dataframe


# Convertit les cotes d'un triplet en probabilités implicites normalisées.
def triplet_probabilities(dataframe: pd.DataFrame, triplet: OddsTriplet) -> pd.DataFrame:
    home_odds = numeric_series(dataframe, triplet.home_col)
    draw_odds = numeric_series(dataframe, triplet.draw_col)
    away_odds = numeric_series(dataframe, triplet.away_col)
    valid = (home_odds > 1.0) & (draw_odds > 1.0) & (away_odds > 1.0)

    inv_home = 1.0 / home_odds
    inv_draw = 1.0 / draw_odds
    inv_away = 1.0 / away_odds
    overround = inv_home + inv_draw + inv_away

    key = triplet.key
    return pd.DataFrame(
        {
            f"{key}_prob_HOME_WIN": (inv_home / overround).where(valid),
            f"{key}_prob_DRAW": (inv_draw / overround).where(valid),
            f"{key}_prob_AWAY_WIN": (inv_away / overround).where(valid),
        },
        index=dataframe.index,
    )


# Construit toutes les features market + Elo + calendrier et closing/opening movement en mémoire.
def build_market_consensus_features(dataframe: pd.DataFrame, triplets: list[OddsTriplet]) -> pd.DataFrame:
    probability_blocks = [triplet_probabilities(dataframe, triplet) for triplet in triplets]
    probabilities = pd.concat(probability_blocks, axis=1) if probability_blocks else pd.DataFrame(index=dataframe.index)

    home_columns = [column for column in probabilities.columns if column.endswith("prob_HOME_WIN")]
    draw_columns = [column for column in probabilities.columns if column.endswith("prob_DRAW")]
    away_columns = [column for column in probabilities.columns if column.endswith("prob_AWAY_WIN")]

    features = pd.DataFrame(index=dataframe.index)
    for class_name, columns in [
        ("home", home_columns),
        ("draw", draw_columns),
        ("away", away_columns),
    ]:
        features[f"market_{class_name}_prob_avg"] = probabilities[columns].mean(axis=1, skipna=True)
        features[f"market_{class_name}_prob_std"] = probabilities[columns].std(axis=1, skipna=True).fillna(0.0)
        features[f"market_{class_name}_prob_min"] = probabilities[columns].min(axis=1, skipna=True)
        features[f"market_{class_name}_prob_max"] = probabilities[columns].max(axis=1, skipna=True)
        features[f"market_{class_name}_dispersion"] = (
            features[f"market_{class_name}_prob_max"] - features[f"market_{class_name}_prob_min"]
        ).fillna(0.0)

    features["market_available_triplets"] = pd.concat(
        [
            probabilities[home_columns].notna().sum(axis=1),
            probabilities[draw_columns].notna().sum(axis=1),
            probabilities[away_columns].notna().sum(axis=1),
        ],
        axis=1,
    ).min(axis=1)

    for market_type in ["closing", "opening_or_standard"]:
        for class_label, suffix in [
            ("home", "HOME_WIN"),
            ("draw", "DRAW"),
            ("away", "AWAY_WIN"),
        ]:
            columns = [
                column
                for column in probabilities.columns
                if column.startswith(f"{market_type}_") and column.endswith(f"prob_{suffix}")
            ]
            features[f"market_{market_type}_{class_label}_prob_avg"] = (
                probabilities[columns].mean(axis=1, skipna=True) if columns else 0.0
            )

    common_prefixes = sorted(
        {
            triplet.bookmaker_prefix
            for triplet in triplets
            if triplet.market_type == "closing"
            and any(
                other.market_type == "opening_or_standard" and other.bookmaker_prefix == triplet.bookmaker_prefix
                for other in triplets
            )
        }
    )
    for prefix in common_prefixes:
        for class_name, class_label in [
            ("home", "HOME_WIN"),
            ("draw", "DRAW"),
            ("away", "AWAY_WIN"),
        ]:
            closing_column = f"closing_{prefix}_prob_{class_label}"
            opening_column = f"opening_or_standard_{prefix}_prob_{class_label}"
            if closing_column in probabilities.columns and opening_column in probabilities.columns:
                features[f"market_move_{prefix}_{class_name}"] = (
                    probabilities[closing_column] - probabilities[opening_column]
                ).fillna(0.0)

    for class_name in ["home", "draw", "away"]:
        move_columns = [
            column
            for column in features.columns
            if column.startswith("market_move_") and column.endswith(f"_{class_name}")
        ]
        features[f"market_move_{class_name}_avg"] = (
            features[move_columns].mean(axis=1, skipna=True).fillna(0.0) if move_columns else 0.0
        )
        features[f"market_move_{class_name}_abs_avg"] = features[f"market_move_{class_name}_avg"].abs()

    consensus_probabilities = features[
        ["market_home_prob_avg", "market_draw_prob_avg", "market_away_prob_avg"]
    ].fillna(0.0)
    probability_array = consensus_probabilities.to_numpy()
    predicted_indices = np.argmax(probability_array, axis=1)
    sorted_probabilities = np.sort(probability_array, axis=1)

    features["market_consensus_prediction"] = np.array(TARGET_CLASSES)[predicted_indices]
    features["market_favorite_prob"] = sorted_probabilities[:, -1]
    features["market_second_prob"] = sorted_probabilities[:, -2]
    features["market_margin_top1_top2"] = features["market_favorite_prob"] - features["market_second_prob"]
    features["market_home_away_gap"] = features["market_home_prob_avg"] - features["market_away_prob_avg"]
    features["market_abs_home_away_gap"] = features["market_home_away_gap"].abs()
    features["market_draw_pressure"] = features["market_draw_prob_avg"] - features[["market_home_prob_avg", "market_away_prob_avg"]].max(axis=1)
    features["market_is_clear_favorite"] = (features["market_margin_top1_top2"] >= 0.15).astype(int)
    features["market_is_balanced_match"] = (features["market_margin_top1_top2"] <= 0.08).astype(int)

    entropy_base = consensus_probabilities.replace(0.0, np.nan)
    features["market_entropy"] = -(entropy_base * np.log(entropy_base)).sum(axis=1).fillna(0.0)

    individual_predictions: list[pd.Series] = []
    for triplet in triplets:
        key = triplet.key
        required_columns = [
            f"{key}_prob_HOME_WIN",
            f"{key}_prob_DRAW",
            f"{key}_prob_AWAY_WIN",
        ]
        if not all(column in probabilities.columns for column in required_columns):
            continue
        matrix = probabilities[required_columns].to_numpy()
        valid = ~np.isnan(matrix).any(axis=1)
        series = pd.Series(pd.NA, index=dataframe.index, dtype="object")
        series.loc[valid] = np.array(TARGET_CLASSES)[np.argmax(matrix[valid], axis=1)]
        individual_predictions.append(series)

    if individual_predictions:
        individual_prediction_frame = pd.concat(individual_predictions, axis=1)
        features["market_bookmaker_agreement_score"] = (
            individual_prediction_frame.eq(features["market_consensus_prediction"], axis=0).sum(axis=1)
            / features["market_available_triplets"].replace(0, np.nan)
        ).fillna(0.0)
    else:
        features["market_bookmaker_agreement_score"] = 0.0

    return features



# Convertit les formats de date Football-Data en datetime robuste pour calculer Elo et repos.
def parse_match_dates(date_series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(date_series, errors="coerce", dayfirst=True)
    fallback = pd.to_datetime(date_series, errors="coerce", dayfirst=False)
    return parsed.fillna(fallback)


# Convertit un résultat cible en score numérique domicile pour la mise à jour Elo.
def result_to_home_score(result: object) -> float | None:
    if result == "HOME_WIN":
        return 1.0
    if result == "DRAW":
        return 0.5
    if result == "AWAY_WIN":
        return 0.0
    return None


# Calcule l'espérance Elo de l'équipe à domicile avec avantage terrain simple.
def elo_expected_home(home_elo: float, away_elo: float, home_advantage: float = 60.0) -> float:
    return 1.0 / (1.0 + 10.0 ** ((away_elo - (home_elo + home_advantage)) / 400.0))


# Construit les features Elo pré-match et calendrier/fatigue en lecture seule.
def build_elo_calendar_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    working = dataframe.copy()
    working["__match_date"] = parse_match_dates(working.get("Date", pd.Series(index=working.index, dtype=object)))
    working["__original_index"] = working.index
    working = working.sort_values(["__match_date", "__season", "__league_code", "__original_index"], na_position="last")

    features = pd.DataFrame(index=dataframe.index)
    elo_by_team: dict[str, float] = {}
    last_match_date_by_team: dict[str, pd.Timestamp] = {}
    recent_dates_by_team: dict[str, deque[pd.Timestamp]] = {}

    default_elo = 1500.0
    k_factor = 20.0
    home_advantage = 60.0

    for _, row in working.iterrows():
        idx = row["__original_index"]
        league = str(row.get("__league_code", "UNKNOWN"))
        home_team = str(row.get("HomeTeam", "UNKNOWN_HOME"))
        away_team = str(row.get("AwayTeam", "UNKNOWN_AWAY"))
        home_key = f"{league}::{home_team}"
        away_key = f"{league}::{away_team}"
        match_date = row.get("__match_date")

        home_elo = float(elo_by_team.get(home_key, default_elo))
        away_elo = float(elo_by_team.get(away_key, default_elo))
        elo_diff = home_elo - away_elo
        elo_diff_adjusted = elo_diff + home_advantage

        features.loc[idx, "elo_home_before"] = home_elo
        features.loc[idx, "elo_away_before"] = away_elo
        features.loc[idx, "elo_diff"] = elo_diff
        features.loc[idx, "elo_diff_home_adjusted"] = elo_diff_adjusted
        features.loc[idx, "elo_abs_diff"] = abs(elo_diff_adjusted)
        features.loc[idx, "elo_home_expected"] = elo_expected_home(home_elo, away_elo, home_advantage)

        home_last_date = last_match_date_by_team.get(home_key)
        away_last_date = last_match_date_by_team.get(away_key)
        if pd.notna(match_date) and home_last_date is not None and pd.notna(home_last_date):
            home_rest_days = max(0.0, float((match_date - home_last_date).days))
        else:
            home_rest_days = 14.0
        if pd.notna(match_date) and away_last_date is not None and pd.notna(away_last_date):
            away_rest_days = max(0.0, float((match_date - away_last_date).days))
        else:
            away_rest_days = 14.0

        features.loc[idx, "calendar_home_rest_days"] = min(home_rest_days, 30.0)
        features.loc[idx, "calendar_away_rest_days"] = min(away_rest_days, 30.0)
        features.loc[idx, "calendar_rest_days_diff"] = min(home_rest_days, 30.0) - min(away_rest_days, 30.0)

        for team_key, prefix in [(home_key, "home"), (away_key, "away")]:
            dates_queue = recent_dates_by_team.setdefault(team_key, deque())
            if pd.notna(match_date):
                while dates_queue and (match_date - dates_queue[0]).days > 14:
                    dates_queue.popleft()
                last_7 = sum(1 for past_date in dates_queue if (match_date - past_date).days <= 7)
                last_14 = len(dates_queue)
            else:
                last_7 = 0
                last_14 = 0
            features.loc[idx, f"calendar_{prefix}_matches_last_7_days"] = float(last_7)
            features.loc[idx, f"calendar_{prefix}_matches_last_14_days"] = float(last_14)

        features.loc[idx, "calendar_congestion_diff_7"] = (
            features.loc[idx, "calendar_home_matches_last_7_days"]
            - features.loc[idx, "calendar_away_matches_last_7_days"]
        )
        features.loc[idx, "calendar_congestion_diff_14"] = (
            features.loc[idx, "calendar_home_matches_last_14_days"]
            - features.loc[idx, "calendar_away_matches_last_14_days"]
        )

        target = row.get(TARGET_COLUMN)
        home_score = result_to_home_score(target)
        if home_score is not None:
            expected_home = elo_expected_home(home_elo, away_elo, home_advantage)
            goal_diff = 1.0
            try:
                goal_diff = abs(float(row.get("FTHG", 0)) - float(row.get("FTAG", 0)))
                goal_diff = max(1.0, goal_diff)
            except Exception:  # noqa: BLE001 - fallback si anciens fichiers incomplets
                goal_diff = 1.0
            margin_multiplier = math.log(goal_diff + 1.0)
            update = k_factor * margin_multiplier * (home_score - expected_home)
            elo_by_team[home_key] = home_elo + update
            elo_by_team[away_key] = away_elo - update

        if pd.notna(match_date):
            last_match_date_by_team[home_key] = match_date
            last_match_date_by_team[away_key] = match_date
            recent_dates_by_team.setdefault(home_key, deque()).append(match_date)
            recent_dates_by_team.setdefault(away_key, deque()).append(match_date)

    features["calendar_home_low_rest"] = (features["calendar_home_rest_days"] <= 3).astype(int)
    features["calendar_away_low_rest"] = (features["calendar_away_rest_days"] <= 3).astype(int)
    features["calendar_abs_rest_days_diff"] = features["calendar_rest_days_diff"].abs()
    return features.fillna(0.0)


# Construit le dataset V12 final sans écrire en base de données.
def build_v12_dataset(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    dataframe, metadata = load_raw_match_dataframe(project_root)
    triplets = detect_odds_triplets(dataframe.columns)
    usable_triplets, triplet_coverage = select_usable_triplets(dataframe, triplets)
    market_features = build_market_consensus_features(dataframe, usable_triplets)
    elo_calendar_features = build_elo_calendar_features(dataframe)
    features = pd.concat([market_features, elo_calendar_features], axis=1)

    base_columns = [
        "__league_code",
        "__season",
        "__season_start_year",
        "__source_file",
        "Date",
        "HomeTeam",
        "AwayTeam",
        TARGET_COLUMN,
    ]
    available_base_columns = [column for column in base_columns if column in dataframe.columns]
    dataset = pd.concat([dataframe[available_base_columns], features], axis=1)
    dataset = dataset.dropna(
        subset=[TARGET_COLUMN, "market_home_prob_avg", "market_draw_prob_avg", "market_away_prob_avg"]
    ).copy()
    dataset = dataset[dataset[TARGET_COLUMN].isin(TARGET_CLASSES)].copy()

    metadata.update(
        {
            "detected_triplets": len(triplets),
            "usable_triplets": len(usable_triplets),
            "usable_triplet_keys": ", ".join([triplet.key for triplet in usable_triplets[:20]]),
            "dataset_rows": len(dataset),
            "recent_test_rows": int((dataset["__season_start_year"] >= RECENT_TEST_START_YEAR).sum()),
        }
    )
    return dataset, triplet_coverage, metadata


# Crée les splits temporels train / validation / test.
def prepare_temporal_splits(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    train = dataset[dataset["__season_start_year"] < VALIDATION_START_YEAR].copy()
    validation = dataset[dataset["__season_start_year"] == VALIDATION_START_YEAR].copy()
    test = dataset[dataset["__season_start_year"] >= RECENT_TEST_START_YEAR].copy()

    if train.empty or validation.empty or test.empty:
        sorted_dataset = dataset.sort_values(["__season_start_year", "__league_code"]).reset_index(drop=True)
        first_split = int(len(sorted_dataset) * 0.70)
        second_split = int(len(sorted_dataset) * 0.85)
        train = sorted_dataset.iloc[:first_split].copy()
        validation = sorted_dataset.iloc[first_split:second_split].copy()
        test = sorted_dataset.iloc[second_split:].copy()
        split_mode = "fallback_ratio_split"
    else:
        split_mode = "temporal_2021_validation_2022_plus_test"

    metadata = {
        "split_mode": split_mode,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_rows": len(test),
        "train_seasons": ", ".join(sorted(train["__season"].dropna().astype(str).unique().tolist())),
        "validation_seasons": ", ".join(sorted(validation["__season"].dropna().astype(str).unique().tolist())),
        "test_seasons": ", ".join(sorted(test["__season"].dropna().astype(str).unique().tolist())),
    }
    return train, validation, test, metadata


# Retourne la liste des features numériques V12 utilisables par les modèles.
def get_v12_numeric_feature_columns(dataset: pd.DataFrame) -> list[str]:
    prefixes = (
        "market_home_",
        "market_draw_",
        "market_away_",
        "market_closing_",
        "market_opening_or_standard_",
        "market_move_",
        "market_favorite_",
        "market_second_",
        "market_margin_",
        "market_entropy",
        "market_available_",
        "market_bookmaker_",
        "market_abs_",
        "market_is_",
        "elo_",
        "calendar_",
    )
    columns = [column for column in dataset.columns if column.startswith(prefixes)]
    excluded = {"market_consensus_prediction"}
    return [column for column in columns if column not in excluded]


# Construit une matrice de features avec encodage minimal de la ligue.
def build_feature_matrix(
    dataframe: pd.DataFrame,
    numeric_columns: list[str],
    reference_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    numeric_matrix = dataframe[numeric_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    categorical_matrix = pd.get_dummies(dataframe[["__league_code"]].fillna("UNKNOWN").astype(str), prefix=["league"])
    matrix = pd.concat([numeric_matrix, categorical_matrix], axis=1)

    if reference_columns is None:
        feature_columns = matrix.columns.tolist()
    else:
        feature_columns = reference_columns
        matrix = matrix.reindex(columns=feature_columns, fill_value=0.0)

    return matrix, feature_columns


# Construit un modèle V12 candidat.
def build_model(model_variant: str):
    if model_variant == "v12_logistic_market_elo_calendar_balanced":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
        )
    if model_variant == "v12_random_forest_market_elo_calendar_balanced":
        return RandomForestClassifier(
            n_estimators=120,
            max_depth=6,
            min_samples_leaf=40,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
    raise RuntimeError(f"Modèle V12 inconnu : {model_variant}")


# Ajoute les probabilités de prédiction d'un modèle V12 au DataFrame cible.
def add_model_predictions(
    dataframe: pd.DataFrame,
    model_variant: str,
    model,
    feature_columns: list[str],
    numeric_columns: list[str],
) -> pd.DataFrame:
    output = dataframe.copy()
    x_predict, _ = build_feature_matrix(output, numeric_columns, reference_columns=feature_columns)
    probabilities = model.predict_proba(x_predict)
    class_labels = list(model.classes_)

    for class_name in TARGET_CLASSES:
        if class_name in class_labels:
            output[f"{model_variant}_prob_{class_name}"] = probabilities[:, class_labels.index(class_name)]
        else:
            output[f"{model_variant}_prob_{class_name}"] = 0.0

    probability_columns = [f"{model_variant}_prob_{class_name}" for class_name in TARGET_CLASSES]
    probability_array = output[probability_columns].to_numpy()
    output[f"{model_variant}_prediction"] = np.array(TARGET_CLASSES)[np.argmax(probability_array, axis=1)]
    sorted_probabilities = np.sort(probability_array, axis=1)
    output[f"{model_variant}_max_probability"] = sorted_probabilities[:, -1]
    output[f"{model_variant}_second_probability"] = sorted_probabilities[:, -2]
    output[f"{model_variant}_margin"] = (
        output[f"{model_variant}_max_probability"] - output[f"{model_variant}_second_probability"]
    )
    return output


# Ajoute les probabilités directes issues du consensus de marché.
def add_direct_market_predictions(dataframe: pd.DataFrame) -> pd.DataFrame:
    output = dataframe.copy()
    mapping = {
        "HOME_WIN": "market_home_prob_avg",
        "DRAW": "market_draw_prob_avg",
        "AWAY_WIN": "market_away_prob_avg",
    }
    for class_name, source_column in mapping.items():
        output[f"v12_direct_market_consensus_prob_{class_name}"] = pd.to_numeric(
            output[source_column], errors="coerce"
        ).fillna(0.0)

    probability_columns = [f"v12_direct_market_consensus_prob_{class_name}" for class_name in TARGET_CLASSES]
    probability_array = output[probability_columns].to_numpy()
    output["v12_direct_market_consensus_prediction"] = np.array(TARGET_CLASSES)[np.argmax(probability_array, axis=1)]
    sorted_probabilities = np.sort(probability_array, axis=1)
    output["v12_direct_market_consensus_max_probability"] = sorted_probabilities[:, -1]
    output["v12_direct_market_consensus_second_probability"] = sorted_probabilities[:, -2]
    output["v12_direct_market_consensus_margin"] = (
        output["v12_direct_market_consensus_max_probability"]
        - output["v12_direct_market_consensus_second_probability"]
    )
    return output


# Entraîne les modèles V12 et enrichit validation/test avec les probabilités de tous les candidats.
def build_candidate_predictions(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    numeric_columns = get_v12_numeric_feature_columns(train)
    validation_output = add_direct_market_predictions(validation)
    test_output = add_direct_market_predictions(test)
    metadata = {"feature_count": len(numeric_columns), "feature_columns": ", ".join(numeric_columns[:40])}

    x_train, feature_columns = build_feature_matrix(train, numeric_columns)
    y_train = train[TARGET_COLUMN].astype(str)

    for model_variant in [variant for variant in MODEL_VARIANTS if variant != "v12_direct_market_consensus"]:
        print(f"Entraînement du modèle V12 : {model_variant}", flush=True)
        model = build_model(model_variant)
        model.fit(x_train, y_train)
        validation_output = add_model_predictions(validation_output, model_variant, model, feature_columns, numeric_columns)
        test_output = add_model_predictions(test_output, model_variant, model, feature_columns, numeric_columns)

    return validation_output, test_output, metadata


# Génère les politiques sélectives V12 à évaluer.
def build_policies() -> list[V12Policy]:
    return [
        V12Policy(model_variant, probability_threshold, margin_threshold, agreement_threshold, draw_policy)
        for model_variant in MODEL_VARIANTS
        for probability_threshold in MAX_PROBABILITY_THRESHOLDS
        for margin_threshold in MIN_MARGIN_THRESHOLDS
        for agreement_threshold in MIN_AGREEMENT_THRESHOLDS
        for draw_policy in DRAW_POLICIES
    ]


# Applique une politique V12 et produit les colonnes de sélection/abstention.
def apply_policy(dataframe: pd.DataFrame, policy: V12Policy) -> pd.DataFrame:
    output = dataframe.copy()
    prediction_column = f"{policy.model_variant}_prediction"
    max_probability_column = f"{policy.model_variant}_max_probability"
    margin_column = f"{policy.model_variant}_margin"

    if prediction_column not in output.columns:
        raise RuntimeError(f"Colonne de prédiction absente : {prediction_column}")

    output[max_probability_column] = pd.to_numeric(output[max_probability_column], errors="coerce").fillna(0.0)
    output[margin_column] = pd.to_numeric(output[margin_column], errors="coerce").fillna(0.0)
    output["market_bookmaker_agreement_score"] = pd.to_numeric(
        output["market_bookmaker_agreement_score"], errors="coerce"
    ).fillna(0.0)

    base_mask = (
        (output[max_probability_column] >= policy.max_probability_threshold)
        & (output[margin_column] >= policy.min_margin_threshold)
        & (output["market_bookmaker_agreement_score"] >= policy.min_agreement_threshold)
    )

    if policy.draw_policy == "exclude_draw":
        draw_mask = output[prediction_column] != "DRAW"
    elif policy.draw_policy == "allow_draw_if_strong":
        draw_probability_column = f"{policy.model_variant}_prob_DRAW"
        output[draw_probability_column] = pd.to_numeric(output[draw_probability_column], errors="coerce").fillna(0.0)
        draw_mask = (output[prediction_column] != "DRAW") | (
            (output[prediction_column] == "DRAW")
            & (output[draw_probability_column] >= 0.36)
            & (output[max_probability_column] >= max(policy.max_probability_threshold, 0.55))
        )
    elif policy.draw_policy == "allow_all":
        draw_mask = pd.Series([True] * len(output), index=output.index)
    else:
        raise RuntimeError(f"Politique DRAW inconnue : {policy.draw_policy}")

    recommend_mask = base_mask & draw_mask
    output["v12_policy"] = policy.name
    output["v12_model_variant"] = policy.model_variant
    output["v12_recommendation_status"] = np.where(recommend_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v12_prediction"] = np.where(recommend_mask, output[prediction_column], ABSTAIN_STATUS)
    output["v12_confidence_probability"] = output[max_probability_column]
    output["v12_margin"] = output[margin_column]
    output["v12_is_correct"] = output[TARGET_COLUMN] == output["v12_prediction"]

    output["v12_abstention_reason"] = "accepted"
    output.loc[~base_mask, "v12_abstention_reason"] = "low_probability_margin_or_agreement"
    output.loc[base_mask & ~draw_mask, "v12_abstention_reason"] = "draw_not_allowed_or_not_strong_enough"
    return output


# Calcule les métriques d'une politique V12 sur un périmètre donné.
def compute_policy_metrics(policy_dataframe: pd.DataFrame, policy: V12Policy, scope: str) -> dict[str, object]:
    selected = policy_dataframe[policy_dataframe["v12_recommendation_status"] == RECOMMEND_STATUS].copy()
    total_rows = len(policy_dataframe)
    selected_rows = len(selected)
    correct_rows = int(selected["v12_is_correct"].sum()) if selected_rows else 0
    selected_accuracy = safe_rate(correct_rows, selected_rows)
    coverage = safe_rate(selected_rows, total_rows)
    predicted_draw_rows = int((selected["v12_prediction"] == "DRAW").sum()) if selected_rows else 0

    return {
        "scope": scope,
        "strategy": policy.name,
        "model_variant": policy.model_variant,
        "max_probability_threshold": policy.max_probability_threshold,
        "min_margin_threshold": policy.min_margin_threshold,
        "min_agreement_threshold": policy.min_agreement_threshold,
        "draw_policy": policy.draw_policy,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(coverage),
        "abstention_rate": rounded(1.0 - coverage),
        "selected_accuracy": rounded(selected_accuracy),
        "selected_correct_rows": correct_rows,
        "predicted_draw_rows": predicted_draw_rows,
        "actual_draw_rows_selected": int((selected[TARGET_COLUMN] == "DRAW").sum()) if selected_rows else 0,
        "net_correct_delta_vs_static_v9": correct_rows - STATIC_V9_CORRECT_ROWS if scope == "test" else 0,
    }



# Calcule les métriques d'une politique V12 sans copier tout le DataFrame, pour garder le script rapide.
def compute_policy_metrics_fast(dataframe: pd.DataFrame, policy: V12Policy, scope: str) -> dict[str, object]:
    prediction_column = f"{policy.model_variant}_prediction"
    max_probability_column = f"{policy.model_variant}_max_probability"
    margin_column = f"{policy.model_variant}_margin"
    draw_probability_column = f"{policy.model_variant}_prob_DRAW"

    predictions = dataframe[prediction_column].astype(str).to_numpy()
    targets = dataframe[TARGET_COLUMN].astype(str).to_numpy()
    max_probability = pd.to_numeric(dataframe[max_probability_column], errors="coerce").fillna(0.0).to_numpy()
    margin = pd.to_numeric(dataframe[margin_column], errors="coerce").fillna(0.0).to_numpy()
    agreement = pd.to_numeric(dataframe["market_bookmaker_agreement_score"], errors="coerce").fillna(0.0).to_numpy()

    base_mask = (
        (max_probability >= policy.max_probability_threshold)
        & (margin >= policy.min_margin_threshold)
        & (agreement >= policy.min_agreement_threshold)
    )

    if policy.draw_policy == "exclude_draw":
        draw_mask = predictions != "DRAW"
    elif policy.draw_policy == "allow_draw_if_strong":
        draw_probability = pd.to_numeric(dataframe[draw_probability_column], errors="coerce").fillna(0.0).to_numpy()
        draw_mask = (predictions != "DRAW") | (
            (predictions == "DRAW")
            & (draw_probability >= 0.36)
            & (max_probability >= max(policy.max_probability_threshold, 0.55))
        )
    elif policy.draw_policy == "allow_all":
        draw_mask = np.ones(len(dataframe), dtype=bool)
    else:
        raise RuntimeError(f"Politique DRAW inconnue : {policy.draw_policy}")

    selected_mask = base_mask & draw_mask
    total_rows = len(dataframe)
    selected_rows = int(selected_mask.sum())
    selected_correct = int((predictions[selected_mask] == targets[selected_mask]).sum()) if selected_rows else 0

    return {
        "scope": scope,
        "strategy": policy.name,
        "model_variant": policy.model_variant,
        "max_probability_threshold": policy.max_probability_threshold,
        "min_margin_threshold": policy.min_margin_threshold,
        "min_agreement_threshold": policy.min_agreement_threshold,
        "draw_policy": policy.draw_policy,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "selected_accuracy": rounded(safe_rate(selected_correct, selected_rows)),
        "selected_correct_rows": selected_correct,
        "predicted_draw_rows": int((predictions[selected_mask] == "DRAW").sum()) if selected_rows else 0,
        "actual_draw_rows_selected": int((targets[selected_mask] == "DRAW").sum()) if selected_rows else 0,
        "net_correct_delta_vs_static_v9": selected_correct - STATIC_V9_CORRECT_ROWS if scope == "test" else 0,
        "net_correct_delta_vs_static_v11": selected_correct - STATIC_V11_CORRECT_ROWS if scope == "test" else 0,
    }


# Évalue toutes les politiques V12 sur validation et test final.
def evaluate_policies(validation: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []

    policies = build_policies()
    for policy in policies:
        rows.append(compute_policy_metrics_fast(validation, policy, "validation"))

    results = pd.DataFrame(rows)
    validation_candidates = results[
        (results["scope"] == "validation")
        & (results["selected_rows"] >= 100)
        & (results["coverage"] >= 0.05)
    ].copy()

    if validation_candidates.empty:
        raise RuntimeError("Aucune politique V12 exploitable sur validation.")

    validation_candidates["validation_gate_accuracy"] = validation_candidates["selected_accuracy"] >= 0.72
    validation_candidates["validation_gate_coverage"] = validation_candidates["coverage"] >= 0.15
    validation_candidates["selection_score"] = (
        validation_candidates["selected_accuracy"] * 0.68
        + validation_candidates["coverage"] * 0.25
        + (validation_candidates["selected_rows"] / max(1, len(validation))) * 0.07
    )
    validation_candidates = validation_candidates.sort_values(
        by=["validation_gate_accuracy", "validation_gate_coverage", "selection_score", "selected_accuracy", "coverage"],
        ascending=[False, False, False, False, False],
    )

    best_strategy_name = str(validation_candidates.iloc[0]["strategy"])
    best_policy = next(policy for policy in policies if policy.name == best_strategy_name)
    rows.append(compute_policy_metrics_fast(test, best_policy, "test"))
    test_policy_dataframe = apply_policy(test, best_policy)

    return pd.DataFrame(rows), test_policy_dataframe


# Calcule la stabilité de la meilleure politique par classe prédite.
def build_by_class(best_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = best_predictions[best_predictions["v12_recommendation_status"] == RECOMMEND_STATUS].copy()
    rows: list[dict[str, object]] = []
    for predicted_class in ["HOME_WIN", "DRAW", "AWAY_WIN"]:
        subset = selected[selected["v12_prediction"] == predicted_class]
        rows.append(
            {
                "predicted_class": predicted_class,
                "selected_rows": len(subset),
                "selected_accuracy": rounded(safe_rate(int(subset["v12_is_correct"].sum()), len(subset))),
                "actual_draw_rows": int((subset[TARGET_COLUMN] == "DRAW").sum()) if len(subset) else 0,
                "class_status": "NO_RECOMMENDATION_FOR_CLASS" if len(subset) == 0 else "STABLE_REVIEW",
            }
        )
    return pd.DataFrame(rows)


# Calcule la stabilité de la meilleure politique par ligue et saison.
def build_by_league_season(best_predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = best_predictions.groupby(["__league_code", "__season"], dropna=False)
    for (league_code, season), group in grouped:
        selected = group[group["v12_recommendation_status"] == RECOMMEND_STATUS]
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "total_rows": len(group),
                "selected_rows": len(selected),
                "coverage": rounded(safe_rate(len(selected), len(group))),
                "selected_accuracy": rounded(safe_rate(int(selected["v12_is_correct"].sum()), len(selected))),
                "predicted_draw_rows": int((selected["v12_prediction"] == "DRAW").sum()) if len(selected) else 0,
                "actual_draw_rows": int((selected[TARGET_COLUMN] == "DRAW").sum()) if len(selected) else 0,
            }
        )
    return pd.DataFrame(rows).sort_values(["selected_rows", "selected_accuracy"], ascending=[False, True])


# Génère les principaux motifs d'erreur restants sur les recommandations sélectionnées.
def build_error_patterns(best_predictions: pd.DataFrame) -> pd.DataFrame:
    selected_errors = best_predictions[
        (best_predictions["v12_recommendation_status"] == RECOMMEND_STATUS)
        & (~best_predictions["v12_is_correct"])
    ].copy()

    if selected_errors.empty:
        return pd.DataFrame(
            columns=["league_code", "season", "error_label", "rows"]
        )

    selected_errors["error_label"] = (
        selected_errors["v12_prediction"].astype(str)
        + " predicted instead of "
        + selected_errors[TARGET_COLUMN].astype(str)
    )
    return (
        selected_errors.groupby(["__league_code", "__season", "error_label"], dropna=False)
        .size()
        .reset_index(name="rows")
        .rename(columns={"__league_code": "league_code", "__season": "season"})
        .sort_values("rows", ascending=False)
    )


# Détermine la décision V12 selon les gates fixés avant l'expérience.
def decide_v12(test_metrics: dict[str, object]) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings_list: list[str] = []

    selected_accuracy = float(test_metrics.get("selected_accuracy", 0.0))
    coverage = float(test_metrics.get("coverage", 0.0))
    selected_rows = int(test_metrics.get("selected_rows", 0))
    net_delta = int(test_metrics.get("net_correct_delta_vs_static_v9", 0))
    net_delta_v11 = int(test_metrics.get("net_correct_delta_vs_static_v11", 0))
    predicted_draw_rows = int(test_metrics.get("predicted_draw_rows", 0))

    if selected_accuracy < ACCEPT_MIN_ACCURACY:
        blockers.append(f"Accuracy sélectionnée inférieure au gate d'acceptation : {selected_accuracy} < {ACCEPT_MIN_ACCURACY}.")
    if coverage < ACCEPT_MIN_COVERAGE:
        blockers.append(f"Coverage inférieur au gate d'acceptation : {coverage} < {ACCEPT_MIN_COVERAGE}.")
    if selected_rows <= ACCEPT_MIN_SELECTED_ROWS:
        blockers.append(f"Nombre de matchs sélectionnés insuffisant : {selected_rows} <= {ACCEPT_MIN_SELECTED_ROWS}.")
    if net_delta < ACCEPT_MIN_NET_DELTA_VS_V9:
        blockers.append(f"Delta correct vs V9 insuffisant : {net_delta} < {ACCEPT_MIN_NET_DELTA_VS_V9}.")
    if net_delta_v11 < 0:
        blockers.append(f"Delta correct vs V11 insuffisant : {net_delta_v11} < 0.")

    if predicted_draw_rows == 0:
        warnings_list.append("Aucun DRAW recommandé : limite acceptable uniquement si elle est documentée.")

    if not blockers:
        return "V12_ACCEPTED_MARKET_ELO_CALENDAR_CANDIDATE", blockers, warnings_list

    review_ok = (
        selected_accuracy >= REVIEW_MIN_ACCURACY
        and coverage >= REVIEW_MIN_COVERAGE
        and selected_rows >= REVIEW_MIN_SELECTED_ROWS
        and net_delta >= REVIEW_MIN_NET_DELTA_VS_V9
    )
    if review_ok:
        return "V12_MARKET_ELO_CALENDAR_REVIEW", blockers, warnings_list

    return "V12_MARKET_ELO_CALENDAR_REJECTED", blockers, warnings_list


# Écrit la synthèse V12 dans un fichier texte exploitable en preuve RNCP.
def write_summary(
    output_path: Path,
    metadata: dict[str, object],
    split_metadata: dict[str, object],
    model_metadata: dict[str, object],
    best_test_metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - ML 1X2 V12 market + Elo + calendrier selective",
        "179 - Synthèse expérience V12",
        "",
        "Objectif :",
        "Tester si l'enrichissement par consensus de cotes multi-bookmakers, Elo pré-match et contexte calendrier permet d'augmenter la couverture par rapport à V9 sans perdre trop d'accuracy.",
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
        f"- CSV analysés : {metadata.get('csv_files')}",
        f"- Lignes brutes : {metadata.get('raw_rows')}",
        f"- Lignes dataset V12 : {metadata.get('dataset_rows')}",
        f"- Ligues : {metadata.get('leagues')}",
        f"- Saisons : {metadata.get('first_season')} -> {metadata.get('last_season')}",
        f"- Triplets détectés : {metadata.get('detected_triplets')}",
        f"- Triplets utilisés : {metadata.get('usable_triplets')}",
        f"- Exemples triplets utilisés : {metadata.get('usable_triplet_keys')}",
        "",
        "Splits temporels :",
        f"- Mode : {split_metadata.get('split_mode')}",
        f"- Train rows : {split_metadata.get('train_rows')}",
        f"- Validation rows : {split_metadata.get('validation_rows')}",
        f"- Test rows : {split_metadata.get('test_rows')}",
        f"- Validation seasons : {split_metadata.get('validation_seasons')}",
        f"- Test seasons : {split_metadata.get('test_seasons')}",
        "",
        "Features :",
        "- Familles ajoutées : consensus de cotes, mouvements opening/closing, Elo pré-match, repos et congestion calendrier.",
        f"- Nombre de features numériques/catégorielles après encodage : {model_metadata.get('feature_count')}",
        f"- Exemples : {model_metadata.get('feature_columns')}",
        "",
        "Meilleure stratégie V12 sélectionnée sur validation :",
        f"- Strategy : {best_test_metrics.get('strategy')}",
        f"- Model variant : {best_test_metrics.get('model_variant')}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Selected accuracy : {best_test_metrics.get('selected_accuracy')}",
        f"- Coverage : {best_test_metrics.get('coverage')}",
        f"- Abstention rate : {best_test_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_test_metrics.get('selected_rows')}",
        f"- Predicted DRAW rows : {best_test_metrics.get('predicted_draw_rows')}",
        f"- Net correct delta vs V9 static reference : {best_test_metrics.get('net_correct_delta_vs_static_v9')}",
        f"- Net correct delta vs V11 static reference : {best_test_metrics.get('net_correct_delta_vs_static_v11')}",
        f"- V9 reference selected accuracy : {STATIC_V9_SELECTED_ACCURACY}",
        f"- V9 reference coverage : {STATIC_V9_COVERAGE}",
        f"- V9 reference selected rows : {STATIC_V9_SELECTED_ROWS}",
        "",
        "Raisons bloquantes :",
        *(f"- {item}" for item in blockers),
        "- Aucune." if not blockers else "",
        "",
        "Points de vigilance :",
        *(f"- {item}" for item in warnings_list),
        "- Aucun." if not warnings_list else "",
        "",
        "Décision produit :",
        "Ne pas intégrer V12 au produit à ce stade. Le scoring explicable V1 reste le socle officiel tant qu'aucun candidat ML n'est validé fortement.",
        "",
        "Statut de suivi :",
        "- V12 market + Elo + calendrier selective : réalisée si les fichiers 179 à 185 sont générés.",
        "- Fichiers sources à mettre à jour ensuite : plan ML/RNCP et documents de preuves concernés.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision V12 dans un fichier court.
def write_decision(output_path: Path, best_test_metrics: dict[str, object], status: str, blockers: list[str], warnings_list: list[str]) -> None:
    lines = [
        "RubyBets - Décision V12 market + Elo + calendrier selective",
        "185 - Decision expérience V12",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_test_metrics.get('strategy')}",
        f"- Selected accuracy : {best_test_metrics.get('selected_accuracy')}",
        f"- Coverage : {best_test_metrics.get('coverage')}",
        f"- Abstention rate : {best_test_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_test_metrics.get('selected_rows')}",
        f"- Net correct delta vs V9 static reference : {best_test_metrics.get('net_correct_delta_vs_static_v9')}",
        f"- Net correct delta vs V11 static reference : {best_test_metrics.get('net_correct_delta_vs_static_v11')}",
        f"- Predicted DRAW rows : {best_test_metrics.get('predicted_draw_rows')}",
        "",
        "Gates appliqués :",
        f"- Selected accuracy >= {ACCEPT_MIN_ACCURACY}",
        f"- Coverage >= {ACCEPT_MIN_COVERAGE}",
        f"- Selected rows > {ACCEPT_MIN_SELECTED_ROWS}",
        f"- Net correct delta vs V9 >= {ACCEPT_MIN_NET_DELTA_VS_V9}",
        "- Net correct delta vs V11 >= 0.",
        "- Pas de sauvegarde de modèle officiel.",
        "- Pas d'intégration API/frontend/scoring V1.",
        "",
        "Raisons bloquantes :",
        *(f"- {item}" for item in blockers),
        "- Aucune." if not blockers else "",
        "",
        "Points de vigilance :",
        *(f"- {item}" for item in warnings_list),
        "- Aucun." if not warnings_list else "",
        "",
        "Décision opérationnelle :",
        "- Si le statut est ACCEPTED : conserver V12 comme candidat expérimental à analyser en stabilité, sans intégration produit.",
        "- Si le statut est REVIEW : comparer finement V12 à V11 et V9 avant toute décision officielle.",
        "- Si le statut est REJECTED : documenter l'échec et conserver V9/V11 comme références expérimentales.",
        "",
        "Statut de suivi à mettre à jour :",
        "- V12 market + Elo + calendrier selective : réalisée.",
        "- Fichiers concernés : 179, 180, 181, 182, 183, 184, 185.",
        "- Prochaine action : analyser le statut obtenu et décider si une stabilité V12 est justifiée.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Fonction principale : exécute toute l'expérience V12 et génère les preuves.
def main() -> None:
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)

    summary_path = evidence_dir / OUTPUT_SUMMARY
    results_path = evidence_dir / OUTPUT_RESULTS
    best_strategy_path = evidence_dir / OUTPUT_BEST_STRATEGY
    by_class_path = evidence_dir / OUTPUT_BY_CLASS
    by_league_season_path = evidence_dir / OUTPUT_BY_LEAGUE_SEASON
    error_patterns_path = evidence_dir / OUTPUT_ERROR_PATTERNS
    decision_path = evidence_dir / OUTPUT_DECISION

    print("Chargement et enrichissement des CSV bruts pour V12 market + Elo + calendrier...", flush=True)
    dataset, triplet_coverage, metadata = build_v12_dataset(project_root)

    print("Préparation des splits temporels V12...", flush=True)
    train, validation, test, split_metadata = prepare_temporal_splits(dataset)

    print("Entraînement et génération des probabilités V12...", flush=True)
    validation_predictions, test_predictions, model_metadata = build_candidate_predictions(train, validation, test)

    print("Évaluation des stratégies V12 market + Elo + calendrier selective...", flush=True)
    results, best_predictions = evaluate_policies(validation_predictions, test_predictions)

    test_rows = results[results["scope"] == "test"].copy()
    if test_rows.empty:
        raise RuntimeError("Aucun résultat test V12 généré.")
    best_test_metrics = test_rows.iloc[0].to_dict()
    status, blockers, warnings_list = decide_v12(best_test_metrics)

    by_class = build_by_class(best_predictions)
    by_league_season = build_by_league_season(best_predictions)
    error_patterns = build_error_patterns(best_predictions)

    print("Génération des fichiers de preuve V12...", flush=True)
    results.to_csv(results_path, index=False, encoding="utf-8")
    pd.DataFrame([best_test_metrics]).to_csv(best_strategy_path, index=False, encoding="utf-8")
    by_class.to_csv(by_class_path, index=False, encoding="utf-8")
    by_league_season.to_csv(by_league_season_path, index=False, encoding="utf-8")
    error_patterns.to_csv(error_patterns_path, index=False, encoding="utf-8")
    write_summary(summary_path, metadata, split_metadata, model_metadata, best_test_metrics, status, blockers, warnings_list)
    write_decision(decision_path, best_test_metrics, status, blockers, warnings_list)

    print("OK - Expérience V12 market + Elo + calendrier selective terminée.", flush=True)
    print(f"Status: {status}", flush=True)
    print(f"Selected validation strategy: {best_test_metrics.get('strategy')}", flush=True)
    print(f"Test selected accuracy: {best_test_metrics.get('selected_accuracy')}", flush=True)
    print(f"Test coverage: {best_test_metrics.get('coverage')}", flush=True)
    print(f"Test abstention rate: {best_test_metrics.get('abstention_rate')}", flush=True)
    print(f"Selected rows: {best_test_metrics.get('selected_rows')}", flush=True)
    print(f"Predicted DRAW rows: {best_test_metrics.get('predicted_draw_rows')}", flush=True)
    print(f"Net correct delta vs V9 static reference: {best_test_metrics.get('net_correct_delta_vs_static_v9')}", flush=True)
    print(f"Net correct delta vs V11 static reference: {best_test_metrics.get('net_correct_delta_vs_static_v11')}", flush=True)
    print(f"Summary saved: {summary_path}", flush=True)
    print(f"Results CSV saved: {results_path}", flush=True)
    print(f"Best strategy CSV saved: {best_strategy_path}", flush=True)
    print(f"By class CSV saved: {by_class_path}", flush=True)
    print(f"By league/season CSV saved: {by_league_season_path}", flush=True)
    print(f"Error patterns CSV saved: {error_patterns_path}", flush=True)
    print(f"Decision saved: {decision_path}", flush=True)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# data/ml/raw/*.csv
#        ↓ lecture seule
# train_1x2_v12_market_elo_calendar_selective.py
#        ↓ génération de preuves uniquement
# reports/evidence/ml_training/179 à 185
#
# Aucune communication avec PostgreSQL, ml.features, models/, API, frontend ou scoring explicable V1.
