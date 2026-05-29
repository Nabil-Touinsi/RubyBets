# Rôle du fichier : analyser la stabilité de la V9 ML 1X2 sélective à partir des CSV déjà générés, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modèles sauvegardés.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

V9_RESULTS_CSV = EVIDENCE_DIR / "146_1x2_v9_selective_calibration_abstention_results.csv"
V9_BEST_PREDICTIONS_CSV = EVIDENCE_DIR / "147_1x2_v9_selective_calibration_abstention_best_predictions.csv"
V9_CONFIDENCE_BINS_CSV = EVIDENCE_DIR / "148_1x2_v9_selective_calibration_abstention_confidence_bins.csv"
V9_ERROR_PATTERNS_CSV = EVIDENCE_DIR / "149_1x2_v9_selective_calibration_abstention_error_patterns.csv"
V9_DECISION_TXT = EVIDENCE_DIR / "150_1x2_v9_selective_calibration_abstention_decision.txt"

SUMMARY_TXT = EVIDENCE_DIR / "151_1x2_v9_selective_stability_summary.txt"
LEAGUE_SEASON_CSV = EVIDENCE_DIR / "152_1x2_v9_selective_stability_by_league_season.csv"
PREDICTED_CLASS_CSV = EVIDENCE_DIR / "153_1x2_v9_selective_stability_by_predicted_class.csv"
CONFIDENCE_CSV = EVIDENCE_DIR / "154_1x2_v9_selective_stability_by_confidence.csv"
DECISION_TXT = EVIDENCE_DIR / "155_1x2_v9_selective_stability_decision.txt"

TARGET_COLUMN = "target_result"
TARGET_CLASSES = ["HOME_WIN", "DRAW", "AWAY_WIN"]
RECOMMEND_STATUS = "RECOMMEND"
ABSTAIN_STATUS = "ABSTAIN"

CONFIDENCE_BINS = [0.0, 0.45, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90, 1.0]
CONFIDENCE_LABELS = [
    "very_low_<0.45",
    "low_0.45_0.55",
    "medium_0.55_0.60",
    "solid_0.60_0.65",
    "strong_0.65_0.70",
    "selected_0.70_0.75",
    "selected_0.75_0.80",
    "selected_0.80_0.90",
    "elite_0.90_1.00",
]

MIN_OVERALL_SELECTED_ACCURACY = 0.70
MIN_OVERALL_COVERAGE = 0.10
MIN_OVERALL_SELECTED_ROWS = 500
MIN_RAW_V6_NET_DELTA = 0
MIN_LEAGUE_ROWS_FOR_GATE = 50
MIN_SEASON_ROWS_FOR_GATE = 100
MIN_LEAGUE_SELECTED_ACCURACY = 0.65
MIN_SEASON_SELECTED_ACCURACY = 0.65
MAX_LEAGUE_CONCENTRATION = 0.45
MAX_SEASON_CONCENTRATION = 0.60


@dataclass(frozen=True)
class SegmentMetrics:
    rows: int
    selected_rows: int
    abstained_rows: int
    coverage: float
    abstention_rate: float
    selected_accuracy: float
    raw_v6_accuracy_same_selected: float
    selected_accuracy_delta_vs_raw_v6_same_selected: float
    selected_correct_rows: int
    selected_error_rows: int
    raw_v6_correct_same_selected: int
    net_correct_delta_vs_raw_v6_same_selected: int
    avg_confidence_selected: float
    avg_margin_selected: float
    predicted_home_win_rows: int
    predicted_draw_rows: int
    predicted_away_win_rows: int
    actual_home_win_rows: int
    actual_draw_rows: int
    actual_away_win_rows: int


# Arrondit une valeur numérique pour produire des exports stables et lisibles.
def rounded(value: object, digits: int = 4) -> float:
    try:
        result = float(value)
        if math.isnan(result):
            return 0.0
        return round(result, digits)
    except (TypeError, ValueError):
        return 0.0


# Calcule un ratio en évitant les divisions par zéro.
def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# Charge un CSV obligatoire et produit une erreur claire si la preuve V9 est absente.
def load_required_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Fichier obligatoire introuvable : {path}")
    return pd.read_csv(path)


# Charge un fichier texte optionnel pour enrichir la synthèse sans bloquer l'analyse.
def load_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# Vérifie que les colonnes nécessaires à l'analyse de stabilité V9 existent.
def validate_required_columns(dataframe: pd.DataFrame) -> None:
    required_columns = [
        TARGET_COLUMN,
        "season",
        "v9_policy",
        "v9_recommendation_status",
        "v9_prediction",
        "v9_confidence_probability",
        "v9_margin",
        "v9_is_correct",
    ]
    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes dans le fichier 147 V9 : {missing_columns}")


