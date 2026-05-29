# Rôle du fichier : analyser les erreurs des prédictions ML 1X2 V3 à forte confiance afin d'identifier les segments où le modèle se trompe le plus.

from pathlib import Path
import sys

import pandas as pd



# Retrouve la racine du projet RubyBets, même si le script est déplacé ou testé hors du dossier backend.
def resolve_project_root() -> Path:
    current_path = Path(__file__).resolve()

    for parent in [current_path.parent, *current_path.parents]:
        if (parent / "reports" / "evidence" / "ml_training").exists():
            return parent

        if parent.name.lower() == "rubybets":
            return parent

    if len(current_path.parents) > 3:
        return current_path.parents[3]

    return current_path.parent


PROJECT_ROOT = resolve_project_root()
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"
INPUT_CSV_PATH = REPORT_DIR / "53_1x2_v3_high_confidence_predictions.csv"
SEGMENTS_OUTPUT_PATH = REPORT_DIR / "56_1x2_v3_error_segments.csv"
SUMMARY_OUTPUT_PATH = REPORT_DIR / "55_1x2_v3_error_segments_summary.txt"

EXPECTED_COLUMNS = [
    "clean_match_id",
    "match_date",
    "league_code",
    "season",
    "match",
    "actual_result",
    "predicted_result",
    "prob_home_win",
    "prob_draw",
    "prob_away_win",
    "max_probability",
    "correct",
]

CLASS_LABELS = ["HOME_WIN", "DRAW", "AWAY_WIN"]

MIN_ROWS_FOR_RELIABLE_SEGMENT = 20


# Vérifie que le fichier d'entrée 53 existe et que les colonnes minimales sont disponibles.
def validate_input_file() -> None:
    if not INPUT_CSV_PATH.exists():
        raise FileNotFoundError(
            "Le fichier 53 est introuvable. Lance d'abord export_1x2_v3_high_confidence_predictions.py. "
            f"Chemin attendu : {INPUT_CSV_PATH}"
        )


# Charge les prédictions forte confiance V3 et normalise les types utiles pour l'analyse.
def load_high_confidence_predictions() -> pd.DataFrame:
    validate_input_file()
    dataframe = pd.read_csv(INPUT_CSV_PATH, encoding="utf-8-sig")
    missing_columns = [column for column in EXPECTED_COLUMNS if column not in dataframe.columns]

    if missing_columns:
        raise RuntimeError(f"Colonnes manquantes dans le fichier 53 : {missing_columns}")

    dataframe = dataframe.copy()
    dataframe["match_date"] = pd.to_datetime(dataframe["match_date"], errors="coerce")

    for column in ["prob_home_win", "prob_draw", "prob_away_win", "max_probability"]:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    dataframe["correct"] = dataframe["correct"].astype(str).str.lower().isin(["true", "1", "yes"])
    dataframe["error"] = ~dataframe["correct"]
    dataframe["is_actual_draw"] = dataframe["actual_result"] == "DRAW"
    dataframe["is_predicted_draw"] = dataframe["predicted_result"] == "DRAW"
    dataframe["draw_missed"] = dataframe["is_actual_draw"] & ~dataframe["is_predicted_draw"]
    dataframe["top_probability_gap_vs_draw"] = dataframe["max_probability"] - dataframe["prob_draw"]

    if "home_away_context_diff" in dataframe.columns:
        dataframe["abs_home_away_context_diff"] = pd.to_numeric(
            dataframe["home_away_context_diff"], errors="coerce"
        ).abs()

    if "team_strength_diff" in dataframe.columns:
        dataframe["abs_signed_team_strength_diff"] = pd.to_numeric(
            dataframe["team_strength_diff"], errors="coerce"
        ).abs()

    return dataframe


