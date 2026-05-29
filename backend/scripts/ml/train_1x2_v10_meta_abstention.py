# Rôle du fichier : tester une V10 ML 1X2 sous forme de méta-couche KEEP/ABSTAIN au-dessus de V6/V9, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

V9_RESULTS_CSV = EVIDENCE_DIR / "146_1x2_v9_selective_calibration_abstention_results.csv"
V9_BEST_PREDICTIONS_CSV = EVIDENCE_DIR / "147_1x2_v9_selective_calibration_abstention_best_predictions.csv"

SUMMARY_TXT = EVIDENCE_DIR / "157_1x2_v10_meta_abstention_summary.txt"
RESULTS_CSV = EVIDENCE_DIR / "158_1x2_v10_meta_abstention_results.csv"
BEST_STRATEGY_CSV = EVIDENCE_DIR / "159_1x2_v10_meta_abstention_best_strategy.csv"
BY_CLASS_CSV = EVIDENCE_DIR / "160_1x2_v10_meta_abstention_by_class.csv"
BY_LEAGUE_SEASON_CSV = EVIDENCE_DIR / "161_1x2_v10_meta_abstention_by_league_season.csv"
ERROR_PATTERNS_CSV = EVIDENCE_DIR / "162_1x2_v10_meta_abstention_error_patterns.csv"
DECISION_TXT = EVIDENCE_DIR / "163_1x2_v10_meta_abstention_decision.txt"

sys.path.append(str(SCRIPT_DIR))

warnings.filterwarnings("ignore", category=UserWarning)

TARGET_COLUMN = "target_result"
TARGET_CLASSES = ["HOME_WIN", "DRAW", "AWAY_WIN"]
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

V10_MODEL_NAMES = ["v10_logistic_balanced", "v10_random_forest_balanced"]
KEEP_PROBABILITY_THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
MIN_MARGIN_THRESHOLDS = [0.00, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]
DRAW_POLICIES = ["exclude_draw", "allow_draw_if_strong"]

META_TRAIN_RATIO = 0.60
MIN_VALIDATION_COVERAGE = 0.10
MIN_VALIDATION_SELECTED_ROWS = 80
MIN_TEST_COVERAGE_FOR_REVIEW = 0.10
MIN_TEST_ACCURACY_FOR_REVIEW = 0.75
TARGET_TEST_ACCURACY = 0.78
TARGET_TEST_COVERAGE = 0.15
STATIC_V9_REFERENCE_ACCURACY = 0.7874
STATIC_V9_REFERENCE_COVERAGE = 0.1492
STATIC_V9_REFERENCE_SELECTED_ROWS = 795

BASE_NUMERIC_FEATURES = [
    "market_home_prob",
    "market_draw_prob",
    "market_away_prob",
    "market_favorite_prob",
    "market_second_prob",
    "market_confidence_gap",
    "market_home_away_gap",
    "market_abs_home_away_gap",
    "market_draw_gap",
    "sigmoid_max_probability",
    "sigmoid_second_probability",
    "sigmoid_margin",
    "sigmoid_prob_HOME_WIN",
    "sigmoid_prob_DRAW",
    "sigmoid_prob_AWAY_WIN",
    "raw_v6_reference_max_probability",
    "raw_v6_reference_margin",
    "raw_v6_reference_prob_HOME_WIN",
    "raw_v6_reference_prob_DRAW",
    "raw_v6_reference_prob_AWAY_WIN",
    "v10_raw_entropy",
    "v10_sigmoid_entropy",
    "v10_raw_home_away_gap",
    "v10_sigmoid_home_away_gap",
]

BASE_CATEGORICAL_FEATURES = [
    "league_code",
    "raw_v6_reference_predicted_class",
    "sigmoid_predicted_class",
]


@dataclass(frozen=True)
class V10Policy:
    model_name: str
    keep_probability_threshold: float
    min_margin_threshold: float
    draw_policy: str

    @property
    def name(self) -> str:
        return (
            f"{self.model_name}"
            f"_keep{self.keep_probability_threshold:.2f}"
            f"_margin{self.min_margin_threshold:.2f}"
            f"_{self.draw_policy}"
        ).replace(".", "")


# Arrondit une valeur numérique pour stabiliser les fichiers de preuve.
def rounded(value: object, digits: int = 4) -> float:
    try:
        result = float(value)
        if math.isnan(result):
            return 0.0
        return round(result, digits)
    except (TypeError, ValueError):
        return 0.0


# Convertit une colonne lue depuis CSV en booléen exploitable.
def normalize_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin(["true", "1", "yes", "y"])


