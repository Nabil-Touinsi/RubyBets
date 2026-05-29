# Rôle du fichier :
# Analyse la stabilité de l'expérience ML V8 Understat xG à partir des prédictions déjà générées.
# Le script travaille en dry-run : il lit les CSV de preuves, produit des analyses segmentées et ne modifie aucune base ni modèle.

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

PREDICTIONS_CSV = EVIDENCE_DIR / "131_1x2_v8_understat_xg_in_memory_best_predictions.csv"
RESULTS_CSV = EVIDENCE_DIR / "130_1x2_v8_understat_xg_in_memory_results.csv"
REPORT_JSON = EVIDENCE_DIR / "132_1x2_v8_understat_xg_in_memory_classification_report.json"

SUMMARY_TXT = EVIDENCE_DIR / "134_1x2_v8_understat_xg_stability_summary.txt"
LEAGUE_SEASON_CSV = EVIDENCE_DIR / "135_1x2_v8_understat_xg_stability_by_league_season.csv"
CONFIDENCE_CSV = EVIDENCE_DIR / "136_1x2_v8_understat_xg_stability_by_confidence.csv"
DRAW_SEGMENTS_CSV = EVIDENCE_DIR / "137_1x2_v8_understat_xg_stability_draw_segments.csv"
ERROR_PATTERNS_CSV = EVIDENCE_DIR / "138_1x2_v8_understat_xg_stability_error_patterns.csv"
DECISION_TXT = EVIDENCE_DIR / "139_1x2_v8_understat_xg_stability_decision.txt"

TARGET_CLASSES = ["HOME_WIN", "DRAW", "AWAY_WIN"]

REFERENCE_V6 = {
    "accuracy": 0.5205,
    "f1_macro": 0.4878,
    "draw_precision": 0.3166,
    "draw_recall": 0.2628,
}


@dataclass
class StabilityMetrics:
    rows: int
    accuracy: float
    f1_macro: float
    draw_precision: float
    draw_recall: float
    predicted_draw_rate: float
    actual_draw_rate: float


# Charge un CSV obligatoire et arrête clairement le script si le fichier est absent.
def load_required_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    return pd.read_csv(path)


# Charge le rapport JSON s'il existe pour enrichir la synthèse, sans rendre le script fragile.
def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# Convertit une valeur en float proprement, même si elle est absente ou non numérique.
def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


# Calcule la précision d'une classe donnée à partir des prédictions et de la cible réelle.
def class_precision(df: pd.DataFrame, class_name: str) -> float:
    predicted = df[df["predicted_result"] == class_name]
    if predicted.empty:
        return 0.0
    return float((predicted["target_result"] == class_name).mean())


# Calcule le recall d'une classe donnée à partir des prédictions et de la cible réelle.
def class_recall(df: pd.DataFrame, class_name: str) -> float:
    actual = df[df["target_result"] == class_name]
    if actual.empty:
        return 0.0
    return float((actual["predicted_result"] == class_name).mean())