# Ajoute des bandes lisibles pour analyser la confiance, le risque de nul et certains écarts entre équipes.
def add_analysis_bands(dataframe: pd.DataFrame) -> pd.DataFrame:
    working_dataframe = dataframe.copy()

    working_dataframe["confidence_band"] = pd.cut(
        working_dataframe["max_probability"],
        bins=[0.0, 0.62, 0.70, 0.80, 0.90, 1.01],
        labels=["<0.62", "0.62-0.70", "0.70-0.80", "0.80-0.90", "0.90-1.00"],
        include_lowest=True,
    ).astype(str)

    working_dataframe["prob_draw_band"] = pd.cut(
        working_dataframe["prob_draw"],
        bins=[-0.001, 0.05, 0.10, 0.15, 0.20, 0.30, 1.01],
        labels=["0.00-0.05", "0.05-0.10", "0.10-0.15", "0.15-0.20", "0.20-0.30", "0.30-1.00"],
        include_lowest=True,
    ).astype(str)

    working_dataframe["top_probability_gap_vs_draw_band"] = pd.cut(
        working_dataframe["top_probability_gap_vs_draw"],
        bins=[-0.001, 0.30, 0.45, 0.60, 0.75, 1.01],
        labels=["0.00-0.30", "0.30-0.45", "0.45-0.60", "0.60-0.75", "0.75-1.00"],
        include_lowest=True,
    ).astype(str)

    add_quantile_band(
        dataframe=working_dataframe,
        source_column="abs_team_strength_diff",
        target_column="abs_team_strength_diff_band",
        labels=["low_strength_gap", "medium_strength_gap", "high_strength_gap"],
    )

    add_quantile_band(
        dataframe=working_dataframe,
        source_column="draw_profile_score_with_strength",
        target_column="draw_profile_score_band",
        labels=["low_draw_profile", "medium_draw_profile", "high_draw_profile"],
    )

    add_quantile_band(
        dataframe=working_dataframe,
        source_column="abs_home_away_context_diff",
        target_column="abs_home_away_context_diff_band",
        labels=["low_context_gap", "medium_context_gap", "high_context_gap"],
    )

    return working_dataframe


# Crée une bande par quantiles quand la colonne numérique existe et contient assez de valeurs différentes.
def add_quantile_band(dataframe: pd.DataFrame, source_column: str, target_column: str, labels: list[str]) -> None:
    if source_column not in dataframe.columns:
        dataframe[target_column] = "not_available"
        return

    numeric_values = pd.to_numeric(dataframe[source_column], errors="coerce")

    if numeric_values.nunique(dropna=True) < len(labels):
        dataframe[target_column] = "not_enough_variation"
        return

    dataframe[target_column] = pd.qcut(
        numeric_values,
        q=len(labels),
        labels=labels,
        duplicates="drop",
    ).astype(str)


# Calcule les indicateurs d'un segment : volume, accuracy, erreurs, nuls réels et probabilités moyennes.
def summarize_group(dataframe: pd.DataFrame, segment_type: str, segment_value: str) -> dict:
    rows = len(dataframe)
    correct_rows = int(dataframe["correct"].sum()) if rows else 0
    error_rows = rows - correct_rows
    actual_draw_rows = int((dataframe["actual_result"] == "DRAW").sum()) if rows else 0
    predicted_draw_rows = int((dataframe["predicted_result"] == "DRAW").sum()) if rows else 0
    draw_missed_rows = int(dataframe["draw_missed"].sum()) if rows else 0

    result = {
        "segment_type": segment_type,
        "segment_value": str(segment_value),
        "rows": rows,
        "correct_rows": correct_rows,
        "error_rows": error_rows,
        "accuracy": round(correct_rows / rows, 4) if rows else 0.0,
        "error_rate": round(error_rows / rows, 4) if rows else 0.0,
        "actual_draw_rows": actual_draw_rows,
        "actual_draw_rate": round(actual_draw_rows / rows, 4) if rows else 0.0,
        "predicted_draw_rows": predicted_draw_rows,
        "draw_missed_rows": draw_missed_rows,
        "draw_missed_rate": round(draw_missed_rows / rows, 4) if rows else 0.0,
        "predicted_home_win_rows": int((dataframe["predicted_result"] == "HOME_WIN").sum()) if rows else 0,
        "predicted_away_win_rows": int((dataframe["predicted_result"] == "AWAY_WIN").sum()) if rows else 0,
        "actual_home_win_rows": int((dataframe["actual_result"] == "HOME_WIN").sum()) if rows else 0,
        "actual_away_win_rows": int((dataframe["actual_result"] == "AWAY_WIN").sum()) if rows else 0,
        "avg_max_probability": safe_mean(dataframe, "max_probability"),
        "avg_prob_home_win": safe_mean(dataframe, "prob_home_win"),
        "avg_prob_draw": safe_mean(dataframe, "prob_draw"),
        "avg_prob_away_win": safe_mean(dataframe, "prob_away_win"),
        "avg_top_probability_gap_vs_draw": safe_mean(dataframe, "top_probability_gap_vs_draw"),
        "avg_abs_team_strength_diff": safe_mean(dataframe, "abs_team_strength_diff"),
        "avg_draw_profile_score_with_strength": safe_mean(dataframe, "draw_profile_score_with_strength"),
        "avg_abs_home_away_context_diff": safe_mean(dataframe, "abs_home_away_context_diff"),
    }

    return result


