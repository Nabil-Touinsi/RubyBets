# Role du fichier :
# Ce script evalue un selecteur experimental V18.2 WC enriched.
# Il choisit entre STRICT_1X2, DOUBLE_CHANCE, OVER_1_5, OVER_2_5, BTTS ou ABSTAIN
# a partir des predictions V18.1 Kaggle + Elo + StatsBomb.

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]

EVIDENCE_DIR = ROOT_DIR / "reports" / "evidence" / "ml_training"

INPUT_PREDICTIONS_CSV = EVIDENCE_DIR / "336_v18_1_wc_enriched_predictions.csv"

SUMMARY_FILE = EVIDENCE_DIR / "338_v18_2_wc_enriched_selector_summary.txt"
RESULTS_CSV = EVIDENCE_DIR / "339_v18_2_wc_enriched_selector_results.csv"
BEST_PREDICTIONS_CSV = EVIDENCE_DIR / "340_v18_2_wc_enriched_best_predictions.csv"


SELECTED_MODELS = {
    "target_1x2": {
        "feature_set": "kaggle_elo_statsbomb",
        "model_name": "random_forest_balanced",
    },
    "target_over_1_5": {
        "feature_set": "kaggle_elo_statsbomb",
        "model_name": "logistic_regression_balanced",
    },
    "target_over_2_5": {
        "feature_set": "kaggle_elo_statsbomb",
        "model_name": "random_forest_balanced",
    },
    "target_btts": {
        "feature_set": "kaggle_elo_only",
        "model_name": "logistic_regression_balanced",
    },
}


STRATEGIES = [
    {
        "strategy_name": "v18_2_balanced_market_selector",
        "strict_1x2_threshold": 0.62,
        "double_chance_threshold": 0.46,
        "over_1_5_threshold": 0.78,
        "over_2_5_threshold": 0.62,
        "btts_threshold": 0.66,
        "priority": ["STRICT_1X2", "OVER_1_5", "OVER_2_5", "BTTS", "DOUBLE_CHANCE"],
    },
    {
        "strategy_name": "v18_2_safe_market_selector",
        "strict_1x2_threshold": 0.68,
        "double_chance_threshold": 0.52,
        "over_1_5_threshold": 0.82,
        "over_2_5_threshold": 0.68,
        "btts_threshold": 0.72,
        "priority": ["STRICT_1X2", "OVER_1_5", "OVER_2_5", "BTTS", "DOUBLE_CHANCE"],
    },
    {
        "strategy_name": "v18_2_coverage_market_selector",
        "strict_1x2_threshold": 0.56,
        "double_chance_threshold": 0.42,
        "over_1_5_threshold": 0.72,
        "over_2_5_threshold": 0.56,
        "btts_threshold": 0.58,
        "priority": ["STRICT_1X2", "OVER_1_5", "OVER_2_5", "BTTS", "DOUBLE_CHANCE"],
    },
    {
        "strategy_name": "v18_2_1x2_first_selector",
        "strict_1x2_threshold": 0.60,
        "double_chance_threshold": 0.44,
        "over_1_5_threshold": 0.76,
        "over_2_5_threshold": 0.60,
        "btts_threshold": 0.64,
        "priority": ["STRICT_1X2", "DOUBLE_CHANCE", "OVER_1_5", "OVER_2_5", "BTTS"],
    },
]


# Cette fonction charge un CSV en liste de dictionnaires.
def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


