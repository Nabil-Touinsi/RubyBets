# Rôle du fichier : tester une V13 expérimentale en double chance 1X / X2 / 12, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


TARGET_COLUMN = "target_result"
TARGET_CLASSES = ["HOME_WIN", "DRAW", "AWAY_WIN"]
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"
STRICT_TYPE = "STRICT_1X2"
DOUBLE_CHANCE_TYPE = "DOUBLE_CHANCE"

OUTPUT_SUMMARY = "187_1x2_v13_double_chance_summary.txt"
OUTPUT_RESULTS = "188_1x2_v13_double_chance_results.csv"
OUTPUT_BY_MARKET = "189_1x2_v13_double_chance_by_market.csv"
OUTPUT_BY_LEAGUE_SEASON = "190_1x2_v13_double_chance_by_league_season.csv"
OUTPUT_ERROR_PATTERNS = "191_1x2_v13_double_chance_error_patterns.csv"
OUTPUT_DECISION = "192_1x2_v13_double_chance_decision.txt"

RECENT_TEST_START_YEAR = 2022
VALIDATION_START_YEAR = 2021
RECENT_COVERAGE_START_YEAR = 2020
MIN_RECENT_TRIPLET_COVERAGE = 0.80
MIN_RECENT_TRIPLET_ROWS = 1000

STATIC_V9_SELECTED_ACCURACY = 0.7874
STATIC_V9_COVERAGE = 0.1492
STATIC_V9_SELECTED_ROWS = 795
STATIC_V11_SELECTED_ACCURACY = 0.7363
STATIC_V11_COVERAGE = 0.2326
STATIC_V11_SELECTED_ROWS = 1240

ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY = 0.82
ACCEPT_MIN_COVERAGE = 0.50
ACCEPT_MIN_SELECTED_ROWS = 2500
ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY = 0.75

REVIEW_MIN_DOUBLE_CHANCE_ACCURACY = 0.78
REVIEW_MIN_COVERAGE = 0.35
REVIEW_MIN_SELECTED_ROWS = 1800

