# Rôle du fichier : analyser la stabilité du candidat V5 1X2 par rapport à la V2, sans modifier la base, l’API, le frontend ou les modèles sauvegardés.

from pathlib import Path
import sys
import warnings

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = PROJECT_ROOT / "reports" / "evidence" / "ml_training"

SUMMARY_PATH = REPORT_DIR / "71_1x2_v5_candidate_stability_summary.txt"
STABILITY_CSV_PATH = REPORT_DIR / "72_1x2_v5_candidate_stability.csv"
ERROR_SEGMENTS_CSV_PATH = REPORT_DIR / "73_1x2_v5_candidate_error_segments.csv"

sys.path.append(str(SCRIPT_DIR))

from compare_1x2_feature_sets import (  # noqa: E402
    TARGET_COLUMN,
    TEST_SEASONS,
    ensure_report_dir,
    fetch_clean_matches,
    get_database_url,
)
from experiment_1x2_v5_balance_features import (  # noqa: E402
    CLASS_LABELS,
    V2_REFERENCE_MODEL_NAME,
    add_v5_balance_features,
    build_reference_model,
    build_v5_feature_sets,
    build_v2_fast_feature_dataframe,
    prepare_train_test,
)

warnings.filterwarnings("ignore", category=UserWarning)

V2_FEATURE_SET_NAME = "v2_reference"
V5_FEATURE_SET_NAME = "v5_draw_context_scores"

MIN_SAVE_READY_ACCURACY_GAIN = 0.0030
MIN_SAVE_READY_F1_MACRO_GAIN = 0.0030
MAX_ALLOWED_LEAGUE_ACCURACY_DROP = -0.0100
MAX_ALLOWED_SEASON_ACCURACY_DROP = -0.0100


# Arrondit une valeur numérique pour stabiliser les exports.
def rounded(value: float | int | None, digits: int = 4) -> float:
    if value is None:
        return 0.0

    return round(float(value), digits)


# Convertit un booléen en entier pour faciliter la lecture des CSV.
def bool_to_int(value: bool) -> int:
    return 1 if value else 0


# Calcule les métriques 1X2 principales pour une série de prédictions.
def compute_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict:
    report = classification_report(
        y_true,
        y_pred,
        labels=CLASS_LABELS,
        output_dict=True,
        zero_division=0,
    )

    prediction_distribution = y_pred.value_counts().to_dict()

    return {
        "accuracy": rounded(accuracy_score(y_true, y_pred)),
        "f1_macro": rounded(f1_score(y_true, y_pred, average="macro")),
        "f1_weighted": rounded(f1_score(y_true, y_pred, average="weighted")),
        "home_win_precision": rounded(report["HOME_WIN"]["precision"]),
        "home_win_recall": rounded(report["HOME_WIN"]["recall"]),
        "draw_precision": rounded(report["DRAW"]["precision"]),
        "draw_recall": rounded(report["DRAW"]["recall"]),
        "away_win_precision": rounded(report["AWAY_WIN"]["precision"]),
        "away_win_recall": rounded(report["AWAY_WIN"]["recall"]),
        "predicted_home_win_rows": int(prediction_distribution.get("HOME_WIN", 0)),
        "predicted_draw_rows": int(prediction_distribution.get("DRAW", 0)),
        "predicted_away_win_rows": int(prediction_distribution.get("AWAY_WIN", 0)),
    }


# Entraîne un modèle pour un set de features et retourne les prédictions du test set.
def train_and_predict(feature_dataframe: pd.DataFrame, feature_set_name: str, feature_columns: list[str]) -> pd.DataFrame:
    x_train, y_train, x_test, y_test, _, _, test_dataframe = prepare_train_test(
        feature_dataframe=feature_dataframe,
        feature_columns=feature_columns,
    )

    model = build_reference_model()
    model.fit(x_train, y_train)

    predictions = pd.Series(model.predict(x_test), index=x_test.index, name=f"{feature_set_name}_prediction")

    probabilities_dataframe = pd.DataFrame(
        model.predict_proba(x_test),
        index=x_test.index,
        columns=[f"{feature_set_name}_proba_{label}" for label in model.classes_],
    )

    metadata_columns = [
        "clean_match_id",
        "match_date",
        "league_code",
        "season",
        "home_team",
        "away_team",
        TARGET_COLUMN,
    ]

    prediction_dataframe = test_dataframe[metadata_columns].copy()
    prediction_dataframe = prediction_dataframe.join(predictions)
    prediction_dataframe = prediction_dataframe.join(probabilities_dataframe)
    prediction_dataframe[f"{feature_set_name}_correct"] = (
        prediction_dataframe[f"{feature_set_name}_prediction"] == prediction_dataframe[TARGET_COLUMN]
    )

    return prediction_dataframe.reset_index(drop=True)


