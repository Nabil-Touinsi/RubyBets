# Rôle du fichier : tester V14 Over/Under 2.5 en stratégie selective, à partir des scores réels et des cotes O/U 2.5 disponibles dans les CSV historiques.

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


TARGET_COLUMN = "target_over_under_25"
OVER_LABEL = "OVER_2_5"
UNDER_LABEL = "UNDER_2_5"
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

OUTPUT_SUMMARY = "208_goals_v14_over_under_25_summary.txt"
OUTPUT_RESULTS = "209_goals_v14_over_under_25_results.csv"
OUTPUT_BY_LEAGUE_SEASON = "210_goals_v14_over_under_25_by_league_season.csv"
OUTPUT_BY_MARKET_SIGNAL = "211_goals_v14_over_under_25_by_market_signal.csv"
OUTPUT_ERROR_PATTERNS = "212_goals_v14_over_under_25_error_patterns.csv"
OUTPUT_DECISION = "213_goals_v14_over_under_25_decision.txt"

VALIDATION_SEASON = "2021_2022"
TEST_SEASONS = ["2022_2023", "2023_2024", "2024_2025"]

STRONG_MIN_ACCURACY = 0.70
STRONG_MIN_COVERAGE = 0.45
STRONG_MIN_SELECTED_ROWS = 2400
REVIEW_MIN_ACCURACY = 0.62
REVIEW_MIN_COVERAGE = 0.45
REVIEW_MIN_SELECTED_ROWS = 2000
EXPERIMENTAL_MIN_ACCURACY = 0.60
EXPERIMENTAL_MIN_COVERAGE = 0.30
MIN_MAJOR_SEGMENT_ROWS = 80
MIN_MAJOR_SEGMENT_ACCURACY = 0.60

FAVORITE_PROBABILITY_THRESHOLDS = [0.52, 0.54, 0.56, 0.58, 0.60, 0.62, 0.64, 0.66, 0.68, 0.70]
MARGIN_THRESHOLDS = [0.00, 0.04, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18]
MAX_ENTROPY_THRESHOLDS = [0.60, 0.65, 0.69]
MIN_AVAILABLE_PAIR_THRESHOLDS = [1, 3, 5]
MIN_AGREEMENT_THRESHOLDS = [0.00, 0.60, 0.75, 1.00]

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


@dataclass(frozen=True)
class CsvFileInfo:
    path: Path
    league_code: str
    season: str


@dataclass(frozen=True)
class OddsPair:
    bookmaker_prefix: str
    over_col: str
    under_col: str

    @property
    def key(self) -> str:
        return f"OVER_UNDER_2_5_{self.bookmaker_prefix}"