DOUBLE_CHANCE_TOP2_THRESHOLDS = [0.68, 0.70, 0.72, 0.74, 0.76, 0.78, 0.80, 0.82]
MAX_ENTROPY_THRESHOLDS = [1.05, 1.07, 1.09, 1.11]
MIN_AVAILABLE_TRIPLETS = [1, 3, 5]
MIN_AGREEMENT_THRESHOLDS = [0.00, 0.50, 0.70]
STRICT_MODES = ["no_strict", "strict_if_very_strong"]
STRICT_MAX_PROBABILITY_THRESHOLDS = [0.78, 0.80]
STRICT_MARGIN_THRESHOLDS = [0.20]

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
class V13Policy:
    double_chance_top2_threshold: float
    max_entropy_threshold: float
    min_available_triplets: int
    min_agreement_threshold: float
    strict_mode: str
    strict_max_probability_threshold: float
    strict_margin_threshold: float

    @property
    def name(self) -> str:
        return (
            "v13_double_chance"
            f"_top2{self.double_chance_top2_threshold:.2f}"
            f"_ent{self.max_entropy_threshold:.2f}"
            f"_trip{self.min_available_triplets}"
            f"_agr{self.min_agreement_threshold:.2f}"
            f"_{self.strict_mode}"
            f"_sp{self.strict_max_probability_threshold:.2f}"
            f"_sm{self.strict_margin_threshold:.2f}"
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


# Liste les fichiers CSV bruts disponibles pour V13.
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


# Charge tous les CSV bruts et construit le DataFrame source V13.
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


# Sélectionne les triplets de cotes suffisamment complets pour la V13.
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


# Transforme une classe omise en marché double chance lisible.
def map_omitted_class_to_double_chance(omitted_class: str) -> str:
    mapping = {
        "AWAY_WIN": "1X",
        "HOME_WIN": "X2",
        "DRAW": "12",
    }
    return mapping.get(str(omitted_class), "UNKNOWN")


# Transforme une double chance en classes couvertes.
def covered_classes_for_double_chance(double_chance: str) -> set[str]:
    mapping = {
        "1X": {"HOME_WIN", "DRAW"},
        "X2": {"DRAW", "AWAY_WIN"},
        "12": {"HOME_WIN", "AWAY_WIN"},
    }
    return mapping.get(str(double_chance), set())


# Décrit le profil du signal de marché pour faciliter l'analyse des erreurs.
def infer_signal_profile(row: pd.Series) -> str:
    max_probability = float(row.get("market_favorite_prob", 0.0))
    margin = float(row.get("market_margin_top1_top2", 0.0))
    draw_probability = float(row.get("market_draw_prob_avg", 0.0))
    home_away_gap = abs(float(row.get("market_home_away_gap", 0.0)))
    omitted_class = str(row.get("v13_omitted_class", ""))

    if max_probability >= 0.62 and margin >= 0.18:
        return "CLEAR_FAVORITE"
    if home_away_gap <= 0.08 and draw_probability >= 0.26:
        return "BALANCED_DRAW_PRESSURE"
    if omitted_class == "DRAW":
        return "LOW_DRAW_12_PROFILE"
    if draw_probability >= 0.30:
        return "DRAW_PRESSURE"
    return "MIXED_SIGNAL"


# Construit les features market consensus et les signaux V13 en mémoire.
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

    consensus_probabilities = features[
        ["market_home_prob_avg", "market_draw_prob_avg", "market_away_prob_avg"]
    ].fillna(0.0)
    probability_sums = consensus_probabilities.sum(axis=1).replace(0.0, np.nan)
    consensus_probabilities = consensus_probabilities.div(probability_sums, axis=0).fillna(0.0)

    probability_array = consensus_probabilities.to_numpy()
    predicted_indices = np.argmax(probability_array, axis=1)
    omitted_indices = np.argmin(probability_array, axis=1)
    sorted_probabilities = np.sort(probability_array, axis=1)

    features["market_home_prob_avg"] = consensus_probabilities["market_home_prob_avg"]
    features["market_draw_prob_avg"] = consensus_probabilities["market_draw_prob_avg"]
    features["market_away_prob_avg"] = consensus_probabilities["market_away_prob_avg"]
    features["market_consensus_prediction"] = np.array(TARGET_CLASSES)[predicted_indices]
    features["market_favorite_prob"] = sorted_probabilities[:, -1]
    features["market_second_prob"] = sorted_probabilities[:, -2]
    features["market_lowest_prob"] = sorted_probabilities[:, 0]
    features["market_top2_sum"] = sorted_probabilities[:, -1] + sorted_probabilities[:, -2]
    features["market_margin_top1_top2"] = features["market_favorite_prob"] - features["market_second_prob"]
    features["market_home_away_gap"] = features["market_home_prob_avg"] - features["market_away_prob_avg"]

    entropy_base = consensus_probabilities.replace(0.0, np.nan)
    features["market_entropy"] = -(entropy_base * np.log(entropy_base)).sum(axis=1).fillna(0.0)

    features["v13_strict_prediction"] = features["market_consensus_prediction"]
    features["v13_omitted_class"] = np.array(TARGET_CLASSES)[omitted_indices]
    features["v13_double_chance"] = features["v13_omitted_class"].map(map_omitted_class_to_double_chance)

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

    features["v13_signal_profile"] = features.apply(infer_signal_profile, axis=1)
    return features


# Construit le dataset V13 final sans écrire en base de données.
def build_v13_dataset(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    dataframe, metadata = load_raw_match_dataframe(project_root)
    triplets = detect_odds_triplets(dataframe.columns)
    usable_triplets, triplet_coverage = select_usable_triplets(dataframe, triplets)
    features = build_market_consensus_features(dataframe, usable_triplets)

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


# Crée les splits temporels validation / test sans entraîner de modèle officiel.
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
        "train_rows_reference_only": len(train),
        "validation_rows": len(validation),
        "test_rows": len(test),
        "train_seasons_reference_only": ", ".join(sorted(train["__season"].dropna().astype(str).unique().tolist())),
        "validation_seasons": ", ".join(sorted(validation["__season"].dropna().astype(str).unique().tolist())),
        "test_seasons": ", ".join(sorted(test["__season"].dropna().astype(str).unique().tolist())),
    }
    return train, validation, test, metadata


# Génère les politiques sélectives V13 à évaluer.
def build_policies() -> list[V13Policy]:
    policies: list[V13Policy] = []
    for top2_threshold in DOUBLE_CHANCE_TOP2_THRESHOLDS:
        for entropy_threshold in MAX_ENTROPY_THRESHOLDS:
            for min_triplets in MIN_AVAILABLE_TRIPLETS:
                for agreement_threshold in MIN_AGREEMENT_THRESHOLDS:
                    for strict_mode in STRICT_MODES:
                        strict_probability_thresholds = (
                            STRICT_MAX_PROBABILITY_THRESHOLDS if strict_mode == "strict_if_very_strong" else [0.99]
                        )
                        strict_margin_thresholds = STRICT_MARGIN_THRESHOLDS if strict_mode == "strict_if_very_strong" else [0.99]
                        for strict_probability in strict_probability_thresholds:
                            for strict_margin in strict_margin_thresholds:
                                policies.append(
                                    V13Policy(
                                        double_chance_top2_threshold=top2_threshold,
                                        max_entropy_threshold=entropy_threshold,
                                        min_available_triplets=min_triplets,
                                        min_agreement_threshold=agreement_threshold,
                                        strict_mode=strict_mode,
                                        strict_max_probability_threshold=strict_probability,
                                        strict_margin_threshold=strict_margin,
                                    )
                                )
    return policies


# Vérifie si le résultat réel est couvert par une double chance.
def is_double_chance_correct(target: str, double_chance: str) -> bool:
    return str(target) in covered_classes_for_double_chance(str(double_chance))


# Applique une politique V13 et produit les colonnes de sélection/abstention.
def apply_policy(dataframe: pd.DataFrame, policy: V13Policy) -> pd.DataFrame:
    output = dataframe.copy()

    numeric_columns = [
        "market_top2_sum",
        "market_entropy",
        "market_available_triplets",
        "market_bookmaker_agreement_score",
        "market_favorite_prob",
        "market_margin_top1_top2",
    ]
    for column in numeric_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0.0)

    double_chance_mask = (
        (output["market_top2_sum"] >= policy.double_chance_top2_threshold)
        & (output["market_entropy"] <= policy.max_entropy_threshold)
        & (output["market_available_triplets"] >= policy.min_available_triplets)
        & (output["market_bookmaker_agreement_score"] >= policy.min_agreement_threshold)
    )

    if policy.strict_mode == "strict_if_very_strong":
        strict_mask = (
            (output["market_favorite_prob"] >= policy.strict_max_probability_threshold)
            & (output["market_margin_top1_top2"] >= policy.strict_margin_threshold)
            & (output["v13_strict_prediction"] != "DRAW")
        )
    else:
        strict_mask = pd.Series([False] * len(output), index=output.index)

    selected_mask = double_chance_mask | strict_mask
    strict_selected_mask = selected_mask & strict_mask
    double_selected_mask = selected_mask & ~strict_mask

    output["v13_strategy"] = policy.name
    output["v13_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v13_recommendation_type"] = np.where(
        strict_selected_mask,
        STRICT_TYPE,
        np.where(double_selected_mask, DOUBLE_CHANCE_TYPE, "ABSTAIN"),
    )
    output["v13_recommendation_value"] = np.where(
        strict_selected_mask,
        output["v13_strict_prediction"],
        np.where(double_selected_mask, output["v13_double_chance"], "ABSTAIN"),
    )
    output["v13_double_chance_is_correct"] = [
        is_double_chance_correct(target, double_chance)
        for target, double_chance in zip(output[TARGET_COLUMN], output["v13_double_chance"], strict=False)
    ]
    output["v13_strict_is_correct"] = output[TARGET_COLUMN].astype(str) == output["v13_strict_prediction"].astype(str)
    output["v13_is_correct"] = np.where(
        output["v13_recommendation_type"] == STRICT_TYPE,
        output["v13_strict_is_correct"],
        np.where(output["v13_recommendation_type"] == DOUBLE_CHANCE_TYPE, output["v13_double_chance_is_correct"], False),
    )
    return output