# Calcule un ratio en évitant les divisions par zéro.
def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# Produit une entropie simple à partir des trois probabilités 1X2.
def compute_entropy(dataframe: pd.DataFrame, probability_columns: list[str]) -> pd.Series:
    probabilities = dataframe[probability_columns].copy()
    probabilities = probabilities.apply(pd.to_numeric, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    return -(probabilities * np.log(probabilities.replace(0.0, np.nan))).sum(axis=1).fillna(0.0)


# Vérifie les colonnes minimales nécessaires à une expérience V10 depuis un DataFrame de prédictions.
def validate_prediction_columns(dataframe: pd.DataFrame) -> None:
    required_columns = [
        "clean_match_id",
        "season",
        TARGET_COLUMN,
        "raw_v6_reference_predicted_class",
        "raw_v6_reference_is_correct",
        "raw_v6_reference_prob_HOME_WIN",
        "raw_v6_reference_prob_DRAW",
        "raw_v6_reference_prob_AWAY_WIN",
        "raw_v6_reference_margin",
        "sigmoid_predicted_class",
        "sigmoid_max_probability",
        "sigmoid_prob_HOME_WIN",
        "sigmoid_prob_DRAW",
        "sigmoid_prob_AWAY_WIN",
        "sigmoid_margin",
    ]
    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes pour V10 meta-abstention : {missing_columns}")


# Ajoute les colonnes dérivées utiles au méta-modèle V10.
def add_v10_meta_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    validate_prediction_columns(dataframe)
    output = dataframe.copy()

    if "league_code" not in output.columns:
        output["league_code"] = "UNKNOWN"

    output["league_code"] = output["league_code"].fillna("UNKNOWN").astype(str)
    output["season"] = output["season"].fillna("UNKNOWN").astype(str)
    output[TARGET_COLUMN] = output[TARGET_COLUMN].fillna("UNKNOWN").astype(str)
    output["raw_v6_reference_predicted_class"] = output["raw_v6_reference_predicted_class"].fillna("UNKNOWN").astype(str)
    output["sigmoid_predicted_class"] = output["sigmoid_predicted_class"].fillna("UNKNOWN").astype(str)
    output["raw_v6_reference_is_correct"] = normalize_bool_series(output["raw_v6_reference_is_correct"])

    if "v9_is_correct" in output.columns:
        output["v9_is_correct"] = normalize_bool_series(output["v9_is_correct"])
    else:
        output["v9_is_correct"] = False

    if "v9_recommendation_status" not in output.columns:
        output["v9_recommendation_status"] = ABSTAIN_STATUS

    numeric_candidates = [column for column in BASE_NUMERIC_FEATURES if column in output.columns]
    for column in numeric_candidates:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0.0)

    raw_probability_columns = [
        "raw_v6_reference_prob_HOME_WIN",
        "raw_v6_reference_prob_DRAW",
        "raw_v6_reference_prob_AWAY_WIN",
    ]
    sigmoid_probability_columns = [
        "sigmoid_prob_HOME_WIN",
        "sigmoid_prob_DRAW",
        "sigmoid_prob_AWAY_WIN",
    ]

    output["v10_raw_entropy"] = compute_entropy(output, raw_probability_columns)
    output["v10_sigmoid_entropy"] = compute_entropy(output, sigmoid_probability_columns)
    output["v10_raw_home_away_gap"] = output["raw_v6_reference_prob_HOME_WIN"] - output["raw_v6_reference_prob_AWAY_WIN"]
    output["v10_sigmoid_home_away_gap"] = output["sigmoid_prob_HOME_WIN"] - output["sigmoid_prob_AWAY_WIN"]
    output["v10_meta_target_correct"] = output["raw_v6_reference_is_correct"].astype(int)

    return output


# Charge la référence V9 existante pour comparer V10 à la même politique sélective.
def load_v9_best_predictions() -> pd.DataFrame:
    if not V9_BEST_PREDICTIONS_CSV.exists():
        raise FileNotFoundError(f"Fichier V9 obligatoire introuvable : {V9_BEST_PREDICTIONS_CSV}")
    return add_v10_meta_features(pd.read_csv(V9_BEST_PREDICTIONS_CSV))


# Tente de reconstruire les prédictions validation/test de manière stricte depuis les fonctions V9 existantes.
def build_prediction_sets_from_database() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    from train_1x2_v9_selective_calibration_abstention import (  # noqa: WPS433
        build_prediction_dataframe,
        build_v9_feature_dataframe,
        get_database_url,
        prepare_temporal_splits,
        train_and_predict_probabilities,
    )

    database_url = get_database_url()
    feature_dataframe, metadata = build_v9_feature_dataframe(database_url)
    train_core_dataframe, validation_dataframe, test_dataframe = prepare_temporal_splits(feature_dataframe)

    sort_columns = [column for column in ["match_date", "clean_match_id"] if column in validation_dataframe.columns]
    validation_sorted = validation_dataframe.sort_values(sort_columns).reset_index(drop=True) if sort_columns else validation_dataframe.reset_index(drop=True)
    split_index = max(1, min(len(validation_sorted) - 1, int(len(validation_sorted) * META_TRAIN_RATIO)))
    meta_train_source = validation_sorted.iloc[:split_index].copy()
    meta_validation_source = validation_sorted.iloc[split_index:].copy()

    print("Reconstruction des prédictions V6/V9 pour meta-train...", flush=True)
    _, raw_meta_train_probabilities = train_and_predict_probabilities("raw", train_core_dataframe, meta_train_source)
    _, sigmoid_meta_train_probabilities = train_and_predict_probabilities("sigmoid", train_core_dataframe, meta_train_source)
    meta_train_predictions = build_prediction_dataframe(
        meta_train_source,
        sigmoid_meta_train_probabilities,
        "sigmoid",
        raw_v6_probabilities=raw_meta_train_probabilities,
    )

    print("Reconstruction des prédictions V6/V9 pour meta-validation...", flush=True)
    _, raw_meta_validation_probabilities = train_and_predict_probabilities("raw", train_core_dataframe, meta_validation_source)
    _, sigmoid_meta_validation_probabilities = train_and_predict_probabilities("sigmoid", train_core_dataframe, meta_validation_source)
    meta_validation_predictions = build_prediction_dataframe(
        meta_validation_source,
        sigmoid_meta_validation_probabilities,
        "sigmoid",
        raw_v6_probabilities=raw_meta_validation_probabilities,
    )

    print("Reconstruction des prédictions V6/V9 pour test final...", flush=True)
    train_plus_validation = pd.concat([train_core_dataframe, validation_dataframe], ignore_index=True)
    _, raw_test_probabilities = train_and_predict_probabilities("raw", train_plus_validation, test_dataframe)
    _, sigmoid_test_probabilities = train_and_predict_probabilities("sigmoid", train_plus_validation, test_dataframe)
    test_predictions = build_prediction_dataframe(
        test_dataframe,
        sigmoid_test_probabilities,
        "sigmoid",
        raw_v6_probabilities=raw_test_probabilities,
    )

    v9_reference = load_v9_best_predictions()
    v9_columns = [
        "clean_match_id",
        "v9_policy",
        "v9_model_variant",
        "v9_recommendation_status",
        "v9_prediction",
        "v9_confidence_probability",
        "v9_margin",
        "v9_is_correct",
        "v9_abstention_reason",
    ]
    v9_columns = [column for column in v9_columns if column in v9_reference.columns]
    test_predictions = test_predictions.drop(columns=[column for column in v9_columns if column in test_predictions.columns and column != "clean_match_id"], errors="ignore")
    test_predictions = test_predictions.merge(v9_reference[v9_columns], on="clean_match_id", how="left")

    split_metadata = {
        "source_mode": "database_rebuild_from_v9_functions",
        "feature_rows": len(feature_dataframe),
        "train_core_rows": len(train_core_dataframe),
        "validation_rows": len(validation_dataframe),
        "meta_train_rows": len(meta_train_predictions),
        "meta_validation_rows": len(meta_validation_predictions),
        "test_rows": len(test_predictions),
    }
    split_metadata.update(metadata)

    return (
        add_v10_meta_features(meta_train_predictions),
        add_v10_meta_features(meta_validation_predictions),
        add_v10_meta_features(test_predictions),
        split_metadata,
    )