# Calcule une moyenne arrondie si la colonne existe, sinon retourne une valeur vide lisible.
def safe_mean(dataframe: pd.DataFrame, column: str):
    if column not in dataframe.columns or dataframe.empty:
        return ""

    value = pd.to_numeric(dataframe[column], errors="coerce").mean()

    if pd.isna(value):
        return ""

    return round(float(value), 4)


# Ajoute à la liste de résultats l'analyse d'un groupe de colonnes catégorielles.
def add_segment_rows(results: list[dict], dataframe: pd.DataFrame, column: str, segment_type: str) -> None:
    if column not in dataframe.columns:
        return

    for segment_value, group in dataframe.groupby(column, dropna=False):
        results.append(summarize_group(group, segment_type, segment_value))


# Construit le tableau complet des segments d'erreurs à partir du CSV 53.
def build_segments_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    results: list[dict] = []

    results.append(summarize_group(dataframe, "global", "all_high_confidence_predictions"))

    segment_columns = [
        ("league_code", "by_league"),
        ("season", "by_season"),
        ("actual_result", "by_actual_result"),
        ("predicted_result", "by_predicted_result"),
        ("confidence_band", "by_confidence_band"),
        ("prob_draw_band", "by_prob_draw_band"),
        ("top_probability_gap_vs_draw_band", "by_top_probability_gap_vs_draw_band"),
        ("abs_team_strength_diff_band", "by_abs_team_strength_diff_band"),
        ("draw_profile_score_band", "by_draw_profile_score_band"),
        ("abs_home_away_context_diff_band", "by_abs_home_away_context_diff_band"),
    ]

    dataframe["actual_predicted_pair"] = dataframe["actual_result"] + " -> " + dataframe["predicted_result"]
    segment_columns.append(("actual_predicted_pair", "by_actual_predicted_pair"))

    for column, segment_type in segment_columns:
        add_segment_rows(results, dataframe, column, segment_type)

    segments_dataframe = pd.DataFrame(results)
    segments_dataframe = segments_dataframe.sort_values(
        by=["segment_type", "rows", "error_rate"],
        ascending=[True, False, False],
    )

    return segments_dataframe


# Sélectionne les segments les plus fragiles pour les afficher dans le résumé texte.
def get_worst_reliable_segments(segments_dataframe: pd.DataFrame) -> pd.DataFrame:
    excluded_segment_types = {"global", "by_actual_result", "by_predicted_result", "by_actual_predicted_pair"}
    filtered_dataframe = segments_dataframe[
        (~segments_dataframe["segment_type"].isin(excluded_segment_types))
        & (segments_dataframe["rows"] >= MIN_ROWS_FOR_RELIABLE_SEGMENT)
    ].copy()

    return filtered_dataframe.sort_values(
        by=["accuracy", "rows"],
        ascending=[True, False],
    ).head(10)


# Sélectionne les segments qui concentrent le plus de vrais matchs nuls manqués.
def get_draw_risk_segments(segments_dataframe: pd.DataFrame) -> pd.DataFrame:
    excluded_segment_types = {"global", "by_actual_result", "by_predicted_result", "by_actual_predicted_pair"}
    filtered_dataframe = segments_dataframe[
        (~segments_dataframe["segment_type"].isin(excluded_segment_types))
        & (segments_dataframe["rows"] >= MIN_ROWS_FOR_RELIABLE_SEGMENT)
    ].copy()

    return filtered_dataframe.sort_values(
        by=["draw_missed_rows", "actual_draw_rate", "rows"],
        ascending=[False, False, False],
    ).head(10)


# Repère les exemples d'erreurs les plus confiantes pour comprendre les cas les plus dangereux.
def get_top_confident_errors(dataframe: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "clean_match_id",
        "match_date",
        "league_code",
        "season",
        "match",
        "actual_result",
        "predicted_result",
        "max_probability",
        "prob_home_win",
        "prob_draw",
        "prob_away_win",
        "team_strength_diff",
        "home_away_context_diff",
        "draw_profile_score_with_strength",
    ]
    available_columns = [column for column in columns if column in dataframe.columns]

    return dataframe[dataframe["error"]].sort_values(
        by="max_probability",
        ascending=False,
    )[available_columns].head(10)