# Cette fonction convertit une valeur en float.
def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# Cette fonction convertit une valeur en entier.
def to_int(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


# Cette fonction normalise un label de prediction.
def normalize_label(value: Any) -> str:
    return str(value or "").strip()


# Cette fonction verifie si un label correspond a Team A.
def is_team_a_win(label: str) -> bool:
    return label in {"TEAM_A_WIN", "HOME_WIN"}


# Cette fonction verifie si un label correspond a Team B.
def is_team_b_win(label: str) -> bool:
    return label in {"TEAM_B_WIN", "AWAY_WIN"}


# Cette fonction verifie si un label correspond au nul.
def is_draw(label: str) -> bool:
    return label == "DRAW"


# Cette fonction filtre les predictions du modele retenu pour chaque target.
def filter_selected_predictions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_rows = []

    for row in rows:
        target = str(row.get("target"))

        if target not in SELECTED_MODELS:
            continue

        expected = SELECTED_MODELS[target]

        if row.get("feature_set") != expected["feature_set"]:
            continue

        if row.get("model_name") != expected["model_name"]:
            continue

        selected_rows.append(row)

    return selected_rows


# Cette fonction indexe les predictions par match.
def index_predictions_by_match(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    index: dict[str, dict[str, dict[str, Any]]] = {}

    for row in rows:
        match_key = str(row.get("clean_match_id") or row.get("statsbomb_match_id"))
        target = str(row.get("target"))

        if not match_key:
            continue

        index.setdefault(match_key, {})
        index[match_key][target] = row

    return index


# Cette fonction construit une recommandation STRICT_1X2 si le signal est assez fort.
def build_strict_1x2_candidate(
    predictions: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, Any] | None:
    row = predictions.get("target_1x2")

    if not row:
        return None

    confidence = to_float(row.get("predicted_confidence"))
    predicted = normalize_label(row.get("predicted"))

    if confidence < float(strategy["strict_1x2_threshold"]):
        return None

    actual = normalize_label(row.get("actual"))
    is_correct = actual == predicted

    return {
        "market_type": "STRICT_1X2",
        "recommendation": predicted,
        "actual": actual,
        "predicted": predicted,
        "confidence": confidence,
        "positive_probability": "",
        "is_correct": is_correct,
        "source_target": "target_1x2",
        "source_feature_set": row.get("feature_set"),
        "source_model_name": row.get("model_name"),
    }


# Cette fonction construit une recommandation DOUBLE_CHANCE depuis la prediction 1X2.
def build_double_chance_candidate(
    predictions: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, Any] | None:
    row = predictions.get("target_1x2")

    if not row:
        return None

    confidence = to_float(row.get("predicted_confidence"))
    predicted = normalize_label(row.get("predicted"))
    actual = normalize_label(row.get("actual"))

    if confidence < float(strategy["double_chance_threshold"]):
        return None

    if is_team_a_win(predicted):
        recommendation = "TEAM_A_OR_DRAW"
        is_correct = is_team_a_win(actual) or is_draw(actual)

    elif is_team_b_win(predicted):
        recommendation = "DRAW_OR_TEAM_B"
        is_correct = is_team_b_win(actual) or is_draw(actual)

    else:
        return None

    return {
        "market_type": "DOUBLE_CHANCE",
        "recommendation": recommendation,
        "actual": actual,
        "predicted": predicted,
        "confidence": confidence,
        "positive_probability": "",
        "is_correct": is_correct,
        "source_target": "target_1x2",
        "source_feature_set": row.get("feature_set"),
        "source_model_name": row.get("model_name"),
    }


# Cette fonction construit une recommandation OVER_1_5 si le signal est fort.
def build_over_1_5_candidate(
    predictions: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, Any] | None:
    row = predictions.get("target_over_1_5")

    if not row:
        return None

    predicted = to_int(row.get("predicted"))
    positive_probability = to_float(row.get("positive_probability"))

    if predicted != 1:
        return None

    if positive_probability < float(strategy["over_1_5_threshold"]):
        return None

    actual = to_int(row.get("actual"))

    return {
        "market_type": "OVER_1_5",
        "recommendation": "OVER_1_5",
        "actual": actual,
        "predicted": predicted,
        "confidence": to_float(row.get("predicted_confidence")),
        "positive_probability": positive_probability,
        "is_correct": actual == 1,
        "source_target": "target_over_1_5",
        "source_feature_set": row.get("feature_set"),
        "source_model_name": row.get("model_name"),
    }


# Cette fonction construit une recommandation OVER_2_5 si le signal est fort.
def build_over_2_5_candidate(
    predictions: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, Any] | None:
    row = predictions.get("target_over_2_5")

    if not row:
        return None

    predicted = to_int(row.get("predicted"))
    positive_probability = to_float(row.get("positive_probability"))

    if predicted != 1:
        return None

    if positive_probability < float(strategy["over_2_5_threshold"]):
        return None

    actual = to_int(row.get("actual"))

    return {
        "market_type": "OVER_2_5",
        "recommendation": "OVER_2_5",
        "actual": actual,
        "predicted": predicted,
        "confidence": to_float(row.get("predicted_confidence")),
        "positive_probability": positive_probability,
        "is_correct": actual == 1,
        "source_target": "target_over_2_5",
        "source_feature_set": row.get("feature_set"),
        "source_model_name": row.get("model_name"),
    }


# Cette fonction construit une recommandation BTTS si le signal est fort.
def build_btts_candidate(
    predictions: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, Any] | None:
    row = predictions.get("target_btts")

    if not row:
        return None

    predicted = to_int(row.get("predicted"))
    positive_probability = to_float(row.get("positive_probability"))

    if predicted != 1:
        return None

    if positive_probability < float(strategy["btts_threshold"]):
        return None

    actual = to_int(row.get("actual"))

    return {
        "market_type": "BTTS",
        "recommendation": "BTTS_YES",
        "actual": actual,
        "predicted": predicted,
        "confidence": to_float(row.get("predicted_confidence")),
        "positive_probability": positive_probability,
        "is_correct": actual == 1,
        "source_target": "target_btts",
        "source_feature_set": row.get("feature_set"),
        "source_model_name": row.get("model_name"),
    }


# Cette fonction construit tous les candidats possibles pour un match.
def build_candidates(
    predictions: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    candidates = {}

    builders = {
        "STRICT_1X2": build_strict_1x2_candidate,
        "DOUBLE_CHANCE": build_double_chance_candidate,
        "OVER_1_5": build_over_1_5_candidate,
        "OVER_2_5": build_over_2_5_candidate,
        "BTTS": build_btts_candidate,
    }

    for market_type, builder in builders.items():
        candidate = builder(predictions, strategy)

        if candidate:
            candidates[market_type] = candidate

    return candidates


# Cette fonction applique une strategie de selection a un match.
def select_for_match(
    match_key: str,
    predictions: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    context_row = predictions.get("target_1x2") or next(iter(predictions.values()))
    candidates = build_candidates(predictions, strategy)

    selected_candidate = None

    for market_type in strategy["priority"]:
        if market_type in candidates:
            selected_candidate = candidates[market_type]
            break

    if selected_candidate is None:
        selected_candidate = {
            "market_type": "ABSTAIN",
            "recommendation": "ABSTAIN",
            "actual": "",
            "predicted": "",
            "confidence": "",
            "positive_probability": "",
            "is_correct": "",
            "source_target": "",
            "source_feature_set": "",
            "source_model_name": "",
        }

    return {
        "strategy_name": strategy["strategy_name"],
        "match_key": match_key,
        "clean_match_id": context_row.get("clean_match_id"),
        "statsbomb_match_id": context_row.get("statsbomb_match_id"),
        "match_date": context_row.get("match_date"),
        "season": context_row.get("season"),
        "team_a_name": context_row.get("team_a_name"),
        "team_b_name": context_row.get("team_b_name"),
        "team_a_score": context_row.get("team_a_score"),
        "team_b_score": context_row.get("team_b_score"),
        **selected_candidate,
    }


# Cette fonction applique une strategie sur tous les matchs.
def evaluate_strategy(
    predictions_index: dict[str, dict[str, dict[str, Any]]],
    strategy: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        select_for_match(match_key, predictions, strategy)
        for match_key, predictions in predictions_index.items()
    ]


# Cette fonction calcule les metriques d'une strategie.
def summarize_strategy(rows: list[dict[str, Any]], strategy: dict[str, Any]) -> dict[str, Any]:
    total_rows = len(rows)
    selected_rows = [row for row in rows if row["market_type"] != "ABSTAIN"]
    correct_rows = [row for row in selected_rows if row["is_correct"] is True]

    market_counts: dict[str, int] = {}
    market_correct: dict[str, int] = {}

    for row in selected_rows:
        market = str(row["market_type"])
        market_counts[market] = market_counts.get(market, 0) + 1

        if row["is_correct"] is True:
            market_correct[market] = market_correct.get(market, 0) + 1

    market_reliability = {
        market: round(market_correct.get(market, 0) / count, 4)
        for market, count in market_counts.items()
        if count > 0
    }

    return {
        "strategy_name": strategy["strategy_name"],
        "total_rows": total_rows,
        "selected_rows": len(selected_rows),
        "abstain_rows": total_rows - len(selected_rows),
        "coverage": round(len(selected_rows) / total_rows, 4) if total_rows else 0.0,
        "abstention_rate": round((total_rows - len(selected_rows)) / total_rows, 4) if total_rows else 0.0,
        "correct_rows": len(correct_rows),
        "reliability": round(len(correct_rows) / len(selected_rows), 4) if selected_rows else 0.0,
        "strict_1x2_rows": market_counts.get("STRICT_1X2", 0),
        "double_chance_rows": market_counts.get("DOUBLE_CHANCE", 0),
        "over_1_5_rows": market_counts.get("OVER_1_5", 0),
        "over_2_5_rows": market_counts.get("OVER_2_5", 0),
        "btts_rows": market_counts.get("BTTS", 0),
        "market_reliability": market_reliability,
        "priority": " > ".join(strategy["priority"]),
        "thresholds": (
            f"strict_1x2={strategy['strict_1x2_threshold']}; "
            f"double_chance={strategy['double_chance_threshold']}; "
            f"over_1_5={strategy['over_1_5_threshold']}; "
            f"over_2_5={strategy['over_2_5_threshold']}; "
            f"btts={strategy['btts_threshold']}"
        ),
    }


# Cette fonction sauvegarde les resultats des strategies.
def save_results_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "strategy_name",
        "total_rows",
        "selected_rows",
        "abstain_rows",
        "coverage",
        "abstention_rate",
        "correct_rows",
        "reliability",
        "strict_1x2_rows",
        "double_chance_rows",
        "over_1_5_rows",
        "over_2_5_rows",
        "btts_rows",
        "market_reliability",
        "priority",
        "thresholds",
    ]

    with RESULTS_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction sauvegarde les predictions selectionnees de la meilleure strategie.
def save_best_predictions_csv(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "strategy_name",
        "match_key",
        "clean_match_id",
        "statsbomb_match_id",
        "match_date",
        "season",
        "team_a_name",
        "team_b_name",
        "team_a_score",
        "team_b_score",
        "market_type",
        "recommendation",
        "actual",
        "predicted",
        "confidence",
        "positive_probability",
        "is_correct",
        "source_target",
        "source_feature_set",
        "source_model_name",
    ]

    with BEST_PREDICTIONS_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Cette fonction choisit la meilleure strategie produit.
def choose_best_strategy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_rows = [
        row for row in rows
        if float(row["coverage"]) >= 0.35
    ]

    if not eligible_rows:
        eligible_rows = rows

    return sorted(
        eligible_rows,
        key=lambda row: (
            float(row["reliability"]),
            float(row["coverage"]),
            int(row["selected_rows"]),
        ),
        reverse=True,
    )[0]


# Cette fonction sauvegarde la synthese texte.
def save_summary(
    result_rows: list[dict[str, Any]],
    best_result: dict[str, Any],
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "RubyBets - Evaluation selecteur V18.2 WC enriched",
        "",
        f"Source predictions : {INPUT_PREDICTIONS_CSV}",
        f"Resultats strategies : {RESULTS_CSV}",
        f"Predictions meilleure strategie : {BEST_PREDICTIONS_CSV}",
        "",
        "Objectif :",
        "Evaluer un selecteur experimental qui choisit entre STRICT_1X2, DOUBLE_CHANCE,",
        "OVER_1_5, OVER_2_5, BTTS ou ABSTAIN sur le perimetre Coupe du Monde 2022.",
        "",
        "Important :",
        "Le selecteur ne force pas tous les matchs.",
        "OVER_1_5 est conserve, mais avec seuil prudent.",
        "DOUBLE_CHANCE est derivee de la prediction 1X2.",
        "Aucun resultat n'est encore integre au backend ou au frontend.",
        "",
        "Strategies testees :",
    ]

    for row in result_rows:
        lines.append(
            "- "
            f"{row['strategy_name']} | "
            f"reliability={row['reliability']} | "
            f"coverage={row['coverage']} | "
            f"selected={row['selected_rows']} | "
            f"abstain={row['abstain_rows']} | "
            f"1X2={row['strict_1x2_rows']} | "
            f"DC={row['double_chance_rows']} | "
            f"O1.5={row['over_1_5_rows']} | "
            f"O2.5={row['over_2_5_rows']} | "
            f"BTTS={row['btts_rows']}"
        )

    lines.extend(
        [
            "",
            "Meilleure strategie retenue automatiquement :",
            f"- strategy_name : {best_result['strategy_name']}",
            f"- reliability : {best_result['reliability']}",
            f"- coverage : {best_result['coverage']}",
            f"- selected_rows : {best_result['selected_rows']}",
            f"- abstain_rows : {best_result['abstain_rows']}",
            f"- strict_1x2_rows : {best_result['strict_1x2_rows']}",
            f"- double_chance_rows : {best_result['double_chance_rows']}",
            f"- over_1_5_rows : {best_result['over_1_5_rows']}",
            f"- over_2_5_rows : {best_result['over_2_5_rows']}",
            f"- btts_rows : {best_result['btts_rows']}",
            f"- market_reliability : {best_result['market_reliability']}",
            "",
            "Decision attendue apres lecture :",
            "- Si le selecteur ameliore la reliability sans couverture trop faible, formaliser V18.2.",
            "- Si OVER_1_5 est trop dominant ou trop faible, ajuster son seuil.",
            "- Si BTTS degrade la reliability, le garder seulement avec seuil tres strict.",
            "- V18.2 reste experimental sur WC 2022 et ne remplace pas V17.9.2 globale.",
        ]
    )

    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# Cette fonction lance l'evaluation complete du selecteur V18.2.
def main() -> None:
    prediction_rows = load_csv(INPUT_PREDICTIONS_CSV)
    selected_prediction_rows = filter_selected_predictions(prediction_rows)
    predictions_index = index_predictions_by_match(selected_prediction_rows)

    all_strategy_predictions: dict[str, list[dict[str, Any]]] = {}
    result_rows = []

    for strategy in STRATEGIES:
        strategy_predictions = evaluate_strategy(predictions_index, strategy)
        strategy_summary = summarize_strategy(strategy_predictions, strategy)

        all_strategy_predictions[strategy["strategy_name"]] = strategy_predictions
        result_rows.append(strategy_summary)

    best_result = choose_best_strategy(result_rows)
    best_predictions = all_strategy_predictions[str(best_result["strategy_name"])]

    save_results_csv(result_rows)
    save_best_predictions_csv(best_predictions)
    save_summary(result_rows, best_result)

    print("OK - Evaluation selecteur V18.2 WC enriched terminee.")
    print(f"Matches evaluated: {len(predictions_index)}")
    print(f"Strategies tested: {len(result_rows)}")
    print(f"Best strategy: {best_result['strategy_name']}")
    print(f"Best reliability: {best_result['reliability']}")
    print(f"Best coverage: {best_result['coverage']}")
    print(f"Summary saved: {SUMMARY_FILE}")
    print(f"Results CSV saved: {RESULTS_CSV}")
    print(f"Best predictions CSV saved: {BEST_PREDICTIONS_CSV}")


if __name__ == "__main__":
    main()


# Schema de communication :
# evaluate_v18_2_wc_enriched_selector.py
#   -> lit reports/evidence/ml_training/336_v18_1_wc_enriched_predictions.csv
#   -> applique des strategies STRICT_1X2 / DOUBLE_CHANCE / OVER_1_5 / OVER_2_5 / BTTS / ABSTAIN
#   -> produit reports/evidence/ml_training/338_v18_2_wc_enriched_selector_summary.txt
#   -> produit reports/evidence/ml_training/339_v18_2_wc_enriched_selector_results.csv
#   -> produit reports/evidence/ml_training/340_v18_2_wc_enriched_best_predictions.csv