# Sépare le CSV V9 existant en meta-train, meta-validation et test si la reconstruction DB échoue.
def build_prediction_sets_from_existing_v9_csv() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    v9_dataframe = load_v9_best_predictions()
    sort_columns = [column for column in ["season", "match_date", "clean_match_id"] if column in v9_dataframe.columns]
    sorted_dataframe = v9_dataframe.sort_values(sort_columns).reset_index(drop=True) if sort_columns else v9_dataframe.reset_index(drop=True)
    seasons = sorted(sorted_dataframe["season"].dropna().astype(str).unique().tolist())

    if len(seasons) >= 3:
        meta_train_dataframe = sorted_dataframe[sorted_dataframe["season"] == seasons[0]].copy()
        meta_validation_dataframe = sorted_dataframe[sorted_dataframe["season"] == seasons[1]].copy()
        test_dataframe = sorted_dataframe[sorted_dataframe["season"].isin(seasons[2:])].copy()
    else:
        first_split = max(1, int(len(sorted_dataframe) * 0.40))
        second_split = max(first_split + 1, int(len(sorted_dataframe) * 0.70))
        meta_train_dataframe = sorted_dataframe.iloc[:first_split].copy()
        meta_validation_dataframe = sorted_dataframe.iloc[first_split:second_split].copy()
        test_dataframe = sorted_dataframe.iloc[second_split:].copy()

    split_metadata = {
        "source_mode": "fallback_existing_v9_csv_temporal_split",
        "feature_rows": len(v9_dataframe),
        "train_core_rows": 0,
        "validation_rows": 0,
        "meta_train_rows": len(meta_train_dataframe),
        "meta_validation_rows": len(meta_validation_dataframe),
        "test_rows": len(test_dataframe),
        "fallback_reason": "database_rebuild_unavailable_or_failed",
    }

    return meta_train_dataframe, meta_validation_dataframe, test_dataframe, split_metadata


# Charge les données V10 en privilégiant une reconstruction stricte, puis en basculant vers les CSV existants si nécessaire.
def load_v10_prediction_sets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    try:
        return build_prediction_sets_from_database()
    except Exception as error:  # noqa: BLE001
        print("Reconstruction DB indisponible. Bascule sur le fichier V9 147 existant.", flush=True)
        print(f"Raison : {error}", flush=True)
        meta_train_dataframe, meta_validation_dataframe, test_dataframe, metadata = build_prediction_sets_from_existing_v9_csv()
        metadata["fallback_error"] = str(error)
        return meta_train_dataframe, meta_validation_dataframe, test_dataframe, metadata


# Construit la matrice de features du méta-modèle avec alignement strict des colonnes.
def build_meta_matrix(dataframe: pd.DataFrame, reference_columns: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    output = dataframe.copy()
    numeric_columns = [column for column in BASE_NUMERIC_FEATURES if column in output.columns]
    categorical_columns = [column for column in BASE_CATEGORICAL_FEATURES if column in output.columns]

    numeric_matrix = output[numeric_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0) if numeric_columns else pd.DataFrame(index=output.index)
    categorical_matrix = pd.get_dummies(output[categorical_columns].fillna("UNKNOWN").astype(str), prefix=categorical_columns) if categorical_columns else pd.DataFrame(index=output.index)
    matrix = pd.concat([numeric_matrix, categorical_matrix], axis=1)

    if reference_columns is None:
        feature_columns = matrix.columns.tolist()
    else:
        feature_columns = reference_columns
        matrix = matrix.reindex(columns=feature_columns, fill_value=0.0)

    return matrix, feature_columns


# Construit un des modèles candidats V10.
def build_v10_model(model_name: str):
    if model_name == "v10_logistic_balanced":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
        )

    if model_name == "v10_random_forest_balanced":
        return RandomForestClassifier(
            n_estimators=300,
            max_depth=6,
            min_samples_leaf=25,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )

    raise RuntimeError(f"Modèle V10 inconnu : {model_name}")


# Entraîne un méta-modèle V10 qui estime la probabilité que V6 ait raison.
def train_meta_model(model_name: str, meta_train_dataframe: pd.DataFrame):
    x_train, feature_columns = build_meta_matrix(meta_train_dataframe)
    y_train = meta_train_dataframe["v10_meta_target_correct"].astype(int)

    if y_train.nunique() < 2:
        raise RuntimeError("La cible V10 ne contient pas deux classes. Impossible d'entraîner le méta-modèle.")

    model = build_v10_model(model_name)
    model.fit(x_train, y_train)
    return model, feature_columns


# Ajoute la probabilité KEEP produite par le méta-modèle V10.
def add_keep_probability(dataframe: pd.DataFrame, model, feature_columns: list[str], model_name: str) -> pd.DataFrame:
    output = dataframe.copy()
    x_predict, _ = build_meta_matrix(output, reference_columns=feature_columns)
    probabilities = model.predict_proba(x_predict)
    class_labels = list(model.classes_)

    if 1 in class_labels:
        keep_probability = probabilities[:, class_labels.index(1)]
    else:
        keep_probability = np.zeros(len(output))

    output[f"{model_name}_keep_probability"] = keep_probability
    return output