# Calcule les métriques d'une politique V13 sur un périmètre donné.
def compute_policy_metrics(dataframe: pd.DataFrame, policy: V13Policy, scope: str) -> dict[str, object]:
    predictions = apply_policy(dataframe, policy)
    selected = predictions[predictions["v13_recommendation_status"] == RECOMMEND_STATUS]
    double_selected = selected[selected["v13_recommendation_type"] == DOUBLE_CHANCE_TYPE]
    strict_selected = selected[selected["v13_recommendation_type"] == STRICT_TYPE]

    total_rows = len(predictions)
    selected_rows = len(selected)
    mixed_correct_rows = int(selected["v13_is_correct"].sum()) if selected_rows else 0
    double_rows = len(double_selected)
    double_correct_rows = int(double_selected["v13_double_chance_is_correct"].sum()) if double_rows else 0
    strict_rows = len(strict_selected)
    strict_correct_rows = int(strict_selected["v13_strict_is_correct"].sum()) if strict_rows else 0

    strict_reference_correct_rows = int(predictions["v13_strict_is_correct"].sum())
    double_reference_correct_rows = int(predictions["v13_double_chance_is_correct"].sum())
    selected_strict_reference_correct_rows = int(selected["v13_strict_is_correct"].sum()) if selected_rows else 0

    return {
        "scope": scope,
        "strategy": policy.name,
        "double_chance_top2_threshold": policy.double_chance_top2_threshold,
        "max_entropy_threshold": policy.max_entropy_threshold,
        "min_available_triplets": policy.min_available_triplets,
        "min_agreement_threshold": policy.min_agreement_threshold,
        "strict_mode": policy.strict_mode,
        "strict_max_probability_threshold": policy.strict_max_probability_threshold,
        "strict_margin_threshold": policy.strict_margin_threshold,
        "total_rows": total_rows,
        "selected_rows": selected_rows,
        "abstained_rows": total_rows - selected_rows,
        "coverage": rounded(safe_rate(selected_rows, total_rows)),
        "abstention_rate": rounded(1.0 - safe_rate(selected_rows, total_rows)),
        "mixed_accuracy": rounded(safe_rate(mixed_correct_rows, selected_rows)),
        "mixed_correct_rows": mixed_correct_rows,
        "double_chance_rows": double_rows,
        "double_chance_accuracy": rounded(safe_rate(double_correct_rows, double_rows)),
        "double_chance_correct_rows": double_correct_rows,
        "strict_1x2_rows": strict_rows,
        "strict_1x2_accuracy": rounded(safe_rate(strict_correct_rows, strict_rows)),
        "strict_1x2_correct_rows": strict_correct_rows,
        "strict_market_accuracy_all_rows": rounded(safe_rate(strict_reference_correct_rows, total_rows)),
        "double_chance_accuracy_all_rows": rounded(safe_rate(double_reference_correct_rows, total_rows)),
        "strict_market_accuracy_on_selected_rows": rounded(
            safe_rate(selected_strict_reference_correct_rows, selected_rows)
        ),
        "selected_rows_delta_vs_v9": selected_rows - STATIC_V9_SELECTED_ROWS if scope == "test" else 0,
        "selected_rows_delta_vs_v11": selected_rows - STATIC_V11_SELECTED_ROWS if scope == "test" else 0,
        "coverage_delta_vs_v9": rounded(safe_rate(selected_rows, total_rows) - STATIC_V9_COVERAGE) if scope == "test" else 0.0,
        "coverage_delta_vs_v11": rounded(safe_rate(selected_rows, total_rows) - STATIC_V11_COVERAGE) if scope == "test" else 0.0,
        "selected_1x_rows": int((selected["v13_recommendation_value"] == "1X").sum()) if selected_rows else 0,
        "selected_x2_rows": int((selected["v13_recommendation_value"] == "X2").sum()) if selected_rows else 0,
        "selected_12_rows": int((selected["v13_recommendation_value"] == "12").sum()) if selected_rows else 0,
        "actual_draw_rows_selected": int((selected[TARGET_COLUMN] == "DRAW").sum()) if selected_rows else 0,
    }