# Calcule le F1 score d'une classe à partir de la précision et du recall.
def f1_from_precision_recall(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


# Calcule les métriques principales d'un segment.
def compute_metrics(df: pd.DataFrame) -> StabilityMetrics:
    rows = len(df)
    if rows == 0:
        return StabilityMetrics(
            rows=0,
            accuracy=0.0,
            f1_macro=0.0,
            draw_precision=0.0,
            draw_recall=0.0,
            predicted_draw_rate=0.0,
            actual_draw_rate=0.0,
        )

    accuracy = float((df["target_result"] == df["predicted_result"]).mean())
    f1_scores = []
    for class_name in TARGET_CLASSES:
        precision = class_precision(df, class_name)
        recall = class_recall(df, class_name)
        f1_scores.append(f1_from_precision_recall(precision, recall))

    draw_precision = class_precision(df, "DRAW")
    draw_recall = class_recall(df, "DRAW")
    predicted_draw_rate = float((df["predicted_result"] == "DRAW").mean())
    actual_draw_rate = float((df["target_result"] == "DRAW").mean())

    return StabilityMetrics(
        rows=rows,
        accuracy=accuracy,
        f1_macro=float(sum(f1_scores) / len(f1_scores)),
        draw_precision=draw_precision,
        draw_recall=draw_recall,
        predicted_draw_rate=predicted_draw_rate,
        actual_draw_rate=actual_draw_rate,
    )


# Ajoute les colonnes de confiance et de marge à partir des probabilités de classe.
def add_confidence_columns(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    prob_cols = ["prob_HOME_WIN", "prob_DRAW", "prob_AWAY_WIN"]

    for col in prob_cols:
        if col not in output.columns:
            raise ValueError(f"Colonne de probabilité manquante : {col}")

    output["max_probability"] = output[prob_cols].max(axis=1)
    output["second_probability"] = output[prob_cols].apply(lambda row: sorted(row, reverse=True)[1], axis=1)
    output["prediction_margin"] = output["max_probability"] - output["second_probability"]

    output["confidence_band"] = pd.cut(
        output["max_probability"],
        bins=[0.0, 0.45, 0.55, 0.65, 1.0],
        labels=["low_<0.45", "medium_0.45_0.55", "solid_0.55_0.65", "high_>=0.65"],
        include_lowest=True,
    ).astype(str)

    output["margin_band"] = pd.cut(
        output["prediction_margin"],
        bins=[-0.001, 0.05, 0.10, 0.20, 1.0],
        labels=["very_close_<=0.05", "close_0.05_0.10", "medium_0.10_0.20", "clear_>0.20"],
        include_lowest=True,
    ).astype(str)

    output["draw_probability_band"] = pd.cut(
        output["prob_DRAW"],
        bins=[0.0, 0.25, 0.33, 0.40, 1.0],
        labels=["draw_prob_<0.25", "draw_prob_0.25_0.33", "draw_prob_0.33_0.40", "draw_prob_>=0.40"],
        include_lowest=True,
    ).astype(str)

    return output


# Transforme des métriques en dictionnaire sérialisable pour les CSV.
def metrics_to_row(prefix: dict, metrics: StabilityMetrics) -> dict:
    row = dict(prefix)
    row.update(
        {
            "rows": metrics.rows,
            "accuracy": round(metrics.accuracy, 4),
            "f1_macro": round(metrics.f1_macro, 4),
            "draw_precision": round(metrics.draw_precision, 4),
            "draw_recall": round(metrics.draw_recall, 4),
            "predicted_draw_rate": round(metrics.predicted_draw_rate, 4),
            "actual_draw_rate": round(metrics.actual_draw_rate, 4),
        }
    )
    return row


# Produit l'analyse de stabilité par ligue et saison.
def build_league_season_stability(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_cols = ["league_code", "season"]

    for keys, group in df.groupby(group_cols, dropna=False):
        league_code, season = keys
        metrics = compute_metrics(group)
        status = "STABLE_REVIEW_OK"
        if metrics.rows < 250:
            status = "LOW_SAMPLE_REVIEW"
        elif metrics.accuracy < 0.47 or metrics.f1_macro < 0.45:
            status = "PERFORMANCE_REVIEW_NEEDED"
        elif metrics.predicted_draw_rate > 0.40:
            status = "DRAW_OVERPREDICTION_REVIEW"

        rows.append(
            metrics_to_row(
                {"league_code": league_code, "season": season, "segment_status": status},
                metrics,
            )
        )

    return pd.DataFrame(rows).sort_values(["league_code", "season"])


# Produit l'analyse par niveau de confiance et marge de prédiction.
def build_confidence_stability(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group_cols in [["confidence_band"], ["margin_band"], ["confidence_band", "margin_band"]]:
        for keys, group in df.groupby(group_cols, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            prefix = {"segment_type": "+".join(group_cols)}
            for col_name, value in zip(group_cols, keys):
                prefix[col_name] = value
            metrics = compute_metrics(group)
            rows.append(metrics_to_row(prefix, metrics))

    return pd.DataFrame(rows).sort_values(["segment_type", "rows"], ascending=[True, False])


# Produit une analyse ciblée sur les matchs nuls réels et les prédictions DRAW.
def build_draw_segments(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    segment_definitions = [
        ("actual_DRAW_by_league", df[df["target_result"] == "DRAW"], ["league_code"]),
        ("actual_DRAW_by_confidence", df[df["target_result"] == "DRAW"], ["confidence_band"]),
        ("actual_DRAW_by_draw_probability", df[df["target_result"] == "DRAW"], ["draw_probability_band"]),
        ("predicted_DRAW_by_league", df[df["predicted_result"] == "DRAW"], ["league_code"]),
        ("predicted_DRAW_by_confidence", df[df["predicted_result"] == "DRAW"], ["confidence_band"]),
        ("predicted_DRAW_by_margin", df[df["predicted_result"] == "DRAW"], ["margin_band"]),
    ]

    for segment_type, segment_df, group_cols in segment_definitions:
        if segment_df.empty:
            continue
        for keys, group in segment_df.groupby(group_cols, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            prefix = {"segment_type": segment_type}
            for col_name, value in zip(group_cols, keys):
                prefix[col_name] = value
            metrics = compute_metrics(group)
            rows.append(metrics_to_row(prefix, metrics))

    return pd.DataFrame(rows).sort_values(["segment_type", "rows"], ascending=[True, False])


# Produit les erreurs fréquentes et les échantillons d'erreurs à forte confiance.
def build_error_patterns(df: pd.DataFrame) -> pd.DataFrame:
    errors = df[df["target_result"] != df["predicted_result"]].copy()
    rows = []

    if errors.empty:
        return pd.DataFrame(columns=["analysis_type", "target_result", "predicted_result", "rows"])

    confusion = (
        errors.groupby(["target_result", "predicted_result"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values("rows", ascending=False)
    )

    for _, row in confusion.iterrows():
        rows.append(
            {
                "analysis_type": "confusion_pair",
                "target_result": row["target_result"],
                "predicted_result": row["predicted_result"],
                "rows": int(row["rows"]),
                "league_code": "",
                "season": "",
                "confidence_band": "",
                "margin_band": "",
                "sample_match": "",
                "max_probability": "",
            }
        )

    high_confidence_errors = errors.sort_values("max_probability", ascending=False).head(25)
    for _, row in high_confidence_errors.iterrows():
        rows.append(
            {
                "analysis_type": "high_confidence_error_sample",
                "target_result": row.get("target_result", ""),
                "predicted_result": row.get("predicted_result", ""),
                "rows": 1,
                "league_code": row.get("league_code", ""),
                "season": row.get("season", ""),
                "confidence_band": row.get("confidence_band", ""),
                "margin_band": row.get("margin_band", ""),
                "sample_match": f"{row.get('match_date', '')} | {row.get('home_team', '')} - {row.get('away_team', '')}",
                "max_probability": round(safe_float(row.get("max_probability", 0.0)), 4),
            }
        )

    return pd.DataFrame(rows)


# Détermine le statut global de stabilité à partir des métriques et de la référence V6.
def determine_status(metrics: StabilityMetrics) -> str:
    accuracy_delta = metrics.accuracy - REFERENCE_V6["accuracy"]
    f1_delta = metrics.f1_macro - REFERENCE_V6["f1_macro"]
    draw_recall_delta = metrics.draw_recall - REFERENCE_V6["draw_recall"]

    if accuracy_delta >= 0 and f1_delta >= 0:
        return "V8_UNDERSTAT_XG_STABILITY_GLOBAL_CANDIDATE"
    if f1_delta > 0 and draw_recall_delta > 0.05:
        return "V8_UNDERSTAT_XG_STABILITY_SELECTIVE_DRAW_GAIN"
    return "V8_UNDERSTAT_XG_STABILITY_REVIEW_NEEDED"


# Crée le texte de synthèse principal de l'analyse de stabilité.
def write_summary(
    df: pd.DataFrame,
    metrics: StabilityMetrics,
    status: str,
    league_season_df: pd.DataFrame,
    confidence_df: pd.DataFrame,
    draw_df: pd.DataFrame,
    error_df: pd.DataFrame,
) -> None:
    accuracy_delta = metrics.accuracy - REFERENCE_V6["accuracy"]
    f1_delta = metrics.f1_macro - REFERENCE_V6["f1_macro"]
    draw_precision_delta = metrics.draw_precision - REFERENCE_V6["draw_precision"]
    draw_recall_delta = metrics.draw_recall - REFERENCE_V6["draw_recall"]

    lines = [
        "RubyBets - ML 1X2 V8 Understat xG stability",
        "134 - Synthese analyse de stabilite V8 rolling xG",
        "",
        "Objectif :",
        "Analyser les performances de la meilleure strategie V8 par ligue, saison, classe et niveau de confiance.",
        "",
        "Garde-fous respectes :",
        "- Aucune modification de PostgreSQL.",
        "- Aucune modification de ml.features.",
        "- Aucune modification de l'API, du frontend, du scoring V1 ou des modeles sauvegardes.",
        "- Aucune integration produit d'Understat.",
        "- Analyse de stabilite interne uniquement.",
        "",
        "Fichier de predictions utilise :",
        f"- {PREDICTIONS_CSV}",
        "",
        "Resultat global V8 :",
        f"- Rows analysed : {metrics.rows}",
        f"- Accuracy : {metrics.accuracy:.4f}",
        f"- F1 macro : {metrics.f1_macro:.4f}",
        f"- DRAW precision : {metrics.draw_precision:.4f}",
        f"- DRAW recall : {metrics.draw_recall:.4f}",
        f"- Predicted DRAW rate : {metrics.predicted_draw_rate:.4f}",
        f"- Actual DRAW rate : {metrics.actual_draw_rate:.4f}",
        f"- Status : {status}",
        "",
        "Comparaison reference V6 globale observee :",
        f"- Accuracy delta vs V6 : {accuracy_delta:.4f}",
        f"- F1 macro delta vs V6 : {f1_delta:.4f}",
        f"- DRAW precision delta vs V6 : {draw_precision_delta:.4f}",
        f"- DRAW recall delta vs V6 : {draw_recall_delta:.4f}",
        "",
        "Lecture :",
        "- V8 ne doit pas etre consideree comme candidat officiel global tant que l'accuracy reste sous V6.",
        "- V8 apporte cependant un gain selectif sur le rappel des matchs nuls, utile pour comprendre le signal xG.",
        "- Une analyse par segments est necessaire avant toute integration dans ml.features.",
        "",
        "Fichiers generes :",
        f"- {SUMMARY_TXT}",
        f"- {LEAGUE_SEASON_CSV}",
        f"- {CONFIDENCE_CSV}",
        f"- {DRAW_SEGMENTS_CSV}",
        f"- {ERROR_PATTERNS_CSV}",
        f"- {DECISION_TXT}",
        "",
        "Apercu segments :",
        f"- League/season rows : {len(league_season_df)}",
        f"- Confidence segment rows : {len(confidence_df)}",
        f"- DRAW segment rows : {len(draw_df)}",
        f"- Error pattern rows : {len(error_df)}",
        "",
        "Statut de suivi :",
        "- Tache realisee si les fichiers 134, 135, 136, 137, 138 et 139 sont generes.",
        "- Statut source a mettre a jour : a produire -> realise pour l'analyse de stabilite V8 Understat xG.",
    ]

    SUMMARY_TXT.write_text("\n".join(lines), encoding="utf-8")


# Crée le fichier de décision de l'analyse de stabilité V8.
def write_decision(metrics: StabilityMetrics, status: str) -> None:
    lines = [
        "RubyBets - ML 1X2 V8 Understat xG stability",
        "139 - Decision analyse de stabilite V8",
        "",
        f"Status : {status}",
        "",
        "Decision :",
        "Les features rolling xG Understat restent pertinentes comme signal experimental, mais elles ne doivent pas encore devenir une V8 officielle.",
        "",
        "Justification :",
        f"- Accuracy V8 : {metrics.accuracy:.4f}",
        f"- Accuracy reference V6 : {REFERENCE_V6['accuracy']:.4f}",
        f"- F1 macro V8 : {metrics.f1_macro:.4f}",
        f"- F1 macro reference V6 : {REFERENCE_V6['f1_macro']:.4f}",
        f"- DRAW recall V8 : {metrics.draw_recall:.4f}",
        f"- DRAW recall reference V6 : {REFERENCE_V6['draw_recall']:.4f}",
        "",
        "Conclusion :",
        "- V8 apporte un gain selectif sur les matchs nuls.",
        "- V8 ne remplace pas V6 sur la performance globale.",
        "- La prochaine etape utile est une analyse de filtrage ou de gating : utiliser le signal xG uniquement sur les segments ou il ameliore vraiment la decision.",
        "",
        "Garde-fou :",
        "Ne pas modifier ml.features, ne pas sauvegarder de modele, ne pas brancher Understat a l'API ou au frontend.",
        "",
        "Prochaine action recommandee :",
        "Creer une experience V8.1 de gating selectif pour tester si les features xG doivent etre activees seulement sur certains profils de matchs.",
    ]

    DECISION_TXT.write_text("\n".join(lines), encoding="utf-8")


# Exécute l'analyse complète de stabilité V8.
def run_stability_analysis() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    print("Chargement des predictions V8 Understat xG...")
    predictions_df = load_required_csv(PREDICTIONS_CSV)
    _ = load_optional_json(REPORT_JSON)

    print(f"Predictions chargees: {len(predictions_df)}")
    print("Construction des segments de stabilite...")
    df = add_confidence_columns(predictions_df)

    metrics = compute_metrics(df)
    status = determine_status(metrics)

    league_season_df = build_league_season_stability(df)
    confidence_df = build_confidence_stability(df)
    draw_df = build_draw_segments(df)
    error_df = build_error_patterns(df)

    print("Generation des preuves CSV et synthese...")
    league_season_df.to_csv(LEAGUE_SEASON_CSV, index=False, encoding="utf-8")
    confidence_df.to_csv(CONFIDENCE_CSV, index=False, encoding="utf-8")
    draw_df.to_csv(DRAW_SEGMENTS_CSV, index=False, encoding="utf-8")
    error_df.to_csv(ERROR_PATTERNS_CSV, index=False, encoding="utf-8")

    write_summary(df, metrics, status, league_season_df, confidence_df, draw_df, error_df)
    write_decision(metrics, status)

    print("OK - Analyse de stabilite V8 Understat xG terminee.")
    print(f"Rows analysed: {metrics.rows}")
    print(f"Accuracy: {metrics.accuracy:.4f}")
    print(f"F1 macro: {metrics.f1_macro:.4f}")
    print(f"DRAW precision: {metrics.draw_precision:.4f}")
    print(f"DRAW recall: {metrics.draw_recall:.4f}")
    print(f"Status: {status}")
    print(f"Summary saved: {SUMMARY_TXT}")
    print(f"League/season CSV saved: {LEAGUE_SEASON_CSV}")
    print(f"Confidence CSV saved: {CONFIDENCE_CSV}")
    print(f"DRAW CSV saved: {DRAW_SEGMENTS_CSV}")
    print(f"Errors CSV saved: {ERROR_PATTERNS_CSV}")
    print(f"Decision saved: {DECISION_TXT}")


# Point d'entrée principal du script.
def main() -> None:
    try:
        run_stability_analysis()
    except Exception as exc:
        print("Erreur pendant l'analyse de stabilite V8 Understat xG.")
        print(str(exc))
        raise


if __name__ == "__main__":
    main()


# Schema de communication du fichier :
# train_1x2_v8_understat_xg_in_memory_v2.py
#   -> reports/evidence/ml_training/131_...best_predictions.csv
#   -> ce script analyse les predictions V8 en dry-run
#   -> reports/evidence/ml_training/134_...summary.txt
#   -> reports/evidence/ml_training/135_...by_league_season.csv
#   -> reports/evidence/ml_training/136_...by_confidence.csv
#   -> reports/evidence/ml_training/137_...draw_segments.csv
#   -> reports/evidence/ml_training/138_...error_patterns.csv
#   -> reports/evidence/ml_training/139_...decision.txt
# Aucune ecriture PostgreSQL / ml.features / API / frontend / models.