# Construit un tableau de comparaison ligne par ligne entre V2 et V5.
def build_comparison_dataframe(v2_predictions: pd.DataFrame, v5_predictions: pd.DataFrame) -> pd.DataFrame:
    v2_columns = [
        "clean_match_id",
        "v2_reference_prediction",
        "v2_reference_correct",
        "v2_reference_proba_HOME_WIN",
        "v2_reference_proba_DRAW",
        "v2_reference_proba_AWAY_WIN",
    ]
    v5_columns = [
        "clean_match_id",
        "v5_draw_context_scores_prediction",
        "v5_draw_context_scores_correct",
        "v5_draw_context_scores_proba_HOME_WIN",
        "v5_draw_context_scores_proba_DRAW",
        "v5_draw_context_scores_proba_AWAY_WIN",
    ]

    base_columns = [
        "clean_match_id",
        "match_date",
        "league_code",
        "season",
        "home_team",
        "away_team",
        TARGET_COLUMN,
    ]

    comparison_dataframe = v2_predictions[base_columns + v2_columns[1:]].merge(
        v5_predictions[v5_columns],
        on="clean_match_id",
        how="inner",
    )

    comparison_dataframe = comparison_dataframe.rename(
        columns={
            TARGET_COLUMN: "actual_result",
            "v2_reference_prediction": "v2_prediction",
            "v2_reference_correct": "v2_correct",
            "v2_reference_proba_HOME_WIN": "v2_proba_HOME_WIN",
            "v2_reference_proba_DRAW": "v2_proba_DRAW",
            "v2_reference_proba_AWAY_WIN": "v2_proba_AWAY_WIN",
            "v5_draw_context_scores_prediction": "v5_prediction",
            "v5_draw_context_scores_correct": "v5_correct",
            "v5_draw_context_scores_proba_HOME_WIN": "v5_proba_HOME_WIN",
            "v5_draw_context_scores_proba_DRAW": "v5_proba_DRAW",
            "v5_draw_context_scores_proba_AWAY_WIN": "v5_proba_AWAY_WIN",
        }
    )

    comparison_dataframe["prediction_changed"] = (
        comparison_dataframe["v2_prediction"] != comparison_dataframe["v5_prediction"]
    )
    comparison_dataframe["v5_corrected_error"] = (
        (~comparison_dataframe["v2_correct"]) & (comparison_dataframe["v5_correct"])
    )
    comparison_dataframe["v5_created_error"] = (
        (comparison_dataframe["v2_correct"]) & (~comparison_dataframe["v5_correct"])
    )
    comparison_dataframe["both_correct"] = (
        comparison_dataframe["v2_correct"] & comparison_dataframe["v5_correct"]
    )
    comparison_dataframe["both_wrong"] = (
        (~comparison_dataframe["v2_correct"]) & (~comparison_dataframe["v5_correct"])
    )
    comparison_dataframe["prediction_transition"] = (
        comparison_dataframe["v2_prediction"] + " -> " + comparison_dataframe["v5_prediction"]
    )
    comparison_dataframe["v5_draw_probability_delta"] = (
        comparison_dataframe["v5_proba_DRAW"] - comparison_dataframe["v2_proba_DRAW"]
    ).round(6)

    return comparison_dataframe