@dataclass(frozen=True)
class V14Policy:
    favorite_probability_threshold: float
    margin_threshold: float
    max_entropy_threshold: float
    min_available_pairs: int
    min_agreement_threshold: float

    @property
    def name(self) -> str:
        return (
            "v14_ou25"
            f"_fp{self.favorite_probability_threshold:.2f}"
            f"_m{self.margin_threshold:.2f}"
            f"_ent{self.max_entropy_threshold:.2f}"
            f"_pairs{self.min_available_pairs}"
            f"_agr{self.min_agreement_threshold:.2f}"
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


# Détecte les paires Over/Under 2.5 dans les colonnes Football-Data.
def detect_over_under_25_pairs(columns: Iterable[str]) -> list[OddsPair]:
    column_set = {str(column).strip().replace("\ufeff", "") for column in columns}
    pairs: dict[str, OddsPair] = {}

    for column in column_set:
        if ">2.5" not in column:
            continue
        prefix = column.split(">2.5", 1)[0]
        under_col = f"{prefix}<2.5"
        if under_col in column_set:
            pairs[prefix] = OddsPair(bookmaker_prefix=prefix, over_col=column, under_col=under_col)

    return sorted(pairs.values(), key=lambda pair: pair.key)


# Prépare un fichier CSV brut en ajoutant des métadonnées sans modifier le fichier original.
def prepare_raw_frame(file_info: CsvFileInfo) -> pd.DataFrame:
    frame = read_csv_safely(file_info.path)
    frame.columns = clean_columns(frame.columns)
    frame["source_file"] = file_info.path.name
    frame["league_code"] = file_info.league_code
    frame["season"] = file_info.season
    frame["season_start_year"] = season_start_year(file_info.season)
    return frame


# Calcule les probabilités implicites normalisées pour une paire Over/Under.
def calculate_pair_probability(frame: pd.DataFrame, pair: OddsPair) -> pd.Series:
    over_odds = numeric_series(frame, pair.over_col)
    under_odds = numeric_series(frame, pair.under_col)
    valid = (over_odds > 1.0) & (under_odds > 1.0)

    implied_over = 1.0 / over_odds
    implied_under = 1.0 / under_odds
    denominator = implied_over + implied_under
    probability = implied_over / denominator
    return probability.where(valid)


# Construit le dataset V14 à partir d'un fichier CSV brut.
def build_single_file_dataset(file_info: CsvFileInfo) -> pd.DataFrame:
    frame = prepare_raw_frame(file_info)
    pairs = detect_over_under_25_pairs(frame.columns)
    if not pairs:
        return pd.DataFrame()

    home_goals = numeric_series(frame, "FTHG")
    away_goals = numeric_series(frame, "FTAG")
    valid_score = home_goals.notna() & away_goals.notna() & (home_goals >= 0) & (away_goals >= 0)
    total_goals = home_goals + away_goals

    probability_columns: list[pd.Series] = []
    for pair in pairs:
        probability_columns.append(calculate_pair_probability(frame, pair).rename(pair.key))

    probabilities = pd.concat(probability_columns, axis=1)
    available_pairs = probabilities.notna().sum(axis=1)
    over_probability = probabilities.mean(axis=1, skipna=True)
    under_probability = 1.0 - over_probability

    favorite_probability = pd.concat([over_probability, under_probability], axis=1).max(axis=1)
    market_margin = (over_probability - under_probability).abs()
    entropy = -(
        over_probability.clip(0.000001, 0.999999) * np.log(over_probability.clip(0.000001, 0.999999))
        + under_probability.clip(0.000001, 0.999999) * np.log(under_probability.clip(0.000001, 0.999999))
    )

    favorite = np.where(over_probability >= 0.5, OVER_LABEL, UNDER_LABEL)
    agreement_values: list[float] = []
    for index, row in probabilities.iterrows():
        values = row.dropna().to_numpy(dtype="float64")
        if len(values) == 0:
            agreement_values.append(0.0)
            continue
        pair_choices = np.where(values >= 0.5, OVER_LABEL, UNDER_LABEL)
        agreement_values.append(float(np.mean(pair_choices == favorite[index])))

    output = pd.DataFrame(
        {
            "source_file": frame["source_file"],
            "league_code": frame["league_code"],
            "season": frame["season"],
            "season_start_year": frame["season_start_year"],
            "match_date": frame["Date"] if "Date" in frame.columns else "",
            "home_team": frame["HomeTeam"] if "HomeTeam" in frame.columns else "",
            "away_team": frame["AwayTeam"] if "AwayTeam" in frame.columns else "",
            "home_goals": home_goals,
            "away_goals": away_goals,
            "total_goals": total_goals,
            TARGET_COLUMN: np.where(total_goals >= 3, OVER_LABEL, UNDER_LABEL),
            "ou25_market_over_probability": over_probability,
            "ou25_market_under_probability": under_probability,
            "ou25_market_recommendation": favorite,
            "ou25_market_favorite_probability": favorite_probability,
            "ou25_market_margin": market_margin,
            "ou25_market_entropy": entropy,
            "ou25_available_pairs": available_pairs,
            "ou25_bookmaker_agreement_score": agreement_values,
        }
    )

    return output[valid_score & (available_pairs > 0)].copy()


# Construit le dataset V14 complet depuis tous les CSV bruts.
def build_v14_dataset(project_root: Path) -> tuple[pd.DataFrame, list[CsvFileInfo]]:
    files = list_raw_csv_files(project_root)
    datasets: list[pd.DataFrame] = []

    for file_info in files:
        dataset = build_single_file_dataset(file_info)
        if not dataset.empty:
            datasets.append(dataset)

    if not datasets:
        raise RuntimeError("Aucune donnée O/U 2.5 exploitable n'a été trouvée.")

    full_dataset = pd.concat(datasets, ignore_index=True)
    full_dataset = full_dataset.sort_values(["season_start_year", "league_code", "match_date", "home_team", "away_team"]).reset_index(drop=True)
    return full_dataset, files


# Crée toutes les politiques V14 à tester sur validation.
def build_policies() -> list[V14Policy]:
    policies: list[V14Policy] = []
    for favorite_probability in FAVORITE_PROBABILITY_THRESHOLDS:
        for margin in MARGIN_THRESHOLDS:
            for max_entropy in MAX_ENTROPY_THRESHOLDS:
                for min_pairs in MIN_AVAILABLE_PAIR_THRESHOLDS:
                    for min_agreement in MIN_AGREEMENT_THRESHOLDS:
                        policies.append(
                            V14Policy(
                                favorite_probability_threshold=favorite_probability,
                                margin_threshold=margin,
                                max_entropy_threshold=max_entropy,
                                min_available_pairs=min_pairs,
                                min_agreement_threshold=min_agreement,
                            )
                        )
    return policies


# Applique une politique selective V14 sur un DataFrame.
def apply_policy(dataframe: pd.DataFrame, policy: V14Policy) -> pd.DataFrame:
    output = dataframe.copy()
    numeric_columns = [
        "ou25_market_favorite_probability",
        "ou25_market_margin",
        "ou25_market_entropy",
        "ou25_available_pairs",
        "ou25_bookmaker_agreement_score",
    ]
    for column in numeric_columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0.0)

    selected_mask = (
        (output["ou25_market_favorite_probability"] >= policy.favorite_probability_threshold)
        & (output["ou25_market_margin"] >= policy.margin_threshold)
        & (output["ou25_market_entropy"] <= policy.max_entropy_threshold)
        & (output["ou25_available_pairs"] >= policy.min_available_pairs)
        & (output["ou25_bookmaker_agreement_score"] >= policy.min_agreement_threshold)
    )

    output["v14_strategy"] = policy.name
    output["v14_recommendation_status"] = np.where(selected_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v14_recommendation"] = np.where(selected_mask, output["ou25_market_recommendation"], "ABSTAIN")
    output["v14_is_correct"] = (output[TARGET_COLUMN].astype(str) == output["v14_recommendation"].astype(str)) & selected_mask
    output["v14_signal_strength"] = pd.cut(
        output["ou25_market_favorite_probability"],
        bins=[0.0, 0.56, 0.62, 0.70, 1.0],
        labels=["LOW_SIGNAL", "MEDIUM_SIGNAL", "HIGH_SIGNAL", "VERY_HIGH_SIGNAL"],
        include_lowest=True,
    ).astype(str)
    return output


# Calcule les métriques principales d'une politique.
def evaluate_policy(dataframe: pd.DataFrame, policy: V14Policy, split_name: str) -> dict[str, object]:
    predictions = apply_policy(dataframe, policy)
    selected = predictions[predictions["v14_recommendation_status"] == RECOMMEND_STATUS]
    selected_rows = len(selected)
    total_rows = len(predictions)
    accuracy = safe_rate(int(selected["v14_is_correct"].sum()), selected_rows)
    coverage = safe_rate(selected_rows, total_rows)

    return {
        "strategy": policy.name,
        "split": split_name,
        "accuracy": rounded(accuracy),
        "coverage": rounded(coverage),
        "abstention_rate": rounded(1.0 - coverage),
        "selected_rows": selected_rows,
        "total_rows": total_rows,
        "over_rows": int((selected["v14_recommendation"] == OVER_LABEL).sum()),
        "under_rows": int((selected["v14_recommendation"] == UNDER_LABEL).sum()),
        "favorite_probability_threshold": policy.favorite_probability_threshold,
        "margin_threshold": policy.margin_threshold,
        "max_entropy_threshold": policy.max_entropy_threshold,
        "min_available_pairs": policy.min_available_pairs,
        "min_agreement_threshold": policy.min_agreement_threshold,
    }


# Sélectionne la meilleure stratégie sur la saison de validation.
def select_best_policy(validation: pd.DataFrame, policies: list[V14Policy]) -> tuple[V14Policy, pd.DataFrame]:
    rows = [evaluate_policy(validation, policy, "validation") for policy in policies]
    results = pd.DataFrame(rows)

    candidates = results[(results["coverage"] >= REVIEW_MIN_COVERAGE) & (results["selected_rows"] >= 800)].copy()
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

    raise RuntimeError("Impossible de retrouver la meilleure politique V14 sélectionnée.")


# Construit les métriques par ligue et saison sur le test final.
def build_by_league_season(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v14_recommendation_status"] == RECOMMEND_STATUS].copy()
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
                "accuracy": rounded(safe_rate(int(group["v14_is_correct"].sum()), len(group))),
                "over_rows": int((group["v14_recommendation"] == OVER_LABEL).sum()),
                "under_rows": int((group["v14_recommendation"] == UNDER_LABEL).sum()),
                "avg_favorite_probability": rounded(group["ou25_market_favorite_probability"].mean()),
                "is_major_segment": len(group) >= MIN_MAJOR_SEGMENT_ROWS,
            }
        )

    return pd.DataFrame(rows).sort_values(["accuracy", "selected_rows"], ascending=[True, False])