# Génère toutes les politiques KEEP/ABSTAIN à tester pour un modèle V10 donné.
def build_v10_policies(model_name: str) -> list[V10Policy]:
    return [
        V10Policy(
            model_name=model_name,
            keep_probability_threshold=threshold,
            min_margin_threshold=margin,
            draw_policy=draw_policy,
        )
        for threshold in KEEP_PROBABILITY_THRESHOLDS
        for margin in MIN_MARGIN_THRESHOLDS
        for draw_policy in DRAW_POLICIES
    ]


# Applique une politique V10 et produit les colonnes de recommandation/abstention.
def apply_v10_policy(dataframe: pd.DataFrame, policy: V10Policy) -> pd.DataFrame:
    output = dataframe.copy()
    keep_column = f"{policy.model_name}_keep_probability"
    raw_prediction_column = "raw_v6_reference_predicted_class"

    output[keep_column] = pd.to_numeric(output[keep_column], errors="coerce").fillna(0.0)
    output["raw_v6_reference_margin"] = pd.to_numeric(output["raw_v6_reference_margin"], errors="coerce").fillna(0.0)
    output["raw_v6_reference_prob_DRAW"] = pd.to_numeric(output["raw_v6_reference_prob_DRAW"], errors="coerce").fillna(0.0)

    base_keep_mask = (
        (output[keep_column] >= policy.keep_probability_threshold)
        & (output["raw_v6_reference_margin"] >= policy.min_margin_threshold)
    )

    if policy.draw_policy == "exclude_draw":
        draw_mask = output[raw_prediction_column] != "DRAW"
    elif policy.draw_policy == "allow_draw_if_strong":
        draw_mask = (
            (output[raw_prediction_column] != "DRAW")
            | (
                (output[raw_prediction_column] == "DRAW")
                & (output["raw_v6_reference_prob_DRAW"] >= 0.35)
                & (output[keep_column] >= max(policy.keep_probability_threshold, 0.75))
            )
        )
    else:
        raise RuntimeError(f"Politique DRAW inconnue : {policy.draw_policy}")

    recommend_mask = base_keep_mask & draw_mask

    output["v10_policy"] = policy.name
    output["v10_model_name"] = policy.model_name
    output["v10_recommendation_status"] = np.where(recommend_mask, RECOMMEND_STATUS, ABSTAIN_STATUS)
    output["v10_prediction"] = np.where(recommend_mask, output[raw_prediction_column], ABSTAIN_STATUS)
    output["v10_keep_probability"] = output[keep_column]
    output["v10_margin"] = output["raw_v6_reference_margin"]
    output["v10_is_correct"] = output[TARGET_COLUMN] == output["v10_prediction"]

    output["v10_abstention_reason"] = "accepted"
    output.loc[~base_keep_mask, "v10_abstention_reason"] = "low_meta_probability_or_margin"
    output.loc[base_keep_mask & ~draw_mask, "v10_abstention_reason"] = "draw_not_allowed_or_not_strong_enough"

    return output


# Calcule les métriques de référence V9 sur le même périmètre.
def compute_v9_reference_metrics(dataframe: pd.DataFrame) -> dict:
    if "v9_recommendation_status" not in dataframe.columns:
        return {
            "v9_selected_rows": 0,
            "v9_coverage": 0.0,
            "v9_selected_accuracy": 0.0,
            "v9_correct_rows": 0,
        }

    v9_selected = dataframe[dataframe["v9_recommendation_status"] == RECOMMEND_STATUS].copy()
    selected_rows = int(len(v9_selected))
    correct_rows = int(normalize_bool_series(v9_selected.get("v9_is_correct", pd.Series(dtype=bool))).sum()) if selected_rows else 0

    return {
        "v9_selected_rows": selected_rows,
        "v9_coverage": rounded(safe_rate(selected_rows, len(dataframe))),
        "v9_selected_accuracy": rounded(safe_rate(correct_rows, selected_rows)),
        "v9_correct_rows": correct_rows,
    }