# Calcule les métriques comparées V2/V5 pour un segment donné.
def build_segment_row(segment_family: str, segment_value: str, segment_dataframe: pd.DataFrame) -> dict:
    y_true = segment_dataframe["actual_result"]
    v2_predictions = segment_dataframe["v2_prediction"]
    v5_predictions = segment_dataframe["v5_prediction"]

    v2_metrics = compute_metrics(y_true, v2_predictions)
    v5_metrics = compute_metrics(y_true, v5_predictions)

    changed_rows = int(segment_dataframe["prediction_changed"].sum())
    corrected_rows = int(segment_dataframe["v5_corrected_error"].sum())
    created_error_rows = int(segment_dataframe["v5_created_error"].sum())

    return {
        "segment_family": segment_family,
        "segment_value": segment_value,
        "rows": int(len(segment_dataframe)),
        "actual_home_win_rows": int((segment_dataframe["actual_result"] == "HOME_WIN").sum()),
        "actual_draw_rows": int((segment_dataframe["actual_result"] == "DRAW").sum()),
        "actual_away_win_rows": int((segment_dataframe["actual_result"] == "AWAY_WIN").sum()),
        "v2_accuracy": v2_metrics["accuracy"],
        "v5_accuracy": v5_metrics["accuracy"],
        "accuracy_delta": rounded(v5_metrics["accuracy"] - v2_metrics["accuracy"]),
        "v2_f1_macro": v2_metrics["f1_macro"],
        "v5_f1_macro": v5_metrics["f1_macro"],
        "f1_macro_delta": rounded(v5_metrics["f1_macro"] - v2_metrics["f1_macro"]),
        "v2_draw_precision": v2_metrics["draw_precision"],
        "v5_draw_precision": v5_metrics["draw_precision"],
        "draw_precision_delta": rounded(v5_metrics["draw_precision"] - v2_metrics["draw_precision"]),
        "v2_draw_recall": v2_metrics["draw_recall"],
        "v5_draw_recall": v5_metrics["draw_recall"],
        "draw_recall_delta": rounded(v5_metrics["draw_recall"] - v2_metrics["draw_recall"]),
        "v2_predicted_draw_rows": v2_metrics["predicted_draw_rows"],
        "v5_predicted_draw_rows": v5_metrics["predicted_draw_rows"],
        "predicted_draw_delta": int(v5_metrics["predicted_draw_rows"] - v2_metrics["predicted_draw_rows"]),
        "changed_predictions": changed_rows,
        "changed_predictions_rate": rounded(changed_rows / len(segment_dataframe)),
        "v5_corrected_errors": corrected_rows,
        "v5_created_errors": created_error_rows,
        "net_correct_rows_delta": int(corrected_rows - created_error_rows),
        "both_correct_rows": int(segment_dataframe["both_correct"].sum()),
        "both_wrong_rows": int(segment_dataframe["both_wrong"].sum()),
    }


# Génère les lignes de stabilité par famille de segment.
def build_stability_rows(comparison_dataframe: pd.DataFrame) -> list[dict]:
    rows = [
        build_segment_row("overall", "all_test_matches", comparison_dataframe),
    ]

    for league_code, group in comparison_dataframe.groupby("league_code"):
        rows.append(build_segment_row("league", str(league_code), group))

    for season, group in comparison_dataframe.groupby("season"):
        rows.append(build_segment_row("season", str(season), group))

    for actual_result, group in comparison_dataframe.groupby("actual_result"):
        rows.append(build_segment_row("actual_result", str(actual_result), group))

    return rows


# Génère les segments d'erreurs et de transitions pour comprendre ce que V5 change réellement.
def build_error_segment_rows(comparison_dataframe: pd.DataFrame) -> list[dict]:
    rows = []

    for transition, group in comparison_dataframe.groupby("prediction_transition"):
        rows.append(build_segment_row("prediction_transition", str(transition), group))

    changed_dataframe = comparison_dataframe[comparison_dataframe["prediction_changed"]].copy()
    if not changed_dataframe.empty:
        rows.append(build_segment_row("changed_predictions_only", "all_changed_predictions", changed_dataframe))

    corrected_dataframe = comparison_dataframe[comparison_dataframe["v5_corrected_error"]].copy()
    if not corrected_dataframe.empty:
        rows.append(build_segment_row("v5_corrected_errors_only", "errors_corrected_by_v5", corrected_dataframe))

    created_error_dataframe = comparison_dataframe[comparison_dataframe["v5_created_error"]].copy()
    if not created_error_dataframe.empty:
        rows.append(build_segment_row("v5_created_errors_only", "errors_created_by_v5", created_error_dataframe))

    for (league_code, season), group in comparison_dataframe.groupby(["league_code", "season"]):
        rows.append(build_segment_row("league_season", f"{league_code}_{season}", group))

    return rows