# Évalue toutes les politiques V13 sur validation et test final.
def evaluate_policies(validation: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    policies = build_policies()
    rows = [compute_policy_metrics(validation, policy, "validation") for policy in policies]
    results = pd.DataFrame(rows)

    validation_candidates = results[
        (results["scope"] == "validation")
        & (results["selected_rows"] >= 300)
        & (results["coverage"] >= 0.20)
    ].copy()

    if validation_candidates.empty:
        raise RuntimeError("Aucune politique V13 exploitable sur validation.")

    validation_candidates["validation_gate_accuracy"] = (
        validation_candidates["double_chance_accuracy"] >= ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY
    )
    validation_candidates["validation_gate_coverage"] = validation_candidates["coverage"] >= ACCEPT_MIN_COVERAGE
    validation_candidates["validation_gate_rows"] = validation_candidates["selected_rows"] >= 800
    validation_candidates["selection_score"] = (
        validation_candidates["coverage"] * 0.58
        + validation_candidates["double_chance_accuracy"] * 0.34
        + validation_candidates["mixed_accuracy"] * 0.08
    )
    validation_candidates = validation_candidates.sort_values(
        by=[
            "validation_gate_accuracy",
            "validation_gate_coverage",
            "validation_gate_rows",
            "selection_score",
            "coverage",
            "double_chance_accuracy",
        ],
        ascending=[False, False, False, False, False, False],
    )

    best_strategy_name = str(validation_candidates.iloc[0]["strategy"])
    best_policy = next(policy for policy in policies if policy.name == best_strategy_name)
    rows.append(compute_policy_metrics(test, best_policy, "test"))
    test_policy_dataframe = apply_policy(test, best_policy)

    return pd.DataFrame(rows), test_policy_dataframe


# Calcule les résultats séparés par marché recommandé et par référence 1X2 stricte.
def build_by_market(best_predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total_rows = len(best_predictions)
    selected = best_predictions[best_predictions["v13_recommendation_status"] == RECOMMEND_STATUS]

    for (recommendation_type, recommendation_value), group in selected.groupby(
        ["v13_recommendation_type", "v13_recommendation_value"], dropna=False
    ):
        rows.append(
            {
                "metric_scope": "selected_recommendations",
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "total_rows": total_rows,
                "selected_rows": len(group),
                "coverage": rounded(safe_rate(len(group), total_rows)),
                "correct_rows": int(group["v13_is_correct"].sum()),
                "accuracy": rounded(safe_rate(int(group["v13_is_correct"].sum()), len(group))),
                "actual_draw_rows": int((group[TARGET_COLUMN] == "DRAW").sum()),
                "average_market_top2_sum": rounded(group["market_top2_sum"].mean()),
                "average_market_entropy": rounded(group["market_entropy"].mean()),
            }
        )

    for strict_prediction, group in best_predictions.groupby("v13_strict_prediction", dropna=False):
        rows.append(
            {
                "metric_scope": "strict_1x2_reference_all_rows",
                "recommendation_type": "STRICT_1X2_REFERENCE",
                "recommendation_value": strict_prediction,
                "total_rows": total_rows,
                "selected_rows": len(group),
                "coverage": rounded(safe_rate(len(group), total_rows)),
                "correct_rows": int(group["v13_strict_is_correct"].sum()),
                "accuracy": rounded(safe_rate(int(group["v13_strict_is_correct"].sum()), len(group))),
                "actual_draw_rows": int((group[TARGET_COLUMN] == "DRAW").sum()),
                "average_market_top2_sum": rounded(group["market_top2_sum"].mean()),
                "average_market_entropy": rounded(group["market_entropy"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["metric_scope", "selected_rows"], ascending=[True, False])


# Calcule la stabilité de la meilleure politique par ligue et saison.
def build_by_league_season(best_predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = best_predictions.groupby(["__league_code", "__season"], dropna=False)
    for (league_code, season), group in grouped:
        selected = group[group["v13_recommendation_status"] == RECOMMEND_STATUS]
        double_selected = selected[selected["v13_recommendation_type"] == DOUBLE_CHANCE_TYPE]
        selected_rows = len(selected)
        double_rows = len(double_selected)
        mixed_accuracy = safe_rate(int(selected["v13_is_correct"].sum()), selected_rows)
        double_accuracy = safe_rate(int(double_selected["v13_double_chance_is_correct"].sum()), double_rows)
        segment_status = "LOW_VOLUME"
        if selected_rows >= 100 and double_accuracy < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY:
            segment_status = "BELOW_MAJOR_SEGMENT_GATE"
        elif selected_rows >= 100:
            segment_status = "STABLE_REVIEW"

        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "total_rows": len(group),
                "selected_rows": selected_rows,
                "coverage": rounded(safe_rate(selected_rows, len(group))),
                "mixed_accuracy": rounded(mixed_accuracy),
                "double_chance_rows": double_rows,
                "double_chance_accuracy": rounded(double_accuracy),
                "strict_1x2_rows": int((selected["v13_recommendation_type"] == STRICT_TYPE).sum()) if selected_rows else 0,
                "strict_reference_accuracy_all_rows": rounded(safe_rate(int(group["v13_strict_is_correct"].sum()), len(group))),
                "actual_draw_rows_selected": int((selected[TARGET_COLUMN] == "DRAW").sum()) if selected_rows else 0,
                "selected_1x_rows": int((selected["v13_recommendation_value"] == "1X").sum()) if selected_rows else 0,
                "selected_x2_rows": int((selected["v13_recommendation_value"] == "X2").sum()) if selected_rows else 0,
                "selected_12_rows": int((selected["v13_recommendation_value"] == "12").sum()) if selected_rows else 0,
                "segment_status": segment_status,
            }
        )
    return pd.DataFrame(rows).sort_values(["selected_rows", "double_chance_accuracy"], ascending=[False, True])


# Génère les principaux motifs d'erreur restants sur les recommandations sélectionnées.
def build_error_patterns(best_predictions: pd.DataFrame) -> pd.DataFrame:
    selected_errors = best_predictions[
        (best_predictions["v13_recommendation_status"] == RECOMMEND_STATUS)
        & (~best_predictions["v13_is_correct"])
    ].copy()

    if selected_errors.empty:
        return pd.DataFrame(
            columns=[
                "league_code",
                "season",
                "recommendation_type",
                "recommendation_value",
                "actual_result",
                "omitted_class",
                "signal_profile",
                "rows",
                "average_market_top2_sum",
                "average_market_entropy",
                "average_market_favorite_prob",
            ]
        )

    grouped = selected_errors.groupby(
        [
            "__league_code",
            "__season",
            "v13_recommendation_type",
            "v13_recommendation_value",
            TARGET_COLUMN,
            "v13_omitted_class",
            "v13_signal_profile",
        ],
        dropna=False,
    )
    rows: list[dict[str, object]] = []
    for keys, group in grouped:
        league_code, season, recommendation_type, recommendation_value, actual_result, omitted_class, signal_profile = keys
        rows.append(
            {
                "league_code": league_code,
                "season": season,
                "recommendation_type": recommendation_type,
                "recommendation_value": recommendation_value,
                "actual_result": actual_result,
                "omitted_class": omitted_class,
                "signal_profile": signal_profile,
                "rows": len(group),
                "average_market_top2_sum": rounded(group["market_top2_sum"].mean()),
                "average_market_entropy": rounded(group["market_entropy"].mean()),
                "average_market_favorite_prob": rounded(group["market_favorite_prob"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("rows", ascending=False)


# Détermine la décision V13 selon les gates fixés avant l'expérience.
def decide_v13(test_metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings_list: list[str] = []

    double_accuracy = float(test_metrics.get("double_chance_accuracy", 0.0))
    coverage = float(test_metrics.get("coverage", 0.0))
    selected_rows = int(test_metrics.get("selected_rows", 0))
    strict_rows = int(test_metrics.get("strict_1x2_rows", 0))
    major_segments_below_gate = by_league_season[
        (by_league_season["selected_rows"] >= 100)
        & (by_league_season["double_chance_accuracy"] < ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY)
    ]

    if double_accuracy < ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY:
        blockers.append(
            "Accuracy double chance inférieure au gate fort : "
            f"{double_accuracy} < {ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY}."
        )
    if coverage < ACCEPT_MIN_COVERAGE:
        blockers.append(f"Coverage inférieur au gate fort : {coverage} < {ACCEPT_MIN_COVERAGE}.")
    if selected_rows < ACCEPT_MIN_SELECTED_ROWS:
        blockers.append(f"Nombre de matchs sélectionnés insuffisant : {selected_rows} < {ACCEPT_MIN_SELECTED_ROWS}.")
    if not major_segments_below_gate.empty:
        warnings_list.append(
            "Au moins un segment ligue/saison majeur passe sous le gate 0.75 : "
            f"{len(major_segments_below_gate)} segment(s)."
        )

    if strict_rows == 0:
        warnings_list.append(
            "La meilleure stratégie retenue ne force pas de 1X2 strict : la V13 doit rester présentée comme double chance selective."
        )

    if not blockers and major_segments_below_gate.empty:
        return "V13_DOUBLE_CHANCE_STRONG_REVIEW", blockers, warnings_list

    review_ok = (
        double_accuracy >= REVIEW_MIN_DOUBLE_CHANCE_ACCURACY
        and coverage >= REVIEW_MIN_COVERAGE
        and selected_rows >= REVIEW_MIN_SELECTED_ROWS
    )
    if review_ok:
        return "V13_DOUBLE_CHANCE_REVIEW", blockers, warnings_list

    return "V13_DOUBLE_CHANCE_REJECTED", blockers, warnings_list


# Écrit la synthèse V13 dans un fichier texte exploitable en preuve RNCP.
def write_summary(
    output_path: Path,
    metadata: dict[str, object],
    split_metadata: dict[str, object],
    best_test_metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - ML 1X2 V13 double chance selective",
        "187 - Synthèse expérience V13",
        "",
        "Objectif :",
        "Tester une recommandation prudente en double chance 1X / X2 / 12 afin d'augmenter la couverture sans présenter cela comme une amélioration directe du 1X2 strict.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des CSV bruts Football-Data dans data/ml/raw.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "- Aucune donnée Understat/xG ajoutée au produit.",
        "",
        "Périmètre data :",
        f"- CSV analysés : {metadata.get('csv_files')}",
        f"- Lignes brutes : {metadata.get('raw_rows')}",
        f"- Lignes dataset V13 : {metadata.get('dataset_rows')}",
        f"- Ligues : {metadata.get('leagues')}",
        f"- Saisons : {metadata.get('first_season')} -> {metadata.get('last_season')}",
        f"- Triplets détectés : {metadata.get('detected_triplets')}",
        f"- Triplets utilisés : {metadata.get('usable_triplets')}",
        f"- Exemples triplets utilisés : {metadata.get('usable_triplet_keys')}",
        "",
        "Splits temporels :",
        f"- Mode : {split_metadata.get('split_mode')}",
        f"- Train rows référence uniquement : {split_metadata.get('train_rows_reference_only')}",
        f"- Validation rows : {split_metadata.get('validation_rows')}",
        f"- Test rows : {split_metadata.get('test_rows')}",
        f"- Validation seasons : {split_metadata.get('validation_seasons')}",
        f"- Test seasons : {split_metadata.get('test_seasons')}",
        "",
        "Meilleure stratégie V13 sélectionnée sur validation :",
        f"- Strategy : {best_test_metrics.get('strategy')}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Mixed accuracy : {best_test_metrics.get('mixed_accuracy')}",
        f"- Double chance accuracy : {best_test_metrics.get('double_chance_accuracy')}",
        f"- Strict 1X2 accuracy on selected rows : {best_test_metrics.get('strict_market_accuracy_on_selected_rows')}",
        f"- Strict 1X2 reference accuracy on all rows : {best_test_metrics.get('strict_market_accuracy_all_rows')}",
        f"- Double chance reference accuracy on all rows : {best_test_metrics.get('double_chance_accuracy_all_rows')}",
        f"- Coverage : {best_test_metrics.get('coverage')}",
        f"- Abstention rate : {best_test_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_test_metrics.get('selected_rows')}",
        f"- Double chance rows : {best_test_metrics.get('double_chance_rows')}",
        f"- Strict 1X2 rows : {best_test_metrics.get('strict_1x2_rows')}",
        f"- Selected rows delta vs V9 : {best_test_metrics.get('selected_rows_delta_vs_v9')}",
        f"- Selected rows delta vs V11 : {best_test_metrics.get('selected_rows_delta_vs_v11')}",
        f"- Coverage delta vs V9 : {best_test_metrics.get('coverage_delta_vs_v9')}",
        f"- Coverage delta vs V11 : {best_test_metrics.get('coverage_delta_vs_v11')}",
        f"- Répartition 1X / X2 / 12 : {best_test_metrics.get('selected_1x_rows')} / {best_test_metrics.get('selected_x2_rows')} / {best_test_metrics.get('selected_12_rows')}",
        "",
        "Références connues :",
        f"- V9 selected accuracy : {STATIC_V9_SELECTED_ACCURACY}",
        f"- V9 coverage : {STATIC_V9_COVERAGE}",
        f"- V9 selected rows : {STATIC_V9_SELECTED_ROWS}",
        f"- V11 selected accuracy 1X2 strict : {STATIC_V11_SELECTED_ACCURACY}",
        f"- V11 coverage : {STATIC_V11_COVERAGE}",
        f"- V11 selected rows : {STATIC_V11_SELECTED_ROWS}",
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
        "Ne pas intégrer V13 au produit à ce stade. V13 est une expérimentation de format de recommandation prudente ; le scoring explicable V1 reste le socle officiel.",
        "",
        "Statut de suivi :",
        "- V13 double chance selective : réalisée si les fichiers 187 à 192 sont générés.",
        "- Fichiers sources à mettre à jour ensuite : plan ML/RNCP, matrice de preuves et documents de soutenance concernés.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Écrit la décision V13 dans un fichier court.
def write_decision(
    output_path: Path,
    best_test_metrics: dict[str, object],
    status: str,
    blockers: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V13 double chance selective",
        "192 - Décision expérience V13",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_test_metrics.get('strategy')}",
        f"- Double chance accuracy : {best_test_metrics.get('double_chance_accuracy')}",
        f"- Mixed accuracy : {best_test_metrics.get('mixed_accuracy')}",
        f"- Coverage : {best_test_metrics.get('coverage')}",
        f"- Abstention rate : {best_test_metrics.get('abstention_rate')}",
        f"- Selected rows : {best_test_metrics.get('selected_rows')}",
        f"- Double chance rows : {best_test_metrics.get('double_chance_rows')}",
        f"- Strict 1X2 rows : {best_test_metrics.get('strict_1x2_rows')}",
        f"- Strict 1X2 reference accuracy all rows : {best_test_metrics.get('strict_market_accuracy_all_rows')}",
        f"- Selected rows delta vs V11 : {best_test_metrics.get('selected_rows_delta_vs_v11')}",
        f"- Coverage delta vs V11 : {best_test_metrics.get('coverage_delta_vs_v11')}",
        "",
        "Gates appliqués :",
        f"- Double chance accuracy >= {ACCEPT_MIN_DOUBLE_CHANCE_ACCURACY}",
        f"- Coverage >= {ACCEPT_MIN_COVERAGE}",
        f"- Selected rows >= {ACCEPT_MIN_SELECTED_ROWS}",
        f"- Segment majeur >= {ACCEPT_MIN_MAJOR_SEGMENT_ACCURACY}",
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
        "- V13 peut être conservée comme expérimentation double chance si le statut est REVIEW ou STRONG_REVIEW.",
        "- V13 ne doit pas être présentée comme une amélioration directe du 1X2 strict.",
        "- V13 ne doit pas être intégrée au produit sans validation de stabilité dédiée et arbitrage produit explicite.",
        "",
        "Statut de suivi à mettre à jour :",
        "- V13 double chance selective : réalisée.",
        "- Fichiers concernés : 187, 188, 189, 190, 191, 192.",
        "- Prochaine action : analyser les fichiers générés puis décider si une stabilité V13 dédiée est justifiée.",
    ]
    output_path.write_text("\n".join([line for line in lines if line is not None]), encoding="utf-8")


# Fonction principale : exécute toute l'expérience V13 et génère les preuves.
def main() -> None:
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)

    summary_path = evidence_dir / OUTPUT_SUMMARY
    results_path = evidence_dir / OUTPUT_RESULTS
    by_market_path = evidence_dir / OUTPUT_BY_MARKET
    by_league_season_path = evidence_dir / OUTPUT_BY_LEAGUE_SEASON
    error_patterns_path = evidence_dir / OUTPUT_ERROR_PATTERNS
    decision_path = evidence_dir / OUTPUT_DECISION

    print("Chargement et enrichissement des CSV bruts pour V13 double chance selective...", flush=True)
    dataset, _triplet_coverage, metadata = build_v13_dataset(project_root)

    print("Préparation des splits temporels V13...", flush=True)
    _train, validation, test, split_metadata = prepare_temporal_splits(dataset)

    print("Évaluation des stratégies V13 double chance selective...", flush=True)
    results, best_predictions = evaluate_policies(validation, test)

    test_rows = results[results["scope"] == "test"].copy()
    if test_rows.empty:
        raise RuntimeError("Aucun résultat test V13 généré.")
    best_test_metrics = test_rows.iloc[0].to_dict()

    by_market = build_by_market(best_predictions)
    by_league_season = build_by_league_season(best_predictions)
    error_patterns = build_error_patterns(best_predictions)
    status, blockers, warnings_list = decide_v13(best_test_metrics, by_league_season)

    print("Génération des fichiers de preuve V13...", flush=True)
    results.to_csv(results_path, index=False, encoding="utf-8")
    by_market.to_csv(by_market_path, index=False, encoding="utf-8")
    by_league_season.to_csv(by_league_season_path, index=False, encoding="utf-8")
    error_patterns.to_csv(error_patterns_path, index=False, encoding="utf-8")
    write_summary(summary_path, metadata, split_metadata, best_test_metrics, status, blockers, warnings_list)
    write_decision(decision_path, best_test_metrics, status, blockers, warnings_list)

    print("OK - Expérience V13 double chance selective terminée.", flush=True)
    print(f"Status: {status}", flush=True)
    print(f"Selected validation strategy: {best_test_metrics.get('strategy')}", flush=True)
    print(f"Test double chance accuracy: {best_test_metrics.get('double_chance_accuracy')}", flush=True)
    print(f"Test mixed accuracy: {best_test_metrics.get('mixed_accuracy')}", flush=True)
    print(f"Test coverage: {best_test_metrics.get('coverage')}", flush=True)
    print(f"Test abstention rate: {best_test_metrics.get('abstention_rate')}", flush=True)
    print(f"Selected rows: {best_test_metrics.get('selected_rows')}", flush=True)
    print(f"Double chance rows: {best_test_metrics.get('double_chance_rows')}", flush=True)
    print(f"Strict 1X2 rows: {best_test_metrics.get('strict_1x2_rows')}", flush=True)
    print(f"Selected rows delta vs V11: {best_test_metrics.get('selected_rows_delta_vs_v11')}", flush=True)
    print(f"Summary saved: {summary_path}", flush=True)
    print(f"Results CSV saved: {results_path}", flush=True)
    print(f"By market CSV saved: {by_market_path}", flush=True)
    print(f"By league/season CSV saved: {by_league_season_path}", flush=True)
    print(f"Error patterns CSV saved: {error_patterns_path}", flush=True)
    print(f"Decision saved: {decision_path}", flush=True)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# data/ml/raw/*.csv
#        ↓ lecture seule
# backend/scripts/ml/train_1x2_v13_double_chance_selective.py
#        ↓ génération de preuves uniquement
# reports/evidence/ml_training/187 à 192
#
# Aucune communication avec PostgreSQL, ml.features, models/, API, frontend ou scoring explicable V1.