# Construit les métriques par recommandation et force de signal.
def build_by_market_signal(final_predictions: pd.DataFrame) -> pd.DataFrame:
    selected = final_predictions[final_predictions["v14_recommendation_status"] == RECOMMEND_STATUS].copy()
    if selected.empty:
        return pd.DataFrame()

    grouped = selected.groupby(["v14_recommendation", "v14_signal_strength"], dropna=False)
    rows: list[dict[str, object]] = []
    for (recommendation, signal_strength), group in grouped:
        rows.append(
            {
                "recommendation": recommendation,
                "signal_strength": signal_strength,
                "selected_rows": len(group),
                "accuracy": rounded(safe_rate(int(group["v14_is_correct"].sum()), len(group))),
                "avg_over_probability": rounded(group["ou25_market_over_probability"].mean()),
                "avg_under_probability": rounded(group["ou25_market_under_probability"].mean()),
                "avg_favorite_probability": rounded(group["ou25_market_favorite_probability"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values(["recommendation", "signal_strength"])


# Construit un extrait des erreurs restantes sur le test final.
def build_error_patterns(final_predictions: pd.DataFrame) -> pd.DataFrame:
    errors = final_predictions[
        (final_predictions["v14_recommendation_status"] == RECOMMEND_STATUS)
        & (~final_predictions["v14_is_correct"])
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
        "v14_recommendation",
        "ou25_market_over_probability",
        "ou25_market_under_probability",
        "ou25_market_favorite_probability",
        "ou25_market_margin",
        "ou25_available_pairs",
        "ou25_bookmaker_agreement_score",
    ]
    return errors[keep_columns].sort_values(["season", "league_code", "match_date"]).head(500)


# Détermine le statut V14 selon les résultats de test final.
def determine_status(metrics: dict[str, object], by_league_season: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    accuracy = float(metrics.get("accuracy", 0.0))
    coverage = float(metrics.get("coverage", 0.0))
    selected_rows = int(metrics.get("selected_rows", 0))

    major_fragile_segments = 0
    if not by_league_season.empty:
        major_segments = by_league_season[by_league_season["is_major_segment"] == True]  # noqa: E712 - lisible pour DataFrame
        major_fragile_segments = len(major_segments[major_segments["accuracy"] < MIN_MAJOR_SEGMENT_ACCURACY])

    blocking_reasons: list[str] = []
    warnings_list: list[str] = []

    if major_fragile_segments > 0:
        warnings_list.append(f"{major_fragile_segments} segment(s) ligue/saison majeur(s) sous {MIN_MAJOR_SEGMENT_ACCURACY}.")

    if accuracy >= STRONG_MIN_ACCURACY and coverage >= STRONG_MIN_COVERAGE and selected_rows >= STRONG_MIN_SELECTED_ROWS:
        if major_fragile_segments == 0:
            return "V14_OVER_UNDER_25_STRONG_REVIEW", blocking_reasons, warnings_list
        return "V14_OVER_UNDER_25_REVIEW_WITH_SEGMENT_WARNINGS", blocking_reasons, warnings_list

    if accuracy >= REVIEW_MIN_ACCURACY and coverage >= REVIEW_MIN_COVERAGE and selected_rows >= REVIEW_MIN_SELECTED_ROWS:
        warnings_list.append("Le marché O/U 2.5 est exploitable mais reste sous le gate fort de 0.70 d'accuracy.")
        return "V14_OVER_UNDER_25_REVIEW", blocking_reasons, warnings_list

    if accuracy >= EXPERIMENTAL_MIN_ACCURACY and coverage >= EXPERIMENTAL_MIN_COVERAGE:
        warnings_list.append("Le signal est exploitable comme expérience, mais trop faible pour une validation forte.")
        return "V14_OVER_UNDER_25_EXPERIMENTAL_ONLY", blocking_reasons, warnings_list

    blocking_reasons.append("Accuracy ou couverture insuffisante pour conserver V14 comme candidat fiable.")
    return "V14_OVER_UNDER_25_REJECTED", blocking_reasons, warnings_list


# Écrit la synthèse texte V14.
def write_summary(
    evidence_dir: Path,
    dataset: pd.DataFrame,
    files: list[CsvFileInfo],
    best_policy: V14Policy,
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
        "RubyBets - ML Goals V14 Over/Under 2.5 selective",
        "208 - Synthèse expérience V14",
        "",
        "Objectif :",
        "Tester une stratégie selective sur le marché Over/Under 2.5 à partir des scores réels et des cotes de marché disponibles.",
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
        f"- Lignes dataset V14 O/U 2.5 : {len(dataset)}",
        f"- Ligues : {', '.join(leagues)}",
        f"- Saisons : {min(seasons)} -> {max(seasons)}",
        f"- Validation seasons : {VALIDATION_SEASON}",
        f"- Test seasons : {', '.join(TEST_SEASONS)}",
        "",
        "Meilleure stratégie V14 sélectionnée sur validation :",
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
        f"- OVER_2_5 rows : {over_rows}",
        f"- UNDER_2_5 rows : {under_rows}",
        f"- OVER_2_5 share : {rounded(safe_rate(over_rows, selected_rows))}",
        f"- UNDER_2_5 share : {rounded(safe_rate(under_rows, selected_rows))}",
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
        "Ne pas intégrer V14 au produit à ce stade. V14 reste une expérimentation goals/market distincte ; le scoring explicable V1 reste le socle officiel.",
        "",
        "Statut de suivi :",
        "- Audit colonnes Over/Under et BTTS : réalisé.",
        "- V14 Over/Under 2.5 selective : réalisée si les fichiers 208 à 213 sont générés.",
        "- Prochaine étape selon résultat : stabilité dédiée si V14 passe les gates, sinon documenter la limite et passer à V15/V16 labels-only.",
    ]
    (evidence_dir / OUTPUT_SUMMARY).write_text("\n".join(lines), encoding="utf-8")


# Écrit la décision opérationnelle V14.
def write_decision(
    evidence_dir: Path,
    best_policy: V14Policy,
    test_metrics: dict[str, object],
    status: str,
    blocking_reasons: list[str],
    warnings_list: list[str],
) -> None:
    lines = [
        "RubyBets - Décision V14 Over/Under 2.5 selective",
        "213 - Décision expérience V14",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_policy.name}",
        f"- Accuracy : {test_metrics.get('accuracy')}",
        f"- Coverage : {test_metrics.get('coverage')}",
        f"- Abstention rate : {test_metrics.get('abstention_rate')}",
        f"- Selected rows : {test_metrics.get('selected_rows')}",
        f"- OVER_2_5 rows : {test_metrics.get('over_rows')}",
        f"- UNDER_2_5 rows : {test_metrics.get('under_rows')}",
        "",
        "Gates appliqués :",
        f"- Strong accuracy >= {STRONG_MIN_ACCURACY}",
        f"- Strong coverage >= {STRONG_MIN_COVERAGE}",
        f"- Strong selected rows >= {STRONG_MIN_SELECTED_ROWS}",
        f"- Review accuracy >= {REVIEW_MIN_ACCURACY}",
        f"- Review coverage >= {REVIEW_MIN_COVERAGE}",
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
                "- V14 peut être conservée comme expérimentation forte sur Over/Under 2.5.",
                "- Une analyse de stabilité dédiée est justifiée avant toute comparaison multi-marchés.",
            ]
        )
    elif "REVIEW" in status:
        lines.extend(
            [
                "- V14 peut être conservée en REVIEW comme expérimentation utile mais pas encore assez forte pour être candidate produit.",
                "- La comparaison avec V15/V16 reste nécessaire avant de construire le sélecteur multi-marchés V17.",
            ]
        )
    elif "EXPERIMENTAL" in status:
        lines.extend(
            [
                "- V14 doit rester documentée comme expérimentation limitée.",
                "- Ne pas la promouvoir comme marché fiable tant qu'une meilleure stratégie n'est pas trouvée.",
            ]
        )
    else:
        lines.extend(
            [
                "- V14 est rejetée comme candidat fiable dans son état actuel.",
                "- Conserver les fichiers comme preuve de test et passer à une autre stratégie ou à V15/V16.",
            ]
        )

    lines.extend(
        [
            "- V14 ne remplace pas V13.1 mixed selective.",
            "- V14 ne remplace pas le scoring explicable V1.",
            "",
            "Statut de suivi à mettre à jour :",
            "- V14 Over/Under 2.5 selective : réalisée.",
            "- Fichiers concernés : 208, 209, 210, 211, 212, 213.",
        ]
    )
    (evidence_dir / OUTPUT_DECISION).write_text("\n".join(lines), encoding="utf-8")


# Orchestre l'expérience V14 et génère les preuves 208 à 213.
def main() -> None:
    print("Chargement des CSV bruts et construction du dataset V14 Over/Under 2.5...")
    project_root = find_project_root()
    evidence_dir = get_evidence_dir(project_root)
    dataset, files = build_v14_dataset(project_root)

    validation = dataset[dataset["season"] == VALIDATION_SEASON].copy()
    test = dataset[dataset["season"].isin(TEST_SEASONS)].copy()
    if validation.empty or test.empty:
        raise RuntimeError("Split temporel V14 impossible : validation ou test vide.")

    print("Recherche de la meilleure stratégie selective V14 sur validation...")
    policies = build_policies()
    best_policy, validation_results = select_best_policy(validation, policies)
    validation_metrics = evaluate_policy(validation, best_policy, "validation")
    test_metrics = evaluate_policy(test, best_policy, "test")

    print("Application de la meilleure stratégie V14 sur test final...")
    final_predictions = apply_policy(test, best_policy)
    by_league_season = build_by_league_season(final_predictions)
    by_market_signal = build_by_market_signal(final_predictions)
    error_patterns = build_error_patterns(final_predictions)
    status, blocking_reasons, warnings_list = determine_status(test_metrics, by_league_season)

    combined_results = pd.concat([validation_results, pd.DataFrame([test_metrics])], ignore_index=True)
    combined_results.to_csv(evidence_dir / OUTPUT_RESULTS, index=False, encoding="utf-8-sig")
    by_league_season.to_csv(evidence_dir / OUTPUT_BY_LEAGUE_SEASON, index=False, encoding="utf-8-sig")
    by_market_signal.to_csv(evidence_dir / OUTPUT_BY_MARKET_SIGNAL, index=False, encoding="utf-8-sig")
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

    print("OK - Expérience V14 Over/Under 2.5 selective terminée.")
    print(f"Status: {status}")
    print(f"Strategy: {best_policy.name}")
    print(f"Test accuracy: {test_metrics.get('accuracy')}")
    print(f"Test coverage: {test_metrics.get('coverage')}")
    print(f"Test abstention rate: {test_metrics.get('abstention_rate')}")
    print(f"Selected rows: {test_metrics.get('selected_rows')}")
    print(f"OVER_2_5 rows: {test_metrics.get('over_rows')}")
    print(f"UNDER_2_5 rows: {test_metrics.get('under_rows')}")
    print(f"Summary saved: {evidence_dir / OUTPUT_SUMMARY}")
    print(f"Results CSV saved: {evidence_dir / OUTPUT_RESULTS}")
    print(f"By league/season CSV saved: {evidence_dir / OUTPUT_BY_LEAGUE_SEASON}")
    print(f"By market/signal CSV saved: {evidence_dir / OUTPUT_BY_MARKET_SIGNAL}")
    print(f"Error patterns CSV saved: {evidence_dir / OUTPUT_ERROR_PATTERNS}")
    print(f"Decision saved: {evidence_dir / OUTPUT_DECISION}")


if __name__ == "__main__":
    main()


# Schéma de communication :
# data/ml/raw/*.csv -> train_goals_v14_over_under_25_selective.py -> reports/evidence/ml_training/208-213
# Ce script lit uniquement les CSV bruts et écrit uniquement des preuves d'expérimentation ML.