# Détermine si le gain V5 est assez solide pour préparer une sauvegarde candidate.
def decide_v5_status(stability_dataframe: pd.DataFrame) -> dict:
    overall_row = stability_dataframe[
        (stability_dataframe["segment_family"] == "overall")
        & (stability_dataframe["segment_value"] == "all_test_matches")
    ].iloc[0]

    league_rows = stability_dataframe[stability_dataframe["segment_family"] == "league"]
    season_rows = stability_dataframe[stability_dataframe["segment_family"] == "season"]

    min_league_delta = float(league_rows["accuracy_delta"].min()) if not league_rows.empty else 0.0
    min_season_delta = float(season_rows["accuracy_delta"].min()) if not season_rows.empty else 0.0

    accuracy_gain_ok = overall_row["accuracy_delta"] >= MIN_SAVE_READY_ACCURACY_GAIN
    f1_gain_ok = overall_row["f1_macro_delta"] >= MIN_SAVE_READY_F1_MACRO_GAIN
    no_large_league_drop = min_league_delta >= MAX_ALLOWED_LEAGUE_ACCURACY_DROP
    no_large_season_drop = min_season_delta >= MAX_ALLOWED_SEASON_ACCURACY_DROP
    net_positive = overall_row["net_correct_rows_delta"] > 0

    save_ready = all(
        [
            accuracy_gain_ok,
            f1_gain_ok,
            no_large_league_drop,
            no_large_season_drop,
            net_positive,
        ]
    )

    return {
        "status": "V5_SAVE_CANDIDATE_READY" if save_ready else "V5_EXPERIMENTAL_ONLY",
        "accuracy_gain_ok": bool_to_int(accuracy_gain_ok),
        "f1_gain_ok": bool_to_int(f1_gain_ok),
        "no_large_league_drop": bool_to_int(no_large_league_drop),
        "no_large_season_drop": bool_to_int(no_large_season_drop),
        "net_positive": bool_to_int(net_positive),
        "min_league_accuracy_delta": rounded(min_league_delta),
        "min_season_accuracy_delta": rounded(min_season_delta),
    }