# Transforme un tableau court en lignes texte faciles à lire dans le fichier de synthèse.
def dataframe_to_summary_lines(dataframe: pd.DataFrame, columns: list[str]) -> list[str]:
    if dataframe.empty:
        return ["- Aucun segment disponible."]

    lines = []

    for _, row in dataframe.iterrows():
        parts = [f"{column}={row[column]}" for column in columns if column in dataframe.columns]
        lines.append("- " + " | ".join(parts))

    return lines


# Construit le résumé lisible du diagnostic des erreurs V3.
def build_summary(dataframe: pd.DataFrame, segments_dataframe: pd.DataFrame) -> str:
    total_rows = len(dataframe)
    correct_rows = int(dataframe["correct"].sum())
    error_rows = total_rows - correct_rows
    accuracy = correct_rows / total_rows if total_rows else 0
    actual_draw_rows = int((dataframe["actual_result"] == "DRAW").sum())
    predicted_draw_rows = int((dataframe["predicted_result"] == "DRAW").sum())
    draw_missed_rows = int(dataframe["draw_missed"].sum())

    wrong_draws = dataframe[dataframe["draw_missed"]]
    wrong_draws_as_home = int((wrong_draws["predicted_result"] == "HOME_WIN").sum())
    wrong_draws_as_away = int((wrong_draws["predicted_result"] == "AWAY_WIN").sum())

    worst_segments = get_worst_reliable_segments(segments_dataframe)
    draw_risk_segments = get_draw_risk_segments(segments_dataframe)
    top_confident_errors = get_top_confident_errors(dataframe)

    confusion_table = pd.crosstab(
        dataframe["actual_result"],
        dataframe["predicted_result"],
        dropna=False,
    ).reindex(index=CLASS_LABELS, columns=CLASS_LABELS, fill_value=0)

    lines = [
        "RubyBets - ML 1X2 V3 high-confidence error diagnosis",
        "55 - Synthese des segments d'erreurs V3",
        "",
        "Positionnement :",
        "Ce diagnostic analyse les erreurs du fichier 53, sans réentraîner le modèle et sans modifier PostgreSQL, l'API, le frontend ou les modèles sauvegardés.",
        "Il sert à décider la prochaine action ML utile, au lieu d'ajouter des features au hasard.",
        "",
        "Fichier analysé :",
        f"- Input : {INPUT_CSV_PATH.relative_to(PROJECT_ROOT)}",
        f"- Output summary : {SUMMARY_OUTPUT_PATH.relative_to(PROJECT_ROOT)}",
        f"- Output CSV : {SEGMENTS_OUTPUT_PATH.relative_to(PROJECT_ROOT)}",
        "",
        "Résultat global forte confiance V3 :",
        f"- Selected rows : {total_rows}",
        f"- Correct rows : {correct_rows}",
        f"- Error rows : {error_rows}",
        f"- Accuracy : {accuracy:.4f}",
        f"- Actual DRAW rows : {actual_draw_rows}",
        f"- Predicted DRAW rows : {predicted_draw_rows}",
        f"- Missed DRAW rows : {draw_missed_rows}",
        f"- Missed DRAW predicted as HOME_WIN : {wrong_draws_as_home}",
        f"- Missed DRAW predicted as AWAY_WIN : {wrong_draws_as_away}",
        "",
        "Matrice de confusion forte confiance :",
        confusion_table.to_string(),
        "",
        "Segments fiables avec la plus faible accuracy :",
        *dataframe_to_summary_lines(
            worst_segments,
            [
                "segment_type",
                "segment_value",
                "rows",
                "accuracy",
                "error_rate",
                "actual_draw_rows",
                "actual_draw_rate",
                "avg_max_probability",
            ],
        ),
        "",
        "Segments qui concentrent le plus de nuls réels manqués :",
        *dataframe_to_summary_lines(
            draw_risk_segments,
            [
                "segment_type",
                "segment_value",
                "rows",
                "draw_missed_rows",
                "actual_draw_rate",
                "accuracy",
                "avg_prob_draw",
                "avg_top_probability_gap_vs_draw",
            ],
        ),
        "",
        "Top erreurs les plus confiantes :",
        *dataframe_to_summary_lines(
            top_confident_errors,
            [
                "clean_match_id",
                "match_date",
                "league_code",
                "season",
                "match",
                "actual_result",
                "predicted_result",
                "max_probability",
                "prob_draw",
            ],
        ),
        "",
        "Lecture métier :",
        "- Le signal forte confiance V3 est utile pour isoler des matchs plus fiables que le modèle général.",
        "- La limite principale reste l'absence de prédiction DRAW : les vrais nuls sélectionnés deviennent automatiquement des erreurs.",
        "- La prochaine étape pertinente n'est pas d'ajouter encore des moyennes last_10, mais de créer un filtre de risque de nul.",
        "- Ce filtre devra exclure ou dégrader les matchs où le risque DRAW est élevé avant d'appliquer la sélection forte confiance.",
        "",
        "Décision recommandée :",
        "Créer un script experiment_1x2_draw_risk_gate.py pour tester un filtre de risque DRAW sur les prédictions forte confiance V3.",
        "",
        "Statut de suivi :",
        "- Tâche réalisée : diagnostic des erreurs V3 forte confiance.",
        "- Statut source à mettre à jour : réalisé si les fichiers 55 et 56 sont générés.",
        "- Fichiers concernés : reports/evidence/ml_training/55 et 56.",
        "",
    ]

    return "\n".join(lines)