# Convertit une colonne booléenne lue depuis CSV en vraie série booléenne.
def normalize_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin(["true", "1", "yes", "y"])


# Prépare les colonnes de travail : booléens, ligue inconnue, bandes de confiance et statut sélectionné.
def normalize_predictions_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    validate_required_columns(dataframe)
    output = dataframe.copy()

    if "league_code" not in output.columns:
        output["league_code"] = "UNKNOWN"

    output["league_code"] = output["league_code"].fillna("UNKNOWN").astype(str)
    output["season"] = output["season"].fillna("UNKNOWN").astype(str)
    output["v9_recommendation_status"] = output["v9_recommendation_status"].fillna(ABSTAIN_STATUS).astype(str)
    output["v9_prediction"] = output["v9_prediction"].fillna(ABSTAIN_STATUS).astype(str)
    output[TARGET_COLUMN] = output[TARGET_COLUMN].fillna("UNKNOWN").astype(str)

    output["v9_confidence_probability"] = pd.to_numeric(output["v9_confidence_probability"], errors="coerce").fillna(0.0)
    output["v9_margin"] = pd.to_numeric(output["v9_margin"], errors="coerce").fillna(0.0)
    output["v9_is_selected"] = output["v9_recommendation_status"] == RECOMMEND_STATUS
    output["v9_is_correct"] = normalize_bool_series(output["v9_is_correct"])

    if "raw_v6_reference_is_correct" in output.columns:
        output["raw_v6_reference_is_correct"] = normalize_bool_series(output["raw_v6_reference_is_correct"])
    elif "raw_v6_reference_predicted_class" in output.columns:
        output["raw_v6_reference_is_correct"] = output[TARGET_COLUMN] == output["raw_v6_reference_predicted_class"]
    else:
        output["raw_v6_reference_is_correct"] = False

    output["confidence_band"] = pd.cut(
        output["v9_confidence_probability"],
        bins=CONFIDENCE_BINS,
        labels=CONFIDENCE_LABELS,
        include_lowest=True,
    ).astype(str)

    output["margin_band"] = pd.cut(
        output["v9_margin"],
        bins=[-0.001, 0.03, 0.05, 0.10, 0.20, 1.0],
        labels=["tiny_<=0.03", "very_close_0.03_0.05", "close_0.05_0.10", "medium_0.10_0.20", "clear_>0.20"],
        include_lowest=True,
    ).astype(str)

    return output


# Calcule les métriques principales d'un segment en séparant matchs recommandés et abstentions.
def compute_segment_metrics(segment_dataframe: pd.DataFrame) -> SegmentMetrics:
    rows = int(len(segment_dataframe))
    selected_dataframe = segment_dataframe[segment_dataframe["v9_is_selected"]].copy()
    selected_rows = int(len(selected_dataframe))
    abstained_rows = rows - selected_rows

    selected_correct_rows = int(selected_dataframe["v9_is_correct"].sum()) if selected_rows else 0
    selected_error_rows = selected_rows - selected_correct_rows
    raw_v6_correct_same_selected = int(selected_dataframe["raw_v6_reference_is_correct"].sum()) if selected_rows else 0

    predicted_counts = selected_dataframe["v9_prediction"].value_counts().to_dict()
    actual_counts = selected_dataframe[TARGET_COLUMN].value_counts().to_dict()

    selected_accuracy = safe_rate(selected_correct_rows, selected_rows)
    raw_v6_accuracy = safe_rate(raw_v6_correct_same_selected, selected_rows)

    return SegmentMetrics(
        rows=rows,
        selected_rows=selected_rows,
        abstained_rows=abstained_rows,
        coverage=safe_rate(selected_rows, rows),
        abstention_rate=safe_rate(abstained_rows, rows),
        selected_accuracy=selected_accuracy,
        raw_v6_accuracy_same_selected=raw_v6_accuracy,
        selected_accuracy_delta_vs_raw_v6_same_selected=selected_accuracy - raw_v6_accuracy,
        selected_correct_rows=selected_correct_rows,
        selected_error_rows=selected_error_rows,
        raw_v6_correct_same_selected=raw_v6_correct_same_selected,
        net_correct_delta_vs_raw_v6_same_selected=selected_correct_rows - raw_v6_correct_same_selected,
        avg_confidence_selected=float(selected_dataframe["v9_confidence_probability"].mean()) if selected_rows else 0.0,
        avg_margin_selected=float(selected_dataframe["v9_margin"].mean()) if selected_rows else 0.0,
        predicted_home_win_rows=int(predicted_counts.get("HOME_WIN", 0)),
        predicted_draw_rows=int(predicted_counts.get("DRAW", 0)),
        predicted_away_win_rows=int(predicted_counts.get("AWAY_WIN", 0)),
        actual_home_win_rows=int(actual_counts.get("HOME_WIN", 0)),
        actual_draw_rows=int(actual_counts.get("DRAW", 0)),
        actual_away_win_rows=int(actual_counts.get("AWAY_WIN", 0)),
    )