# Construit le résumé texte de l'analyse de stabilité V5.
def build_summary(
    comparison_dataframe: pd.DataFrame,
    stability_dataframe: pd.DataFrame,
    error_segments_dataframe: pd.DataFrame,
    decision: dict,
) -> str:
    overall_row = stability_dataframe[
        (stability_dataframe["segment_family"] == "overall")
        & (stability_dataframe["segment_value"] == "all_test_matches")
    ].iloc[0]

    league_rows = stability_dataframe[stability_dataframe["segment_family"] == "league"].sort_values(
        by="accuracy_delta",
        ascending=False,
    )
    season_rows = stability_dataframe[stability_dataframe["segment_family"] == "season"].sort_values(
        by="season" if "season" in stability_dataframe.columns else "segment_value"
    )

    top_error_segments = error_segments_dataframe.sort_values(
        by=["net_correct_rows_delta", "rows"],
        ascending=[False, False],
    ).head(10)

    lines = [
        "RubyBets - ML 1X2 V5 candidate stability analysis",
        "71 - Synthese de stabilite du candidat V5",
        "",
        "Objectif :",
        "Analyser si le candidat V5 v5_draw_context_scores apporte un gain stable par rapport a la V2, sans modifier PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modeles sauvegardes.",
        "",
        "Perimetre :",
        f"- Modele compare : {V2_REFERENCE_MODEL_NAME}",
        f"- Reference : {V2_FEATURE_SET_NAME}",
        f"- Candidat V5 : {V5_FEATURE_SET_NAME}",
        f"- Saisons test : {', '.join(TEST_SEASONS)}",
        "",
        "Resultat global V2 vs V5 :",
        f"- Rows analysed : {overall_row['rows']}",
        f"- V2 accuracy : {overall_row['v2_accuracy']}",
        f"- V5 accuracy : {overall_row['v5_accuracy']}",
        f"- Accuracy delta : {overall_row['accuracy_delta']}",
        f"- V2 F1 macro : {overall_row['v2_f1_macro']}",
        f"- V5 F1 macro : {overall_row['v5_f1_macro']}",
        f"- F1 macro delta : {overall_row['f1_macro_delta']}",
        f"- V2 DRAW precision : {overall_row['v2_draw_precision']}",
        f"- V5 DRAW precision : {overall_row['v5_draw_precision']}",
        f"- DRAW precision delta : {overall_row['draw_precision_delta']}",
        f"- V2 DRAW recall : {overall_row['v2_draw_recall']}",
        f"- V5 DRAW recall : {overall_row['v5_draw_recall']}",
        f"- DRAW recall delta : {overall_row['draw_recall_delta']}",
        f"- Changed predictions : {overall_row['changed_predictions']}",
        f"- V5 corrected errors : {overall_row['v5_corrected_errors']}",
        f"- V5 created errors : {overall_row['v5_created_errors']}",
        f"- Net correct rows delta : {overall_row['net_correct_rows_delta']}",
        "",
        "Stabilite par ligue :",
    ]

    for _, row in league_rows.iterrows():
        lines.append(
            f"- {row['segment_value']} : V2 accuracy={row['v2_accuracy']}, V5 accuracy={row['v5_accuracy']}, delta={row['accuracy_delta']}, net_correct_rows_delta={row['net_correct_rows_delta']}"
        )

    lines.extend(
        [
            "",
            "Stabilite par saison :",
        ]
    )

    for _, row in season_rows.iterrows():
        lines.append(
            f"- {row['segment_value']} : V2 accuracy={row['v2_accuracy']}, V5 accuracy={row['v5_accuracy']}, delta={row['accuracy_delta']}, net_correct_rows_delta={row['net_correct_rows_delta']}"
        )

    lines.extend(
        [
            "",
            "Top segments d'erreurs / transitions :",
        ]
    )

    for _, row in top_error_segments.iterrows():
        lines.append(
            f"- {row['segment_family']} | {row['segment_value']} : rows={row['rows']}, changed={row['changed_predictions']}, corrected={row['v5_corrected_errors']}, created_errors={row['v5_created_errors']}, net={row['net_correct_rows_delta']}"
        )

    lines.extend(
        [
            "",
            "Decision technique :",
            f"- Status : {decision['status']}",
            f"- Accuracy gain >= {MIN_SAVE_READY_ACCURACY_GAIN:.4f} : {decision['accuracy_gain_ok']}",
            f"- F1 macro gain >= {MIN_SAVE_READY_F1_MACRO_GAIN:.4f} : {decision['f1_gain_ok']}",
            f"- Pas de forte baisse par ligue : {decision['no_large_league_drop']}",
            f"- Pas de forte baisse par saison : {decision['no_large_season_drop']}",
            f"- Net correct rows positif : {decision['net_positive']}",
            f"- Min league accuracy delta : {decision['min_league_accuracy_delta']}",
            f"- Min season accuracy delta : {decision['min_season_accuracy_delta']}",
            "",
        ]
    )

    if decision["status"] == "V5_SAVE_CANDIDATE_READY":
        lines.extend(
            [
                "Conclusion :",
                "Le candidat V5 presente un gain assez stable pour preparer une etape separee de sauvegarde candidate.",
                "Aucune sauvegarde n'est effectuee par ce script.",
            ]
        )
    else:
        lines.extend(
            [
                "Conclusion :",
                "Le candidat V5 reste experimental. Le gain observe n'est pas encore assez fort ou assez stable pour justifier une sauvegarde candidate.",
                "La prochaine piste doit etre decidee apres lecture des segments d'erreurs : soit affiner quelques features V5, soit passer a un enrichissement de donnees avant-match plus riche.",
            ]
        )

    lines.extend(
        [
            "",
            "Fichiers generes :",
            str(SUMMARY_PATH.relative_to(PROJECT_ROOT)),
            str(STABILITY_CSV_PATH.relative_to(PROJECT_ROOT)),
            str(ERROR_SEGMENTS_CSV_PATH.relative_to(PROJECT_ROOT)),
            "",
            "Statut de suivi :",
            "- Tache realisee : analyse de stabilite du candidat V5.",
            "- Statut source a mettre a jour : realise si les fichiers 71, 72 et 73 sont generes.",
            "- Fichiers concernes : reports/evidence/ml_training/71, 72 et 73.",
            "",
        ]
    )

    return "\n".join(lines)