# Calcule les métriques d'une politique V10 sur un périmètre donné.
def compute_v10_metrics(policy_dataframe: pd.DataFrame, policy: V10Policy, evaluation_scope: str) -> dict:
    selected_dataframe = policy_dataframe[policy_dataframe["v10_recommendation_status"] == RECOMMEND_STATUS].copy()
    rows = int(len(policy_dataframe))
    selected_rows = int(len(selected_dataframe))
    abstained_rows = rows - selected_rows
    selected_correct_rows = int(selected_dataframe["v10_is_correct"].sum()) if selected_rows else 0
    selected_accuracy = safe_rate(selected_correct_rows, selected_rows)
    v9_reference = compute_v9_reference_metrics(policy_dataframe)

    if selected_rows:
        report = classification_report(
            selected_dataframe[TARGET_COLUMN],
            selected_dataframe["v10_prediction"],
            labels=TARGET_CLASSES,
            output_dict=True,
            zero_division=0,
        )
        selected_f1_macro = f1_score(
            selected_dataframe[TARGET_COLUMN],
            selected_dataframe["v10_prediction"],
            labels=TARGET_CLASSES,
            average="macro",
            zero_division=0,
        )
    else:
        report = {class_name: {"precision": 0.0, "recall": 0.0} for class_name in TARGET_CLASSES}
        selected_f1_macro = 0.0

    prediction_counts = selected_dataframe["v10_prediction"].value_counts().to_dict() if selected_rows else {}
    actual_counts = selected_dataframe[TARGET_COLUMN].value_counts().to_dict() if selected_rows else {}

    return {
        "evaluation_scope": evaluation_scope,
        "strategy": policy.name,
        "model_name": policy.model_name,
        "policy_type": "meta_abstention",
        "draw_policy": policy.draw_policy,
        "keep_probability_threshold": policy.keep_probability_threshold,
        "min_margin_threshold": policy.min_margin_threshold,
        "rows": rows,
        "selected_rows": selected_rows,
        "abstained_rows": abstained_rows,
        "coverage": rounded(safe_rate(selected_rows, rows)),
        "abstention_rate": rounded(safe_rate(abstained_rows, rows)),
        "selected_accuracy": rounded(selected_accuracy),
        "selected_f1_macro": rounded(selected_f1_macro),
        "selected_correct_rows": selected_correct_rows,
        "selected_error_rows": selected_rows - selected_correct_rows,
        "v9_selected_rows_same_scope": v9_reference["v9_selected_rows"],
        "v9_coverage_same_scope": v9_reference["v9_coverage"],
        "v9_selected_accuracy_same_scope": v9_reference["v9_selected_accuracy"],
        "v9_correct_rows_same_scope": v9_reference["v9_correct_rows"],
        "selected_accuracy_delta_vs_v9_scope": rounded(selected_accuracy - v9_reference["v9_selected_accuracy"]),
        "coverage_delta_vs_v9_scope": rounded(safe_rate(selected_rows, rows) - v9_reference["v9_coverage"]),
        "net_correct_delta_vs_v9_total_scope": int(selected_correct_rows - v9_reference["v9_correct_rows"]),
        "home_win_precision": rounded(report["HOME_WIN"]["precision"]),
        "home_win_recall": rounded(report["HOME_WIN"]["recall"]),
        "draw_precision": rounded(report["DRAW"]["precision"]),
        "draw_recall": rounded(report["DRAW"]["recall"]),
        "away_win_precision": rounded(report["AWAY_WIN"]["precision"]),
        "away_win_recall": rounded(report["AWAY_WIN"]["recall"]),
        "predicted_home_win_rows": int(prediction_counts.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(prediction_counts.get("DRAW", 0)),
        "predicted_away_win_rows": int(prediction_counts.get("AWAY_WIN", 0)),
        "actual_home_win_rows": int(actual_counts.get("HOME_WIN", 0)),
        "actual_draw_rows": int(actual_counts.get("DRAW", 0)),
        "actual_away_win_rows": int(actual_counts.get("AWAY_WIN", 0)),
        "avg_keep_probability_selected": rounded(selected_dataframe["v10_keep_probability"].mean() if selected_rows else 0.0),
        "avg_margin_selected": rounded(selected_dataframe["v10_margin"].mean() if selected_rows else 0.0),
    }


# Sélectionne la meilleure stratégie V10 uniquement à partir de la meta-validation.
def select_best_validation_strategy(results_dataframe: pd.DataFrame) -> pd.Series:
    validation_candidates = results_dataframe[
        (results_dataframe["evaluation_scope"] == "meta_validation")
        & (results_dataframe["coverage"] >= MIN_VALIDATION_COVERAGE)
        & (results_dataframe["selected_rows"] >= MIN_VALIDATION_SELECTED_ROWS)
    ].copy()

    if validation_candidates.empty:
        validation_candidates = results_dataframe[results_dataframe["evaluation_scope"] == "meta_validation"].copy()

    if validation_candidates.empty:
        raise RuntimeError("Aucune stratégie V10 disponible en meta-validation.")

    return validation_candidates.sort_values(
        by=[
            "selected_accuracy",
            "net_correct_delta_vs_v9_total_scope",
            "coverage",
            "selected_f1_macro",
        ],
        ascending=[False, False, False, False],
    ).iloc[0]


# Retrouve l'objet politique à partir d'une ligne de résultats.
def policy_from_result_row(result_row: pd.Series) -> V10Policy:
    return V10Policy(
        model_name=str(result_row["model_name"]),
        keep_probability_threshold=float(result_row["keep_probability_threshold"]),
        min_margin_threshold=float(result_row["min_margin_threshold"]),
        draw_policy=str(result_row["draw_policy"]),
    )


# Evalue tous les modèles et politiques V10 sur validation et test.
def evaluate_v10_policies(
    meta_train_dataframe: pd.DataFrame,
    meta_validation_dataframe: pd.DataFrame,
    test_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    all_metrics = []
    policy_outputs = {}

    for model_name in V10_MODEL_NAMES:
        print(f"Entraînement du méta-modèle : {model_name}", flush=True)
        model, feature_columns = train_meta_model(model_name, meta_train_dataframe)
        validation_with_scores = add_keep_probability(meta_validation_dataframe, model, feature_columns, model_name)
        test_with_scores = add_keep_probability(test_dataframe, model, feature_columns, model_name)

        for policy in build_v10_policies(model_name):
            validation_policy_dataframe = apply_v10_policy(validation_with_scores, policy)
            test_policy_dataframe = apply_v10_policy(test_with_scores, policy)
            all_metrics.append(compute_v10_metrics(validation_policy_dataframe, policy, "meta_validation"))
            all_metrics.append(compute_v10_metrics(test_policy_dataframe, policy, "test"))
            policy_outputs[("meta_validation", policy.name)] = validation_policy_dataframe
            policy_outputs[("test", policy.name)] = test_policy_dataframe

    return pd.DataFrame(all_metrics), policy_outputs


# Calcule la stabilité par classe prédite pour la meilleure stratégie V10.
def build_by_class(best_test_dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for predicted_class in TARGET_CLASSES + [ABSTAIN_STATUS]:
        if predicted_class == ABSTAIN_STATUS:
            class_dataframe = best_test_dataframe[best_test_dataframe["v10_recommendation_status"] == ABSTAIN_STATUS].copy()
        else:
            class_dataframe = best_test_dataframe[best_test_dataframe["v10_prediction"] == predicted_class].copy()

        selected_rows = int(len(class_dataframe))
        correct_rows = int(class_dataframe["v10_is_correct"].sum()) if predicted_class != ABSTAIN_STATUS and selected_rows else 0
        actual_counts = class_dataframe[TARGET_COLUMN].value_counts().to_dict() if selected_rows else {}
        rows.append(
            {
                "predicted_class": predicted_class,
                "rows": selected_rows,
                "selected_accuracy": rounded(safe_rate(correct_rows, selected_rows)) if predicted_class != ABSTAIN_STATUS else 0.0,
                "correct_rows": correct_rows,
                "error_rows": selected_rows - correct_rows if predicted_class != ABSTAIN_STATUS else 0,
                "actual_home_win_rows": int(actual_counts.get("HOME_WIN", 0)),
                "actual_draw_rows": int(actual_counts.get("DRAW", 0)),
                "actual_away_win_rows": int(actual_counts.get("AWAY_WIN", 0)),
            }
        )

    return pd.DataFrame(rows)


# Calcule la stabilité par ligue et saison pour la meilleure stratégie V10.
def build_by_league_season(best_test_dataframe: pd.DataFrame) -> pd.DataFrame:
    group_columns = [column for column in ["league_code", "season"] if column in best_test_dataframe.columns]
    if not group_columns:
        return pd.DataFrame()

    rows = []
    for group_values, group_dataframe in best_test_dataframe.groupby(group_columns):
        if not isinstance(group_values, tuple):
            group_values = (group_values,)
        selected_dataframe = group_dataframe[group_dataframe["v10_recommendation_status"] == RECOMMEND_STATUS].copy()
        selected_rows = int(len(selected_dataframe))
        correct_rows = int(selected_dataframe["v10_is_correct"].sum()) if selected_rows else 0
        prediction_counts = selected_dataframe["v10_prediction"].value_counts().to_dict() if selected_rows else {}
        actual_counts = selected_dataframe[TARGET_COLUMN].value_counts().to_dict() if selected_rows else {}
        row = {
            "rows": int(len(group_dataframe)),
            "selected_rows": selected_rows,
            "abstained_rows": int(len(group_dataframe) - selected_rows),
            "coverage": rounded(safe_rate(selected_rows, len(group_dataframe))),
            "abstention_rate": rounded(safe_rate(len(group_dataframe) - selected_rows, len(group_dataframe))),
            "selected_accuracy": rounded(safe_rate(correct_rows, selected_rows)),
            "correct_rows": correct_rows,
            "error_rows": selected_rows - correct_rows,
            "predicted_home_win_rows": int(prediction_counts.get("HOME_WIN", 0)),
            "predicted_draw_rows": int(prediction_counts.get("DRAW", 0)),
            "predicted_away_win_rows": int(prediction_counts.get("AWAY_WIN", 0)),
            "actual_home_win_rows": int(actual_counts.get("HOME_WIN", 0)),
            "actual_draw_rows": int(actual_counts.get("DRAW", 0)),
            "actual_away_win_rows": int(actual_counts.get("AWAY_WIN", 0)),
        }
        for column, value in zip(group_columns, group_values):
            row[column] = value
        rows.append(row)

    return pd.DataFrame(rows).sort_values(by=["selected_accuracy", "selected_rows"], ascending=[True, False])


# Construit les principaux motifs d'erreur et d'abstention V10.
def build_error_patterns(best_test_dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    selected_errors = best_test_dataframe[
        (best_test_dataframe["v10_recommendation_status"] == RECOMMEND_STATUS)
        & (~best_test_dataframe["v10_is_correct"])
    ].copy()
    abstentions = best_test_dataframe[best_test_dataframe["v10_recommendation_status"] == ABSTAIN_STATUS].copy()

    if not selected_errors.empty:
        group_columns = [column for column in ["league_code", "season", "v10_prediction", TARGET_COLUMN] if column in selected_errors.columns]
        grouped = selected_errors.groupby(group_columns).size().reset_index(name="rows")
        grouped["pattern_type"] = "selected_error"
        rows.append(grouped)

    if not abstentions.empty:
        group_columns = [column for column in ["league_code", "season", "v10_abstention_reason", TARGET_COLUMN] if column in abstentions.columns]
        grouped = abstentions.groupby(group_columns).size().reset_index(name="rows")
        grouped["pattern_type"] = "abstention"
        rows.append(grouped)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True, sort=False).sort_values(by="rows", ascending=False)


# Détermine le statut final V10 selon les gates de performance et de couverture.
def determine_v10_status(best_test_row: pd.Series) -> str:
    target_accuracy = max(TARGET_TEST_ACCURACY, float(best_test_row.get("v9_selected_accuracy_same_scope", STATIC_V9_REFERENCE_ACCURACY)))
    target_coverage = max(TARGET_TEST_COVERAGE, float(best_test_row.get("v9_coverage_same_scope", STATIC_V9_REFERENCE_COVERAGE)))
    target_rows = min(STATIC_V9_REFERENCE_SELECTED_ROWS, max(1, int(float(best_test_row["rows"]) * target_coverage)))

    if (
        float(best_test_row["selected_accuracy"]) >= target_accuracy
        and float(best_test_row["coverage"]) >= target_coverage
        and int(best_test_row["selected_rows"]) >= target_rows
        and int(best_test_row["net_correct_delta_vs_v9_total_scope"]) >= 0
    ):
        return "V10_ACCEPTED_SELECTIVE_CANDIDATE"

    if (
        float(best_test_row["selected_accuracy"]) >= MIN_TEST_ACCURACY_FOR_REVIEW
        and float(best_test_row["coverage"]) >= MIN_TEST_COVERAGE_FOR_REVIEW
    ):
        return "V10_META_ABSTENTION_REVIEW"

    return "V10_META_ABSTENTION_REJECTED"


# Construit une synthèse texte lisible pour le dossier RNCP et la revue ML.
def build_summary(
    metadata: dict,
    results_dataframe: pd.DataFrame,
    best_validation_row: pd.Series,
    best_test_row: pd.Series,
    status: str,
    by_class_dataframe: pd.DataFrame,
) -> str:
    top_validation = results_dataframe[results_dataframe["evaluation_scope"] == "meta_validation"].sort_values(
        by=["selected_accuracy", "coverage"],
        ascending=[False, False],
    ).head(10)

    draw_row = by_class_dataframe[by_class_dataframe["predicted_class"] == "DRAW"]
    predicted_draw_rows = int(draw_row["rows"].iloc[0]) if not draw_row.empty else 0

    lines = [
        "RubyBets - ML 1X2 V10 meta-abstention",
        "157 - Synthèse expérience V10",
        "",
        "Objectif :",
        "Tester une couche de décision KEEP/ABSTAIN au-dessus de la référence V6/V9 afin de vérifier si RubyBets peut recommander moins de matchs, mais avec une fiabilité plus élevée.",
        "",
        "Garde-fous respectés :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend ou du scoring explicable V1.",
        "- Aucun nouveau modèle officiel sauvegardé dans models/.",
        "- Aucune intégration produit.",
        "- Aucune nouvelle feature football ajoutée en base.",
        "",
        "Mode de données :",
        f"- Source mode : {metadata.get('source_mode', 'unknown')}",
        f"- Meta-train rows : {metadata.get('meta_train_rows', 0)}",
        f"- Meta-validation rows : {metadata.get('meta_validation_rows', 0)}",
        f"- Test rows : {metadata.get('test_rows', 0)}",
        "",
        "Principe V10 :",
        "- La V10 ne prédit pas directement HOME_WIN / DRAW / AWAY_WIN.",
        "- Elle apprend une cible binaire : la prédiction V6 est-elle correcte ?",
        "- Si le signal est suffisant, la prédiction V6 est conservée.",
        "- Sinon, RubyBets s'abstient.",
        "",
        "Meilleure stratégie choisie sur meta-validation :",
        f"- Strategy : {best_validation_row['strategy']}",
        f"- Selected accuracy validation : {best_validation_row['selected_accuracy']}",
        f"- Coverage validation : {best_validation_row['coverage']}",
        f"- Net correct delta vs V9 validation scope : {best_validation_row['net_correct_delta_vs_v9_total_scope']}",
        "",
        "Résultat final sur test :",
        f"- Status : {status}",
        f"- Strategy : {best_test_row['strategy']}",
        f"- Selected accuracy : {best_test_row['selected_accuracy']}",
        f"- Coverage : {best_test_row['coverage']}",
        f"- Abstention rate : {best_test_row['abstention_rate']}",
        f"- Selected rows : {best_test_row['selected_rows']}",
        f"- V9 selected accuracy same scope : {best_test_row['v9_selected_accuracy_same_scope']}",
        f"- V9 coverage same scope : {best_test_row['v9_coverage_same_scope']}",
        f"- Net correct delta vs V9 total scope : {best_test_row['net_correct_delta_vs_v9_total_scope']}",
        f"- Predicted DRAW rows : {predicted_draw_rows}",
        "",
        "Lecture experte :",
    ]

    if status == "V10_ACCEPTED_SELECTIVE_CANDIDATE":
        lines.append("La V10 bat la référence sélective sur les gates principaux. Elle peut être conservée comme candidat expérimental fort, mais sans intégration produit immédiate.")
    elif status == "V10_META_ABSTENTION_REVIEW":
        lines.append("La V10 produit un signal intéressant, mais ne valide pas encore assez fortement les gates pour remplacer V9. Elle reste en revue.")
    else:
        lines.append("La V10 ne bat pas suffisamment la V9 sélective. Elle doit être rejetée ou documentée comme piste exploratoire non concluante.")

    lines.extend(
        [
            "",
            "Top stratégies meta-validation :",
        ]
    )
    for _, row in top_validation.iterrows():
        lines.append(
            f"- {row['strategy']} | acc={row['selected_accuracy']} | coverage={row['coverage']} | rows={row['selected_rows']} | delta_v9={row['net_correct_delta_vs_v9_total_scope']}"
        )

    lines.extend(
        [
            "",
            "Décision produit :",
            "Ne pas intégrer la V10 dans RubyBets à ce stade. Le scoring explicable V1 reste le socle officiel. La V10 sert uniquement de preuve expérimentale ML/RNCP.",
            "",
            "Fichiers produits :",
            f"- {SUMMARY_TXT}",
            f"- {RESULTS_CSV}",
            f"- {BEST_STRATEGY_CSV}",
            f"- {BY_CLASS_CSV}",
            f"- {BY_LEAGUE_SEASON_CSV}",
            f"- {ERROR_PATTERNS_CSV}",
            f"- {DECISION_TXT}",
            "",
            "Statut de suivi :",
            "- V10 meta-abstention : réalisée si les fichiers 157 à 163 sont générés.",
            "- Fichiers sources à mettre à jour ensuite : plan ML/RNCP et documents de preuves concernés.",
        ]
    )

    if "fallback_error" in metadata:
        lines.extend(["", "Note fallback :", f"- {metadata['fallback_error']}"])

    return "\n".join(lines)


# Construit le fichier de décision final V10.
def build_decision(best_test_row: pd.Series, status: str) -> str:
    lines = [
        "RubyBets - Décision V10 meta-abstention",
        "163 - Decision expérience V10",
        "",
        f"Status : {status}",
        "",
        "Métriques globales retenues :",
        f"- Strategy : {best_test_row['strategy']}",
        f"- Selected accuracy : {best_test_row['selected_accuracy']}",
        f"- Coverage : {best_test_row['coverage']}",
        f"- Abstention rate : {best_test_row['abstention_rate']}",
        f"- Selected rows : {best_test_row['selected_rows']}",
        f"- V9 selected accuracy same scope : {best_test_row['v9_selected_accuracy_same_scope']}",
        f"- V9 coverage same scope : {best_test_row['v9_coverage_same_scope']}",
        f"- Net correct delta vs V9 total scope : {best_test_row['net_correct_delta_vs_v9_total_scope']}",
        f"- Predicted DRAW rows : {best_test_row['predicted_draw_rows']}",
        "",
        "Gates appliqués :",
        f"- Selected accuracy >= max({TARGET_TEST_ACCURACY}, V9 selected accuracy same scope).",
        f"- Coverage >= max({TARGET_TEST_COVERAGE}, V9 coverage same scope).",
        "- Net correct delta vs V9 total scope >= 0.",
        "- Pas de sauvegarde de modèle officiel.",
        "- Pas d'intégration API/frontend/scoring V1.",
        "",
        "Décision opérationnelle :",
    ]

    if status == "V10_ACCEPTED_SELECTIVE_CANDIDATE":
        lines.append("La V10 peut être conservée comme candidat expérimental fort et passer ensuite en analyse de stabilité détaillée.")
    elif status == "V10_META_ABSTENTION_REVIEW":
        lines.append("La V10 reste intéressante mais nécessite une revue avant toute décision officielle. Elle ne remplace pas V9 à ce stade.")
    else:
        lines.append("La V10 ne doit pas être retenue comme amélioration. Conserver V9 comme meilleure baseline sélective et documenter l'échec expérimental.")

    lines.extend(
        [
            "",
            "Statut de suivi à mettre à jour :",
            "- V10 meta-abstention : réalisée.",
            "- Fichiers concernés : 157, 158, 159, 160, 161, 162, 163.",
            "- Prochaine action : analyser le statut obtenu et décider si une stabilité V10 est justifiée.",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les preuves V10 dans reports/evidence/ml_training.
def save_v10_reports(
    results_dataframe: pd.DataFrame,
    best_strategy_dataframe: pd.DataFrame,
    by_class_dataframe: pd.DataFrame,
    by_league_season_dataframe: pd.DataFrame,
    error_patterns_dataframe: pd.DataFrame,
    summary: str,
    decision: str,
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    results_dataframe.to_csv(RESULTS_CSV, index=False, encoding="utf-8")
    best_strategy_dataframe.to_csv(BEST_STRATEGY_CSV, index=False, encoding="utf-8")
    by_class_dataframe.to_csv(BY_CLASS_CSV, index=False, encoding="utf-8")
    by_league_season_dataframe.to_csv(BY_LEAGUE_SEASON_CSV, index=False, encoding="utf-8")
    error_patterns_dataframe.to_csv(ERROR_PATTERNS_CSV, index=False, encoding="utf-8")
    SUMMARY_TXT.write_text(summary, encoding="utf-8")
    DECISION_TXT.write_text(decision, encoding="utf-8")


# Lance l'expérience complète V10 meta-abstention.
def main() -> None:
    print("Chargement des données V10 meta-abstention...", flush=True)
    meta_train_dataframe, meta_validation_dataframe, test_dataframe, metadata = load_v10_prediction_sets()

    print(f"Meta-train rows: {len(meta_train_dataframe)}", flush=True)
    print(f"Meta-validation rows: {len(meta_validation_dataframe)}", flush=True)
    print(f"Test rows: {len(test_dataframe)}", flush=True)

    print("Entraînement et évaluation des politiques V10...", flush=True)
    results_dataframe, policy_outputs = evaluate_v10_policies(
        meta_train_dataframe=meta_train_dataframe,
        meta_validation_dataframe=meta_validation_dataframe,
        test_dataframe=test_dataframe,
    )

    best_validation_row = select_best_validation_strategy(results_dataframe)
    selected_policy = policy_from_result_row(best_validation_row)
    best_test_rows = results_dataframe[
        (results_dataframe["evaluation_scope"] == "test")
        & (results_dataframe["strategy"] == selected_policy.name)
    ]

    if best_test_rows.empty:
        raise RuntimeError(f"Stratégie V10 sélectionnée introuvable sur test : {selected_policy.name}")

    best_test_row = best_test_rows.iloc[0]
    best_test_dataframe = policy_outputs[("test", selected_policy.name)]
    status = determine_v10_status(best_test_row)

    by_class_dataframe = build_by_class(best_test_dataframe)
    by_league_season_dataframe = build_by_league_season(best_test_dataframe)
    error_patterns_dataframe = build_error_patterns(best_test_dataframe)
    best_strategy_dataframe = pd.DataFrame([best_validation_row.to_dict(), best_test_row.to_dict()])

    summary = build_summary(
        metadata=metadata,
        results_dataframe=results_dataframe,
        best_validation_row=best_validation_row,
        best_test_row=best_test_row,
        status=status,
        by_class_dataframe=by_class_dataframe,
    )
    decision = build_decision(best_test_row, status)

    save_v10_reports(
        results_dataframe=results_dataframe,
        best_strategy_dataframe=best_strategy_dataframe,
        by_class_dataframe=by_class_dataframe,
        by_league_season_dataframe=by_league_season_dataframe,
        error_patterns_dataframe=error_patterns_dataframe,
        summary=summary,
        decision=decision,
    )

    print("OK - Expérience V10 meta-abstention terminée.", flush=True)
    print(f"Status: {status}", flush=True)
    print(f"Selected validation strategy: {best_validation_row['strategy']}", flush=True)
    print(f"Test selected accuracy: {best_test_row['selected_accuracy']}", flush=True)
    print(f"Test coverage: {best_test_row['coverage']}", flush=True)
    print(f"Test abstention rate: {best_test_row['abstention_rate']}", flush=True)
    print(f"Selected rows: {best_test_row['selected_rows']}", flush=True)
    print(f"Predicted DRAW rows: {best_test_row['predicted_draw_rows']}", flush=True)
    print(f"Net correct delta vs V9 total scope: {best_test_row['net_correct_delta_vs_v9_total_scope']}", flush=True)
    print(f"Summary saved: {SUMMARY_TXT}", flush=True)
    print(f"Results CSV saved: {RESULTS_CSV}", flush=True)
    print(f"Best strategy CSV saved: {BEST_STRATEGY_CSV}", flush=True)
    print(f"By class CSV saved: {BY_CLASS_CSV}", flush=True)
    print(f"By league/season CSV saved: {BY_LEAGUE_SEASON_CSV}", flush=True)
    print(f"Error patterns CSV saved: {ERROR_PATTERNS_CSV}", flush=True)
    print(f"Decision saved: {DECISION_TXT}", flush=True)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
#
# backend/scripts/ml/train_1x2_v9_selective_calibration_abstention.py
#        ↓ lecture/reconstruction si DATABASE_URL disponible
# PostgreSQL ml.clean_matches + ml.raw_matches.raw_data  OU  reports/evidence/ml_training/147_*.csv
#        ↓
# V10 meta-modèle KEEP / ABSTAIN en mémoire uniquement
#        ↓
# reports/evidence/ml_training/157 à 163
#
# Aucun flux sortant vers : models/, API, frontend, scoring V1 ou modification PostgreSQL.