# Transforme les métriques d'un segment en dictionnaire prêt pour export CSV.
def metrics_to_row(prefix: dict, metrics: SegmentMetrics) -> dict:
    row = dict(prefix)
    row.update(
        {
            "rows": metrics.rows,
            "selected_rows": metrics.selected_rows,
            "abstained_rows": metrics.abstained_rows,
            "coverage": rounded(metrics.coverage),
            "abstention_rate": rounded(metrics.abstention_rate),
            "selected_accuracy": rounded(metrics.selected_accuracy),
            "raw_v6_accuracy_same_selected": rounded(metrics.raw_v6_accuracy_same_selected),
            "selected_accuracy_delta_vs_raw_v6_same_selected": rounded(metrics.selected_accuracy_delta_vs_raw_v6_same_selected),
            "selected_correct_rows": metrics.selected_correct_rows,
            "selected_error_rows": metrics.selected_error_rows,
            "raw_v6_correct_same_selected": metrics.raw_v6_correct_same_selected,
            "net_correct_delta_vs_raw_v6_same_selected": metrics.net_correct_delta_vs_raw_v6_same_selected,
            "avg_confidence_selected": rounded(metrics.avg_confidence_selected),
            "avg_margin_selected": rounded(metrics.avg_margin_selected),
            "predicted_home_win_rows": metrics.predicted_home_win_rows,
            "predicted_draw_rows": metrics.predicted_draw_rows,
            "predicted_away_win_rows": metrics.predicted_away_win_rows,
            "actual_home_win_rows": metrics.actual_home_win_rows,
            "actual_draw_rows": metrics.actual_draw_rows,
            "actual_away_win_rows": metrics.actual_away_win_rows,
        }
    )
    return row


# Donne un statut simple à un segment pour identifier rapidement les zones solides ou fragiles.
def classify_segment_status(metrics: SegmentMetrics, min_rows: int, min_accuracy: float) -> str:
    if metrics.selected_rows == 0:
        return "NO_SELECTED_MATCH"
    if metrics.selected_rows < min_rows:
        return "LOW_SAMPLE_REVIEW"
    if metrics.selected_accuracy < min_accuracy:
        return "PERFORMANCE_REVIEW_NEEDED"
    if metrics.predicted_draw_rows == 0 and metrics.actual_draw_rows > 0:
        return "STABLE_BUT_NO_DRAW_RECOMMENDATION"
    return "STABLE_OK"