# Sauvegarde les fichiers de stabilité, segments d'erreurs et synthèse.
def save_reports(stability_dataframe: pd.DataFrame, error_segments_dataframe: pd.DataFrame, summary: str) -> None:
    ensure_report_dir()
    stability_dataframe.to_csv(STABILITY_CSV_PATH, index=False, encoding="utf-8")
    error_segments_dataframe.to_csv(ERROR_SEGMENTS_CSV_PATH, index=False, encoding="utf-8")
    SUMMARY_PATH.write_text(summary, encoding="utf-8")


# Lance l'analyse complète de stabilité du candidat V5.
def main() -> None:
    database_url = get_database_url()
    clean_matches = fetch_clean_matches(database_url)

    print(f"Matchs nettoyes charges : {len(clean_matches)}", flush=True)
    print("Construction des features V2 de reference en memoire...", flush=True)

    v2_feature_dataframe = build_v2_fast_feature_dataframe(clean_matches)

    print("Ajout des features V5 d'equilibre de match...", flush=True)
    v5_feature_dataframe = add_v5_balance_features(v2_feature_dataframe)

    feature_sets = build_v5_feature_sets()
    v2_columns = feature_sets[V2_FEATURE_SET_NAME]
    v5_columns = feature_sets[V5_FEATURE_SET_NAME]

    print("Entrainement et predictions V2 reference...", flush=True)
    v2_predictions = train_and_predict(
        feature_dataframe=v5_feature_dataframe,
        feature_set_name=V2_FEATURE_SET_NAME,
        feature_columns=v2_columns,
    )

    print("Entrainement et predictions candidat V5...", flush=True)
    v5_predictions = train_and_predict(
        feature_dataframe=v5_feature_dataframe,
        feature_set_name=V5_FEATURE_SET_NAME,
        feature_columns=v5_columns,
    )

    print("Comparaison V2 vs V5 par segments...", flush=True)
    comparison_dataframe = build_comparison_dataframe(v2_predictions, v5_predictions)

    stability_dataframe = pd.DataFrame(build_stability_rows(comparison_dataframe))
    error_segments_dataframe = pd.DataFrame(build_error_segment_rows(comparison_dataframe))

    decision = decide_v5_status(stability_dataframe)
    summary = build_summary(
        comparison_dataframe=comparison_dataframe,
        stability_dataframe=stability_dataframe,
        error_segments_dataframe=error_segments_dataframe,
        decision=decision,
    )

    save_reports(stability_dataframe, error_segments_dataframe, summary)

    overall_row = stability_dataframe[
        (stability_dataframe["segment_family"] == "overall")
        & (stability_dataframe["segment_value"] == "all_test_matches")
    ].iloc[0]

    print("OK - Analyse de stabilite V5 terminee.", flush=True)
    print(f"Status: {decision['status']}", flush=True)
    print(f"V2 accuracy: {overall_row['v2_accuracy']}", flush=True)
    print(f"V5 accuracy: {overall_row['v5_accuracy']}", flush=True)
    print(f"Accuracy delta: {overall_row['accuracy_delta']}", flush=True)
    print(f"V2 F1 macro: {overall_row['v2_f1_macro']}", flush=True)
    print(f"V5 F1 macro: {overall_row['v5_f1_macro']}", flush=True)
    print(f"F1 macro delta: {overall_row['f1_macro_delta']}", flush=True)
    print(f"Net correct rows delta: {overall_row['net_correct_rows_delta']}", flush=True)
    print(f"Summary saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Stability CSV saved: {STABILITY_CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Error segments CSV saved: {ERROR_SEGMENTS_CSV_PATH.relative_to(PROJECT_ROOT)}", flush=True)


if __name__ == "__main__":
    main()


# Schema de communication :
# analyze_1x2_v5_candidate_stability.py
#   -> lit ml.clean_matches via les fonctions existantes
#   -> reutilise la construction V2 et l'ajout des features V5
#   -> compare v2_reference et v5_draw_context_scores sur le test set
#   -> genere reports/evidence/ml_training/71, 72 et 73
#   -> ne modifie pas PostgreSQL, ml.features, l'API, le frontend, le scoring V1 ou les modeles sauvegardes