# Sauvegarde le résumé TXT et le tableau CSV des segments dans reports/evidence/ml_training.
def save_reports(summary: str, segments_dataframe: pd.DataFrame) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUTPUT_PATH.write_text(summary, encoding="utf-8")
    segments_dataframe.to_csv(SEGMENTS_OUTPUT_PATH, index=False, encoding="utf-8-sig")


# Orchestre le diagnostic des erreurs forte confiance V3.
def main() -> None:
    try:
        print("Chargement des predictions forte confiance V3...", flush=True)
        predictions_dataframe = load_high_confidence_predictions()
        print(f"Predictions chargees : {len(predictions_dataframe)}", flush=True)

        print("Construction des segments d'analyse...", flush=True)
        predictions_dataframe = add_analysis_bands(predictions_dataframe)
        segments_dataframe = build_segments_dataframe(predictions_dataframe)

        print("Generation du resume de diagnostic...", flush=True)
        summary = build_summary(predictions_dataframe, segments_dataframe)
        save_reports(summary, segments_dataframe)

        total_rows = len(predictions_dataframe)
        correct_rows = int(predictions_dataframe["correct"].sum())
        error_rows = total_rows - correct_rows
        actual_draw_rows = int((predictions_dataframe["actual_result"] == "DRAW").sum())
        predicted_draw_rows = int((predictions_dataframe["predicted_result"] == "DRAW").sum())
        draw_missed_rows = int(predictions_dataframe["draw_missed"].sum())

        print("OK - Diagnostic des erreurs V3 termine.", flush=True)
        print(f"Selected rows analysed: {total_rows}", flush=True)
        print(f"Correct rows: {correct_rows}", flush=True)
        print(f"Error rows: {error_rows}", flush=True)
        print(f"Actual DRAW rows: {actual_draw_rows}", flush=True)
        print(f"Predicted DRAW rows: {predicted_draw_rows}", flush=True)
        print(f"Missed DRAW rows: {draw_missed_rows}", flush=True)
        print("Summary saved: reports/evidence/ml_training/55_1x2_v3_error_segments_summary.txt", flush=True)
        print("CSV saved: reports/evidence/ml_training/56_1x2_v3_error_segments.csv", flush=True)

    except Exception as error:
        print("Erreur pendant le diagnostic des erreurs V3.", flush=True)
        print(error, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# Schéma de communication du fichier :
# analyze_1x2_v3_error_segments.py
# ├── lit reports/evidence/ml_training/53_1x2_v3_high_confidence_predictions.csv
# ├── analyse les erreurs par ligue, saison, classe, confiance et profils DRAW
# ├── ne lit pas PostgreSQL et ne réentraîne aucun modèle
# ├── ne modifie pas ml.features, l'API, le frontend ou models/ml/1x2/
# ├── écrit reports/evidence/ml_training/55_1x2_v3_error_segments_summary.txt
# └── écrit reports/evidence/ml_training/56_1x2_v3_error_segments.csv