# Construit l'analyse par ligue, saison et couple ligue/saison dans un seul CSV 152.
def build_league_season_stability(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    segment_definitions = [
        ("global_test", [], 1, MIN_OVERALL_SELECTED_ACCURACY),
        ("by_league", ["league_code"], MIN_LEAGUE_ROWS_FOR_GATE, MIN_LEAGUE_SELECTED_ACCURACY),
        ("by_season", ["season"], MIN_SEASON_ROWS_FOR_GATE, MIN_SEASON_SELECTED_ACCURACY),
        ("by_league_season", ["league_code", "season"], 30, 0.60),
    ]

    for segment_type, group_columns, min_rows, min_accuracy in segment_definitions:
        if not group_columns:
            metrics = compute_segment_metrics(dataframe)
            rows.append(
                metrics_to_row(
                    {"segment_type": segment_type, "league_code": "ALL", "season": "ALL", "segment_status": classify_segment_status(metrics, min_rows, min_accuracy)},
                    metrics,
                )
            )
            continue

        for keys, group in dataframe.groupby(group_columns, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            prefix = {"segment_type": segment_type, "league_code": "ALL", "season": "ALL"}
            for column_name, value in zip(group_columns, keys):
                prefix[column_name] = value
            metrics = compute_segment_metrics(group)
            prefix["segment_status"] = classify_segment_status(metrics, min_rows, min_accuracy)
            rows.append(metrics_to_row(prefix, metrics))

    return pd.DataFrame(rows).sort_values(["segment_type", "league_code", "season"])


# Construit l'analyse par classe recommandée, avec une ligne explicite même si DRAW n'est jamais recommandé.
def build_predicted_class_stability(dataframe: pd.DataFrame) -> pd.DataFrame:
    selected_dataframe = dataframe[dataframe["v9_is_selected"]].copy()
    rows = []

    for class_name in TARGET_CLASSES:
        class_dataframe = selected_dataframe[selected_dataframe["v9_prediction"] == class_name].copy()
        metrics = compute_segment_metrics(class_dataframe)
        class_status = "STABLE_OK"
        if metrics.selected_rows == 0:
            class_status = "NO_RECOMMENDATION_FOR_CLASS"
        elif metrics.selected_accuracy < 0.65:
            class_status = "CLASS_PERFORMANCE_REVIEW"

        rows.append(
            metrics_to_row(
                {"predicted_class": class_name, "class_status": class_status},
                metrics,
            )
        )

    abstained_dataframe = dataframe[~dataframe["v9_is_selected"]].copy()
    abstained_metrics = compute_segment_metrics(abstained_dataframe)
    rows.append(
        metrics_to_row(
            {"predicted_class": ABSTAIN_STATUS, "class_status": "ABSTENTION_SCOPE_ONLY"},
            abstained_metrics,
        )
    )

    return pd.DataFrame(rows)


# Construit l'analyse par niveau de confiance et marge de décision.
def build_confidence_stability(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    scopes = [
        ("ALL", dataframe.copy()),
        (RECOMMEND_STATUS, dataframe[dataframe["v9_is_selected"]].copy()),
        (ABSTAIN_STATUS, dataframe[~dataframe["v9_is_selected"]].copy()),
    ]

    for scope_name, scope_dataframe in scopes:
        if scope_dataframe.empty:
            continue

        for group_columns in [["confidence_band"], ["margin_band"], ["confidence_band", "margin_band"]]:
            for keys, group in scope_dataframe.groupby(group_columns, dropna=False):
                if not isinstance(keys, tuple):
                    keys = (keys,)
                prefix = {"scope": scope_name, "segment_type": "+".join(group_columns)}
                for column_name, value in zip(group_columns, keys):
                    prefix[column_name] = value
                metrics = compute_segment_metrics(group)
                rows.append(metrics_to_row(prefix, metrics))

    return pd.DataFrame(rows).sort_values(["scope", "segment_type", "rows"], ascending=[True, True, False])


# Identifie les principaux motifs d'erreurs encore présents dans les matchs recommandés.
def build_top_error_patterns(dataframe: pd.DataFrame, limit: int = 12) -> pd.DataFrame:
    selected_errors = dataframe[dataframe["v9_is_selected"] & (~dataframe["v9_is_correct"])].copy()
    if selected_errors.empty:
        return pd.DataFrame()

    group_columns = ["league_code", "season", "v9_prediction", TARGET_COLUMN]
    error_patterns = selected_errors.groupby(group_columns, dropna=False).size().reset_index(name="rows")
    error_patterns["error_label"] = error_patterns["v9_prediction"] + " predicted instead of " + error_patterns[TARGET_COLUMN]
    return error_patterns.sort_values("rows", ascending=False).head(limit)


# Retrouve la ligne de résultats V9 test correspondant à la politique sélectionnée.
def find_selected_policy_result(results_dataframe: pd.DataFrame, policy_name: str) -> dict:
    if results_dataframe.empty:
        return {}

    matching_rows = results_dataframe[
        (results_dataframe.get("evaluation_scope", "") == "test")
        & (results_dataframe.get("strategy", "") == policy_name)
    ]

    if matching_rows.empty:
        return {}

    return matching_rows.iloc[0].to_dict()


# Détermine la décision finale de stabilité avec des gates simples et défendables.
def determine_stability_status(
    global_metrics: SegmentMetrics,
    league_season_dataframe: pd.DataFrame,
) -> tuple[str, list[str], list[str]]:
    blocking_reasons = []
    warning_reasons = []

    if global_metrics.selected_accuracy < MIN_OVERALL_SELECTED_ACCURACY:
        blocking_reasons.append(
            f"Selected accuracy globale insuffisante : {rounded(global_metrics.selected_accuracy)} < {MIN_OVERALL_SELECTED_ACCURACY}."
        )
    if global_metrics.coverage < MIN_OVERALL_COVERAGE:
        blocking_reasons.append(f"Coverage insuffisante : {rounded(global_metrics.coverage)} < {MIN_OVERALL_COVERAGE}.")
    if global_metrics.selected_rows < MIN_OVERALL_SELECTED_ROWS:
        blocking_reasons.append(f"Volume de matchs recommandés insuffisant : {global_metrics.selected_rows} < {MIN_OVERALL_SELECTED_ROWS}.")
    if global_metrics.net_correct_delta_vs_raw_v6_same_selected < MIN_RAW_V6_NET_DELTA:
        blocking_reasons.append(
            "La V9 fait moins bien que la V6 brute sur les mêmes matchs sélectionnés."
        )

    league_rows = league_season_dataframe[league_season_dataframe["segment_type"] == "by_league"].copy()
    season_rows = league_season_dataframe[league_season_dataframe["segment_type"] == "by_season"].copy()

    weak_leagues = league_rows[
        (league_rows["selected_rows"] >= MIN_LEAGUE_ROWS_FOR_GATE)
        & (league_rows["selected_accuracy"] < MIN_LEAGUE_SELECTED_ACCURACY)
    ]
    if not weak_leagues.empty:
        warning_reasons.append("Au moins une ligue majeure passe sous le seuil de stabilité recommandé.")

    weak_seasons = season_rows[
        (season_rows["selected_rows"] >= MIN_SEASON_ROWS_FOR_GATE)
        & (season_rows["selected_accuracy"] < MIN_SEASON_SELECTED_ACCURACY)
    ]
    if not weak_seasons.empty:
        warning_reasons.append("Au moins une saison test passe sous le seuil de stabilité recommandé.")

    if global_metrics.selected_rows > 0 and not league_rows.empty:
        max_league_share = float(league_rows["selected_rows"].max() / global_metrics.selected_rows)
        if max_league_share > MAX_LEAGUE_CONCENTRATION:
            warning_reasons.append(
                f"Les recommandations sont trop concentrées sur une seule ligue : {rounded(max_league_share)}."
            )

    if global_metrics.selected_rows > 0 and not season_rows.empty:
        max_season_share = float(season_rows["selected_rows"].max() / global_metrics.selected_rows)
        if max_season_share > MAX_SEASON_CONCENTRATION:
            warning_reasons.append(
                f"Les recommandations sont trop concentrées sur une seule saison : {rounded(max_season_share)}."
            )

    if global_metrics.predicted_draw_rows == 0:
        warning_reasons.append("Aucun DRAW n'est recommandé : limite acceptable uniquement si elle est explicitement documentée.")

    if blocking_reasons:
        return "V9_STABILITY_REJECTED", blocking_reasons, warning_reasons
    if warning_reasons:
        return "V9_STABILITY_REVIEW", blocking_reasons, warning_reasons
    return "V9_STABILITY_VALIDATED", blocking_reasons, warning_reasons


# Transforme un DataFrame en extrait texte court pour la synthèse.
def dataframe_preview(dataframe: pd.DataFrame, columns: list[str], max_rows: int = 8) -> list[str]:
    if dataframe.empty:
        return ["- Aucun élément."]

    existing_columns = [column for column in columns if column in dataframe.columns]
    preview_dataframe = dataframe[existing_columns].head(max_rows)
    return ["- " + " | ".join(f"{column}={row[column]}" for column in existing_columns) for _, row in preview_dataframe.iterrows()]


# Construit le résumé texte 151 pour rendre l'analyse directement exploitable en soutenance.
def build_summary(
    dataframe: pd.DataFrame,
    results_dataframe: pd.DataFrame,
    original_confidence_bins_dataframe: pd.DataFrame,
    original_error_patterns_dataframe: pd.DataFrame,
    original_decision_text: str,
    league_season_dataframe: pd.DataFrame,
    predicted_class_dataframe: pd.DataFrame,
    confidence_dataframe: pd.DataFrame,
    top_error_patterns: pd.DataFrame,
    stability_status: str,
    blocking_reasons: list[str],
    warning_reasons: list[str],
) -> str:
    policy_name = str(dataframe["v9_policy"].mode().iloc[0]) if not dataframe.empty else "UNKNOWN"
    model_variant = str(dataframe.get("v9_model_variant", pd.Series(["UNKNOWN"])).mode().iloc[0])
    global_metrics = compute_segment_metrics(dataframe)
    selected_dataframe = dataframe[dataframe["v9_is_selected"]].copy()
    selected_policy_result = find_selected_policy_result(results_dataframe, policy_name)

    lines = [
        "RubyBets - ML 1X2 V9 selective stability analysis",
        "151 - Synthèse de stabilité V9 sélective",
        "",
        "Objectif :",
        "Vérifier si la performance de la V9 selective calibration + abstention est stable, défendable et exploitable comme candidat expérimental sans l'intégrer au produit.",
        "",
        "Garde-fous respectés :",
        "- Lecture uniquement des fichiers de preuves V9 déjà générés.",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modèles sauvegardés.",
        "- Aucune intégration Understat/xG ou V9 au produit.",
        "",
        "Fichiers d'entrée utilisés :",
        f"- {V9_RESULTS_CSV}",
        f"- {V9_BEST_PREDICTIONS_CSV}",
        f"- {V9_CONFIDENCE_BINS_CSV} (lu pour contexte, non réécrit)",
        f"- {V9_ERROR_PATTERNS_CSV} (lu pour contexte, non réécrit)",
        f"- {V9_DECISION_TXT} (lu pour contexte si disponible)",
        "",
        "Politique V9 analysée :",
        f"- Strategy : {policy_name}",
        f"- Model variant : {model_variant}",
        "",
        "Résultat global sur le test :",
        f"- Total rows : {global_metrics.rows}",
        f"- Selected rows : {global_metrics.selected_rows}",
        f"- Abstained rows : {global_metrics.abstained_rows}",
        f"- Coverage : {rounded(global_metrics.coverage)}",
        f"- Abstention rate : {rounded(global_metrics.abstention_rate)}",
        f"- Selected accuracy : {rounded(global_metrics.selected_accuracy)}",
        f"- Raw V6 accuracy on same selected rows : {rounded(global_metrics.raw_v6_accuracy_same_selected)}",
        f"- Net correct delta vs raw V6 same selected : {global_metrics.net_correct_delta_vs_raw_v6_same_selected}",
        f"- Avg confidence selected : {rounded(global_metrics.avg_confidence_selected)}",
        f"- Avg margin selected : {rounded(global_metrics.avg_margin_selected)}",
        "",
        "Distribution des recommandations sélectionnées :",
        f"- HOME_WIN predicted rows : {global_metrics.predicted_home_win_rows}",
        f"- DRAW predicted rows : {global_metrics.predicted_draw_rows}",
        f"- AWAY_WIN predicted rows : {global_metrics.predicted_away_win_rows}",
        f"- Actual DRAW rows inside selected scope : {global_metrics.actual_draw_rows}",
        "",
        "Lecture experte :",
    ]

    if global_metrics.predicted_draw_rows == 0:
        lines.append("- La V9 sélective ne recommande aucun DRAW. Ce n'est pas bloquant pour un candidat forte confiance, mais cette limite doit être assumée explicitement.")
    else:
        lines.append("- La V9 recommande au moins quelques DRAW ; leur précision doit être analysée avec prudence car le volume peut être faible.")

    if global_metrics.net_correct_delta_vs_raw_v6_same_selected == 0:
        lines.append("- La V9 ne modifie pas réellement le niveau de bonnes prédictions face à la V6 sur les mêmes matchs : son intérêt principal vient de l'abstention.")
    elif global_metrics.net_correct_delta_vs_raw_v6_same_selected > 0:
        lines.append("- La V9 améliore la V6 sur le même périmètre sélectionné, ce qui renforce son intérêt expérimental.")
    else:
        lines.append("- La V9 est moins bonne que la V6 sur le même périmètre sélectionné : la stabilité doit être revue.")

    lines.extend(
        [
            "",
            "Rappel éventuel du fichier 146 pour la politique sélectionnée :",
            f"- selective_accuracy : {selected_policy_result.get('selective_accuracy', 'non disponible')}",
            f"- coverage : {selected_policy_result.get('coverage', 'non disponible')}",
            f"- abstention_rate : {selected_policy_result.get('abstention_rate', 'non disponible')}",
            f"- selected_rows : {selected_policy_result.get('selected_rows', 'non disponible')}",
            "",
            "Segments ligue/saison à surveiller :",
        ]
    )

    fragile_segments = league_season_dataframe[
        league_season_dataframe["segment_status"].isin(["PERFORMANCE_REVIEW_NEEDED", "LOW_SAMPLE_REVIEW", "STABLE_BUT_NO_DRAW_RECOMMENDATION"])
    ].copy()
    lines.extend(
        dataframe_preview(
            fragile_segments.sort_values(["segment_status", "selected_accuracy", "selected_rows"], ascending=[True, True, False]),
            ["segment_type", "league_code", "season", "selected_rows", "selected_accuracy", "segment_status"],
            10,
        )
    )

    lines.extend(["", "Stabilité par classe prédite :"])
    lines.extend(
        dataframe_preview(
            predicted_class_dataframe,
            ["predicted_class", "selected_rows", "selected_accuracy", "raw_v6_accuracy_same_selected", "actual_draw_rows", "class_status"],
            8,
        )
    )

    lines.extend(["", "Top erreurs restantes sur les matchs recommandés :"])
    lines.extend(dataframe_preview(top_error_patterns, ["league_code", "season", "error_label", "rows"], 10))

    lines.extend(
        [
            "",
            "Décision de stabilité :",
            f"- Status : {stability_status}",
            "",
            "Raisons bloquantes :",
        ]
    )
    lines.extend([f"- {reason}" for reason in blocking_reasons] if blocking_reasons else ["- Aucune raison bloquante détectée."])

    lines.extend(["", "Points de vigilance :"])
    lines.extend([f"- {reason}" for reason in warning_reasons] if warning_reasons else ["- Aucun point de vigilance majeur détecté."])

    lines.extend(
        [
            "",
            "Fichiers produits :",
            f"- {SUMMARY_TXT}",
            f"- {LEAGUE_SEASON_CSV}",
            f"- {PREDICTED_CLASS_CSV}",
            f"- {CONFIDENCE_CSV}",
            f"- {DECISION_TXT}",
            "",
            "Statut de suivi :",
            "- Analyse de stabilité V9 sélective : réalisée si les fichiers 151 à 155 sont générés.",
            "- Fichiers sources à mettre à jour ensuite : Plan_prochaines_etapes_V9_RubyBets.docx et documents RNCP/ML concernés.",
        ]
    )

    if not original_decision_text.strip():
        lines.extend(["", "Note : le fichier 150 n'a pas été trouvé ou était vide au moment de l'analyse."])

    if original_confidence_bins_dataframe.empty or original_error_patterns_dataframe.empty:
        lines.extend(["", "Note : un des fichiers de contexte 148 ou 149 est vide. L'analyse 151-155 reste basée sur le fichier 147."])

    return "\n".join(lines)


# Construit le fichier décision 155 avec un statut clair et les actions suivantes.
def build_decision_text(
    stability_status: str,
    global_metrics: SegmentMetrics,
    blocking_reasons: list[str],
    warning_reasons: list[str],
) -> str:
    lines = [
        "RubyBets - Décision stabilité V9 sélective",
        "155 - Decision analyse stabilité V9",
        "",
        f"Status : {stability_status}",
        "",
        "Métriques globales retenues :",
        f"- Selected accuracy : {rounded(global_metrics.selected_accuracy)}",
        f"- Coverage : {rounded(global_metrics.coverage)}",
        f"- Abstention rate : {rounded(global_metrics.abstention_rate)}",
        f"- Selected rows : {global_metrics.selected_rows}",
        f"- Net correct delta vs raw V6 same selected : {global_metrics.net_correct_delta_vs_raw_v6_same_selected}",
        f"- Predicted DRAW rows : {global_metrics.predicted_draw_rows}",
        "",
        "Gates appliqués :",
        f"- Selected accuracy >= {MIN_OVERALL_SELECTED_ACCURACY}",
        f"- Coverage >= {MIN_OVERALL_COVERAGE}",
        f"- Selected rows >= {MIN_OVERALL_SELECTED_ROWS}",
        f"- Net correct delta vs raw V6 same selected >= {MIN_RAW_V6_NET_DELTA}",
        f"- Pas d'effondrement majeur par ligue >= {MIN_LEAGUE_ROWS_FOR_GATE} lignes sélectionnées.",
        f"- Pas d'effondrement majeur par saison >= {MIN_SEASON_ROWS_FOR_GATE} lignes sélectionnées.",
        "",
        "Raisons bloquantes :",
    ]
    lines.extend([f"- {reason}" for reason in blocking_reasons] if blocking_reasons else ["- Aucune."])

    lines.extend(["", "Points de vigilance :"])
    lines.extend([f"- {reason}" for reason in warning_reasons] if warning_reasons else ["- Aucun."])

    lines.extend(["", "Décision opérationnelle :"])
    if stability_status == "V9_STABILITY_VALIDATED":
        lines.extend(
            [
                "- La V9 peut rester candidat expérimental sélectif validé en stabilité.",
                "- Elle ne doit pas encore être intégrée au produit sans validation utilisateur explicite.",
                "- La documentation doit préciser que le gain vient principalement de l'abstention et non d'une amélioration générale du modèle.",
            ]
        )
    elif stability_status == "V9_STABILITY_REVIEW":
        lines.extend(
            [
                "- La V9 reste intéressante mais nécessite une revue avant toute décision officielle.",
                "- Ne pas sauvegarder de modèle et ne pas brancher la V9 à l'API/frontend.",
                "- Analyser les segments faibles, la concentration des recommandations et l'absence éventuelle de DRAW.",
            ]
        )
    else:
        lines.extend(
            [
                "- La V9 ne doit pas être retenue comme candidat stable à ce stade.",
                "- Conserver les fichiers comme preuve d'expérimentation ML et de décision responsable.",
                "- Ne pas refaire d'anciens tests sans nouvelle hypothèse claire.",
            ]
        )

    lines.extend(
        [
            "",
            "Statut de suivi à mettre à jour :",
            "- Analyse de stabilité V9 sélective : réalisée.",
            "- Fichiers concernés : 151, 152, 153, 154, 155.",
            "- Prochaine action : décider si l'on documente V9 comme candidat expérimental stable, candidat à revoir ou piste rejetée.",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les fichiers 151 à 155 dans le dossier de preuves ML.
def save_outputs(
    summary_text: str,
    league_season_dataframe: pd.DataFrame,
    predicted_class_dataframe: pd.DataFrame,
    confidence_dataframe: pd.DataFrame,
    decision_text: str,
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_TXT.write_text(summary_text, encoding="utf-8")
    league_season_dataframe.to_csv(LEAGUE_SEASON_CSV, index=False, encoding="utf-8")
    predicted_class_dataframe.to_csv(PREDICTED_CLASS_CSV, index=False, encoding="utf-8")
    confidence_dataframe.to_csv(CONFIDENCE_CSV, index=False, encoding="utf-8")
    DECISION_TXT.write_text(decision_text, encoding="utf-8")


# Lance l'analyse complète de stabilité V9 à partir des preuves existantes.
def main() -> None:
    try:
        print("Chargement des preuves V9 selective calibration + abstention...", flush=True)
        results_dataframe = load_required_csv(V9_RESULTS_CSV)
        predictions_dataframe = load_required_csv(V9_BEST_PREDICTIONS_CSV)
        original_confidence_bins_dataframe = load_required_csv(V9_CONFIDENCE_BINS_CSV)
        original_error_patterns_dataframe = load_required_csv(V9_ERROR_PATTERNS_CSV)
        original_decision_text = load_optional_text(V9_DECISION_TXT)

        print("Préparation des colonnes de stabilité V9...", flush=True)
        normalized_dataframe = normalize_predictions_dataframe(predictions_dataframe)

        print("Analyse par ligue, saison et couple ligue/saison...", flush=True)
        league_season_dataframe = build_league_season_stability(normalized_dataframe)

        print("Analyse par classe prédite...", flush=True)
        predicted_class_dataframe = build_predicted_class_stability(normalized_dataframe)

        print("Analyse par niveau de confiance et marge...", flush=True)
        confidence_dataframe = build_confidence_stability(normalized_dataframe)

        print("Analyse des erreurs restantes...", flush=True)
        top_error_patterns = build_top_error_patterns(normalized_dataframe)

        global_metrics = compute_segment_metrics(normalized_dataframe)
        stability_status, blocking_reasons, warning_reasons = determine_stability_status(
            global_metrics=global_metrics,
            league_season_dataframe=league_season_dataframe,
        )

        summary_text = build_summary(
            dataframe=normalized_dataframe,
            results_dataframe=results_dataframe,
            original_confidence_bins_dataframe=original_confidence_bins_dataframe,
            original_error_patterns_dataframe=original_error_patterns_dataframe,
            original_decision_text=original_decision_text,
            league_season_dataframe=league_season_dataframe,
            predicted_class_dataframe=predicted_class_dataframe,
            confidence_dataframe=confidence_dataframe,
            top_error_patterns=top_error_patterns,
            stability_status=stability_status,
            blocking_reasons=blocking_reasons,
            warning_reasons=warning_reasons,
        )
        decision_text = build_decision_text(
            stability_status=stability_status,
            global_metrics=global_metrics,
            blocking_reasons=blocking_reasons,
            warning_reasons=warning_reasons,
        )

        save_outputs(
            summary_text=summary_text,
            league_season_dataframe=league_season_dataframe,
            predicted_class_dataframe=predicted_class_dataframe,
            confidence_dataframe=confidence_dataframe,
            decision_text=decision_text,
        )

        print("OK - Analyse de stabilité V9 sélective terminée.", flush=True)
        print(f"Status: {stability_status}", flush=True)
        print(f"Selected accuracy: {rounded(global_metrics.selected_accuracy)}", flush=True)
        print(f"Coverage: {rounded(global_metrics.coverage)}", flush=True)
        print(f"Abstention rate: {rounded(global_metrics.abstention_rate)}", flush=True)
        print(f"Selected rows: {global_metrics.selected_rows}", flush=True)
        print(f"Predicted DRAW rows: {global_metrics.predicted_draw_rows}", flush=True)
        print(f"Net correct delta vs raw V6 same selected: {global_metrics.net_correct_delta_vs_raw_v6_same_selected}", flush=True)
        print(f"Summary saved: {SUMMARY_TXT}", flush=True)
        print(f"League/season CSV saved: {LEAGUE_SEASON_CSV}", flush=True)
        print(f"Predicted class CSV saved: {PREDICTED_CLASS_CSV}", flush=True)
        print(f"Confidence CSV saved: {CONFIDENCE_CSV}", flush=True)
        print(f"Decision saved: {DECISION_TXT}", flush=True)

    except Exception as error:
        print("Erreur pendant l'analyse de stabilité V9 sélective.", flush=True)
        print(str(error), flush=True)
        raise


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
#
# reports/evidence/ml_training/146 à 150
#        ↓
# analyze_1x2_v9_selective_stability.py
#        ↓
# rapports de stabilité 151 à 155
#        ↓
# reports/evidence/ml_training/
