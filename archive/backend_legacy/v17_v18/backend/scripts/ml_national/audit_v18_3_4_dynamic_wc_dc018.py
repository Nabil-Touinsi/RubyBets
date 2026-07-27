# Role du fichier :
# Ce script compare V18.3.3 et la variante experimentale V18.3.4 dc018
# sur les matchs World Cup dynamiques actuellement visibles dans RubyBets.

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


WC_CACHE_RELATIVE_PATH = Path(
    "backend/app/data/cache/matches_wc_scheduled_all_start_dates_all_end_dates.json"
)
FALLBACK_WC_CACHE_RELATIVE_PATH = Path(
    "app/data/cache/matches_wc_scheduled_all_start_dates_all_end_dates.json"
)
SUMMARY_OUTPUT_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/377_v18_3_4_dynamic_wc_dc018_audit_summary.txt"
)
CSV_OUTPUT_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/378_v18_3_4_dynamic_wc_dc018_audit_results.csv"
)
SWITCHES_OUTPUT_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/379_v18_3_4_dynamic_wc_dc018_switches.csv"
)
DECISION_OUTPUT_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/380_v18_3_4_dynamic_wc_dc018_decision.txt"
)

STRICT_1X2_THRESHOLD = 0.76
OVER_1_5_YES_THRESHOLD = 0.78
OVER_2_5_THRESHOLD = 0.70
BTTS_NO_THRESHOLD = 0.75
V18_3_3_DOUBLE_CHANCE_THRESHOLD = 0.15
V18_3_4_DOUBLE_CHANCE_THRESHOLD = 0.18


# Ajoute backend/ au PYTHONPATH pour importer les services app.* depuis la racine.
def configure_python_path(project_root: Path) -> None:
    backend_path = project_root / "backend"
    if backend_path.exists() and str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


# Retrouve la racine RubyBets selon l'emplacement du script ou du terminal.
def find_project_root() -> Path:
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[3],
        script_path.parents[2],
        Path.cwd(),
        Path.cwd().parent,
    ]

    for candidate in candidates:
        if (candidate / "backend").exists() and (candidate / "reports").exists():
            return candidate.resolve()

    return Path.cwd().resolve()


# Retourne le chemin du cache World Cup dans les deux structures possibles.
def get_wc_cache_path(project_root: Path) -> Path:
    root_cache_path = project_root / WC_CACHE_RELATIVE_PATH
    if root_cache_path.exists():
        return root_cache_path

    backend_cache_path = project_root / FALLBACK_WC_CACHE_RELATIVE_PATH
    if backend_cache_path.exists():
        return backend_cache_path

    return root_cache_path


# Charge les matchs World Cup stockes dans le cache RubyBets.
def load_wc_matches(project_root: Path) -> tuple[list[dict[str, Any]], Path]:
    cache_path = get_wc_cache_path(project_root)
    if not cache_path.exists():
        raise FileNotFoundError(
            "Cache World Cup introuvable. Ouvre d'abord Matchs > FIFA World Cup "
            "ou appelle /api/matches?competition_code=WC."
        )

    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    data_payload = cache_payload.get("data", {})
    matches = data_payload.get("matches", [])

    if not isinstance(matches, list):
        raise ValueError("Le cache World Cup ne contient pas une liste matches valide.")

    return matches, cache_path


# Retourne une valeur imbriquee sans declencher d'erreur si une cle manque.
def nested_get(payload: dict[str, Any] | None, *keys: str) -> Any:
    current_value: Any = payload
    for key in keys:
        if not isinstance(current_value, dict):
            return None
        current_value = current_value.get(key)
    return current_value


# Recupere le nom d'une equipe dans un match Football-Data / RubyBets.
def get_team_name(match: dict[str, Any], key: str) -> str | None:
    team = match.get(key)
    if not isinstance(team, dict):
        return None

    name = team.get("name")
    return str(name) if name else None


# Convertit une valeur en float ou None pour eviter les plantages d'audit.
def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# Arrondit une valeur numerique pour rendre les CSV plus lisibles.
def rounded(value: Any, digits: int = 6) -> float | None:
    numeric_value = safe_float(value)
    if numeric_value is None:
        return None
    return round(numeric_value, digits)


# Transforme une confiance numerique en niveau de risque lisible.
def compute_risk_level(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    if confidence >= 0.85:
        return "low"
    if confidence >= 0.75:
        return "medium"
    return "high"


# Calcule la meilleure double chance a partir des probabilites 1X2.
def build_double_chance_candidate(
    market_predictions: dict[str, Any],
    excluded_threshold: float,
) -> dict[str, Any]:
    probabilities = {
        "TEAM_A_WIN": safe_float(
            nested_get(market_predictions, "1x2", "probabilities", "TEAM_A_WIN")
        ),
        "DRAW": safe_float(
            nested_get(market_predictions, "1x2", "probabilities", "DRAW")
        ),
        "TEAM_B_WIN": safe_float(
            nested_get(market_predictions, "1x2", "probabilities", "TEAM_B_WIN")
        ),
    }
    valid_probabilities = {
        key: value for key, value in probabilities.items() if value is not None
    }

    if not valid_probabilities:
        return {
            "is_valid": False,
            "excluded_outcome": None,
            "excluded_probability": None,
            "prediction": None,
            "confidence": None,
        }

    excluded_outcome = min(valid_probabilities, key=lambda key: valid_probabilities[key])
    excluded_probability = valid_probabilities[excluded_outcome]

    prediction_by_excluded_outcome = {
        "TEAM_A_WIN": "DRAW_OR_TEAM_B",
        "DRAW": "TEAM_A_OR_TEAM_B",
        "TEAM_B_WIN": "TEAM_A_OR_DRAW",
    }

    return {
        "is_valid": excluded_probability <= excluded_threshold,
        "excluded_outcome": excluded_outcome,
        "excluded_probability": round(excluded_probability, 6),
        "prediction": prediction_by_excluded_outcome.get(excluded_outcome),
        "confidence": round(1.0 - excluded_probability, 6),
    }


# Applique le selecteur candidat V18.3.4 dc018 sans modifier V18.3.3.
def select_market_with_v18_3_4_dc018(response: dict[str, Any]) -> dict[str, Any] | None:
    if response.get("status") != "computed":
        return None

    market_predictions = response.get("market_predictions", {})

    one_x_two_prediction = nested_get(market_predictions, "1x2", "prediction")
    one_x_two_max_probability = safe_float(
        nested_get(market_predictions, "1x2", "max_probability")
    )
    over_1_5_prediction = nested_get(market_predictions, "over_1_5", "prediction")
    over_1_5_yes_probability = safe_float(
        nested_get(market_predictions, "over_1_5", "probabilities", "YES")
    )
    over_2_5_prediction = nested_get(market_predictions, "over_2_5", "prediction")
    over_2_5_max_probability = safe_float(
        nested_get(market_predictions, "over_2_5", "max_probability")
    )
    btts_prediction = nested_get(market_predictions, "btts", "prediction")
    btts_no_probability = safe_float(
        nested_get(market_predictions, "btts", "probabilities", "NO")
    )

    if (
        one_x_two_prediction != "DRAW"
        and one_x_two_max_probability is not None
        and one_x_two_max_probability >= STRICT_1X2_THRESHOLD
    ):
        return build_selector_result(
            selected_market="STRICT_1X2",
            selected_prediction=str(one_x_two_prediction),
            selected_confidence=one_x_two_max_probability,
            selector_rule=f"1X2 non-DRAW avec confiance >= {STRICT_1X2_THRESHOLD}",
        )

    if (
        over_1_5_prediction == "YES"
        and over_1_5_yes_probability is not None
        and over_1_5_yes_probability >= OVER_1_5_YES_THRESHOLD
    ):
        return build_selector_result(
            selected_market="OVER_1_5",
            selected_prediction="YES",
            selected_confidence=over_1_5_yes_probability,
            selector_rule=f"OVER_1_5 YES avec confiance >= {OVER_1_5_YES_THRESHOLD}",
        )

    if over_2_5_max_probability is not None and over_2_5_max_probability >= OVER_2_5_THRESHOLD:
        return build_selector_result(
            selected_market="OVER_2_5",
            selected_prediction=str(over_2_5_prediction),
            selected_confidence=over_2_5_max_probability,
            selector_rule=f"OVER_2_5 avec confiance >= {OVER_2_5_THRESHOLD}",
        )

    if (
        btts_prediction == "NO"
        and btts_no_probability is not None
        and btts_no_probability >= BTTS_NO_THRESHOLD
    ):
        return build_selector_result(
            selected_market="BTTS",
            selected_prediction="NO",
            selected_confidence=btts_no_probability,
            selector_rule=f"BTTS NO avec confiance >= {BTTS_NO_THRESHOLD}",
        )

    double_chance = build_double_chance_candidate(
        market_predictions,
        V18_3_4_DOUBLE_CHANCE_THRESHOLD,
    )
    if double_chance["is_valid"]:
        return build_selector_result(
            selected_market="DOUBLE_CHANCE",
            selected_prediction=str(double_chance["prediction"]),
            selected_confidence=safe_float(double_chance["confidence"]),
            selector_rule=(
                "DOUBLE_CHANCE si probabilite de l'issue exclue <= "
                f"{V18_3_4_DOUBLE_CHANCE_THRESHOLD}"
            ),
            excluded_outcome=double_chance["excluded_outcome"],
            excluded_probability=double_chance["excluded_probability"],
        )

    return {
        "source": "rubybets_ml_national_v18_3_4_candidate_selector",
        "scope": "experimental_backend",
        "status": "ABSTAIN",
        "selector_version": "v18.3.4-candidate",
        "selector_profile": "dc018_abstention_reduction_audit",
        "selector_variant": "v18_3_4_candidate_dc018",
        "selected_market": "ABSTAIN",
        "selected_prediction": "ABSTAIN",
        "selected_confidence": None,
        "risk_level": None,
        "selector_rule": "Aucun signal ne respecte les seuils V18.3.4 dc018.",
        "responsible_note": (
            "Signal experimental non integre au produit officiel. "
            "Aucune garantie de resultat sportif."
        ),
    }


# Construit une reponse de selecteur homogene pour le candidat V18.3.4.
def build_selector_result(
    selected_market: str,
    selected_prediction: str,
    selected_confidence: float | None,
    selector_rule: str,
    excluded_outcome: Any | None = None,
    excluded_probability: Any | None = None,
) -> dict[str, Any]:
    confidence = rounded(selected_confidence)
    return {
        "source": "rubybets_ml_national_v18_3_4_candidate_selector",
        "scope": "experimental_backend",
        "status": "RECOMMEND",
        "selector_version": "v18.3.4-candidate",
        "selector_profile": "dc018_abstention_reduction_audit",
        "selector_variant": "v18_3_4_candidate_dc018",
        "selected_market": selected_market,
        "selected_prediction": selected_prediction,
        "selected_confidence": confidence,
        "risk_level": compute_risk_level(confidence),
        "selector_rule": selector_rule,
        "responsible_note": (
            "Signal experimental non integre au produit officiel. "
            "Aucune garantie de resultat sportif."
        ),
        "excluded_outcome": excluded_outcome,
        "excluded_probability": excluded_probability,
    }


# Derive une transition lisible entre V18.3.3 et V18.3.4 dc018.
def classify_transition(v18_3_3_result: dict[str, Any] | None, v18_3_4_result: dict[str, Any] | None) -> str:
    old_status = nested_get(v18_3_3_result, "status")
    new_status = nested_get(v18_3_4_result, "status")
    old_market = nested_get(v18_3_3_result, "selected_market")
    new_market = nested_get(v18_3_4_result, "selected_market")
    old_prediction = nested_get(v18_3_3_result, "selected_prediction")
    new_prediction = nested_get(v18_3_4_result, "selected_prediction")

    if v18_3_3_result is None and v18_3_4_result is None:
        return "UNAVAILABLE"
    if old_status == "ABSTAIN" and new_status == "RECOMMEND":
        return "ABSTAIN_TO_RECOMMEND"
    if old_status == "RECOMMEND" and new_status == "RECOMMEND":
        if old_market == new_market and old_prediction == new_prediction:
            return "SAME_RECOMMENDATION"
        return "RECOMMENDATION_CHANGED"
    if old_status == "ABSTAIN" and new_status == "ABSTAIN":
        return "SAME_ABSTENTION"
    if old_status == "RECOMMEND" and new_status == "ABSTAIN":
        return "RECOMMEND_TO_ABSTAIN"
    return "OTHER"


# Transforme une inference dynamique en ligne CSV de comparaison.
def build_comparison_row(match: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    v18_3_3_result = response.get("selector_result")
    v18_3_4_result = select_market_with_v18_3_4_dc018(response)
    transition = classify_transition(v18_3_3_result, v18_3_4_result)
    market_predictions = response.get("market_predictions", {})
    double_chance_015 = build_double_chance_candidate(
        market_predictions,
        V18_3_3_DOUBLE_CHANCE_THRESHOLD,
    )
    double_chance_018 = build_double_chance_candidate(
        market_predictions,
        V18_3_4_DOUBLE_CHANCE_THRESHOLD,
    )

    return {
        "match_id": match.get("id"),
        "utc_date": match.get("utcDate"),
        "competition_code": nested_get(match, "competition", "code"),
        "stage": match.get("stage"),
        "group_name": match.get("group"),
        "home_team": get_team_name(match, "homeTeam"),
        "away_team": get_team_name(match, "awayTeam"),
        "dynamic_status": response.get("status"),
        "unavailable_reason": response.get("unavailable_reason"),
        "transition": transition,
        "v18_3_3_status": nested_get(v18_3_3_result, "status"),
        "v18_3_3_market": nested_get(v18_3_3_result, "selected_market"),
        "v18_3_3_prediction": nested_get(v18_3_3_result, "selected_prediction"),
        "v18_3_3_confidence": rounded(nested_get(v18_3_3_result, "selected_confidence")),
        "v18_3_3_risk_level": nested_get(v18_3_3_result, "risk_level"),
        "v18_3_3_rule": nested_get(v18_3_3_result, "selector_rule"),
        "v18_3_4_status": nested_get(v18_3_4_result, "status"),
        "v18_3_4_market": nested_get(v18_3_4_result, "selected_market"),
        "v18_3_4_prediction": nested_get(v18_3_4_result, "selected_prediction"),
        "v18_3_4_confidence": rounded(nested_get(v18_3_4_result, "selected_confidence")),
        "v18_3_4_risk_level": nested_get(v18_3_4_result, "risk_level"),
        "v18_3_4_rule": nested_get(v18_3_4_result, "selector_rule"),
        "1x2_prediction": nested_get(market_predictions, "1x2", "prediction"),
        "1x2_max_probability": rounded(nested_get(market_predictions, "1x2", "max_probability")),
        "1x2_prob_team_a_win": rounded(nested_get(market_predictions, "1x2", "probabilities", "TEAM_A_WIN")),
        "1x2_prob_draw": rounded(nested_get(market_predictions, "1x2", "probabilities", "DRAW")),
        "1x2_prob_team_b_win": rounded(nested_get(market_predictions, "1x2", "probabilities", "TEAM_B_WIN")),
        "over_1_5_prediction": nested_get(market_predictions, "over_1_5", "prediction"),
        "over_1_5_prob_yes": rounded(nested_get(market_predictions, "over_1_5", "probabilities", "YES")),
        "over_2_5_prediction": nested_get(market_predictions, "over_2_5", "prediction"),
        "over_2_5_max_probability": rounded(nested_get(market_predictions, "over_2_5", "max_probability")),
        "btts_prediction": nested_get(market_predictions, "btts", "prediction"),
        "btts_prob_no": rounded(nested_get(market_predictions, "btts", "probabilities", "NO")),
        "dc015_excluded_outcome": double_chance_015.get("excluded_outcome"),
        "dc015_excluded_probability": double_chance_015.get("excluded_probability"),
        "dc018_excluded_outcome": double_chance_018.get("excluded_outcome"),
        "dc018_excluded_probability": double_chance_018.get("excluded_probability"),
    }


# Lance les deux variantes sur tous les matchs WC du cache.
def run_dynamic_comparison(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.services.ml_national_v18_3_3_dynamic_inference_service import (
        infer_v18_3_3_for_rubybets_match,
    )

    rows: list[dict[str, Any]] = []

    for match in matches:
        try:
            response = infer_v18_3_3_for_rubybets_match(match)
            rows.append(build_comparison_row(match, response))
        except Exception as error:  # noqa: BLE001 - audit robuste pour ne pas interrompre la preuve.
            rows.append(
                {
                    "match_id": match.get("id"),
                    "utc_date": match.get("utcDate"),
                    "competition_code": nested_get(match, "competition", "code"),
                    "stage": match.get("stage"),
                    "group_name": match.get("group"),
                    "home_team": get_team_name(match, "homeTeam"),
                    "away_team": get_team_name(match, "awayTeam"),
                    "dynamic_status": "error",
                    "unavailable_reason": str(error),
                    "transition": "ERROR",
                    "v18_3_3_status": None,
                    "v18_3_3_market": None,
                    "v18_3_3_prediction": None,
                    "v18_3_3_confidence": None,
                    "v18_3_3_risk_level": None,
                    "v18_3_3_rule": None,
                    "v18_3_4_status": None,
                    "v18_3_4_market": None,
                    "v18_3_4_prediction": None,
                    "v18_3_4_confidence": None,
                    "v18_3_4_risk_level": None,
                    "v18_3_4_rule": None,
                    "1x2_prediction": None,
                    "1x2_max_probability": None,
                    "1x2_prob_team_a_win": None,
                    "1x2_prob_draw": None,
                    "1x2_prob_team_b_win": None,
                    "over_1_5_prediction": None,
                    "over_1_5_prob_yes": None,
                    "over_2_5_prediction": None,
                    "over_2_5_max_probability": None,
                    "btts_prediction": None,
                    "btts_prob_no": None,
                    "dc015_excluded_outcome": None,
                    "dc015_excluded_probability": None,
                    "dc018_excluded_outcome": None,
                    "dc018_excluded_probability": None,
                }
            )

    return rows


# Ecrit un fichier CSV a partir des lignes de comparaison.
def write_csv(output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["status"]

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Filtre les matchs ou V18.3.4 transforme une abstention V18.3.3 en recommandation.
def build_switch_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("transition") == "ABSTAIN_TO_RECOMMEND"]


# Calcule les indicateurs principaux pour les deux versions sur le cache dynamique.
def compute_dynamic_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_rows = len(rows)
    computable_rows = sum(1 for row in rows if row.get("dynamic_status") == "computed")
    unavailable_rows = sum(1 for row in rows if row.get("dynamic_status") == "unavailable")
    error_rows = sum(1 for row in rows if row.get("dynamic_status") == "error")

    v18_3_3_recommendations = sum(1 for row in rows if row.get("v18_3_3_status") == "RECOMMEND")
    v18_3_4_recommendations = sum(1 for row in rows if row.get("v18_3_4_status") == "RECOMMEND")
    v18_3_3_abstentions = sum(1 for row in rows if row.get("v18_3_3_status") == "ABSTAIN")
    v18_3_4_abstentions = sum(1 for row in rows if row.get("v18_3_4_status") == "ABSTAIN")
    switched_to_recommend = sum(1 for row in rows if row.get("transition") == "ABSTAIN_TO_RECOMMEND")

    v18_3_4_confidences = [
        safe_float(row.get("v18_3_4_confidence"))
        for row in rows
        if row.get("v18_3_4_status") == "RECOMMEND"
    ]
    v18_3_4_confidences = [value for value in v18_3_4_confidences if value is not None]

    return {
        "total_rows": total_rows,
        "computable_rows": computable_rows,
        "unavailable_rows": unavailable_rows,
        "error_rows": error_rows,
        "v18_3_3_recommendations": v18_3_3_recommendations,
        "v18_3_4_recommendations": v18_3_4_recommendations,
        "v18_3_3_abstentions": v18_3_3_abstentions,
        "v18_3_4_abstentions": v18_3_4_abstentions,
        "switched_to_recommend": switched_to_recommend,
        "v18_3_3_recommendation_rate_total": v18_3_3_recommendations / total_rows if total_rows else 0.0,
        "v18_3_4_recommendation_rate_total": v18_3_4_recommendations / total_rows if total_rows else 0.0,
        "v18_3_3_recommendation_rate_computable": v18_3_3_recommendations / computable_rows if computable_rows else 0.0,
        "v18_3_4_recommendation_rate_computable": v18_3_4_recommendations / computable_rows if computable_rows else 0.0,
        "v18_3_4_avg_confidence": (
            sum(v18_3_4_confidences) / len(v18_3_4_confidences)
            if v18_3_4_confidences
            else 0.0
        ),
    }


# Construit la synthese texte lisible pour la decision projet.
def build_summary_text(
    rows: list[dict[str, Any]],
    cache_path: Path,
    csv_path: Path,
    switches_path: Path,
) -> str:
    metrics = compute_dynamic_metrics(rows)
    transition_counts = Counter(row.get("transition") for row in rows)
    v18_3_3_market_counts = Counter(row.get("v18_3_3_market") for row in rows)
    v18_3_4_market_counts = Counter(row.get("v18_3_4_market") for row in rows)

    lines = [
        "Audit dynamique WC - comparaison V18.3.3 vs V18.3.4 dc018",
        "===========================================================",
        f"Cache analyse : {cache_path}",
        f"CSV detaille : {csv_path}",
        f"CSV switches : {switches_path}",
        "",
        f"Matchs analyses : {metrics['total_rows']}",
        f"Matchs calculables : {metrics['computable_rows']}",
        f"Indisponibles : {metrics['unavailable_rows']}",
        f"Erreurs techniques : {metrics['error_rows']}",
        "",
        "V18.3.3 reference dynamique :",
        f"- recommandations : {metrics['v18_3_3_recommendations']} ({metrics['v18_3_3_recommendation_rate_total']:.4f} total / {metrics['v18_3_3_recommendation_rate_computable']:.4f} calculable)",
        f"- abstentions strictes : {metrics['v18_3_3_abstentions']}",
        "",
        "V18.3.4 candidat dc018 dynamique :",
        f"- recommandations : {metrics['v18_3_4_recommendations']} ({metrics['v18_3_4_recommendation_rate_total']:.4f} total / {metrics['v18_3_4_recommendation_rate_computable']:.4f} calculable)",
        f"- abstentions strictes : {metrics['v18_3_4_abstentions']}",
        f"- abstentions devenues recommandations : {metrics['switched_to_recommend']}",
        f"- confiance moyenne des recommandations : {metrics['v18_3_4_avg_confidence']:.6f}",
        "",
        "Transitions :",
    ]

    for transition, count in transition_counts.most_common():
        lines.append(f"- {transition}: {count}")

    lines.append("")
    lines.append("Repartition marches V18.3.3 :")
    for market, count in v18_3_3_market_counts.most_common():
        lines.append(f"- {market}: {count}")

    lines.append("")
    lines.append("Repartition marches V18.3.4 dc018 :")
    for market, count in v18_3_4_market_counts.most_common():
        lines.append(f"- {market}: {count}")

    lines.append("")
    lines.append("Decision recommandee :")
    lines.append(
        "Utiliser ces resultats comme audit produit uniquement. Ne pas remplacer V18.3.3 "
        "sans inspection des matchs passes de ABSTAIN a RECOMMEND et sans validation de prudence."
    )

    return "\n".join(lines) + "\n"


# Construit le fichier de decision associe a l'audit dynamique.
def build_decision_text(rows: list[dict[str, Any]]) -> str:
    metrics = compute_dynamic_metrics(rows)
    return "\n".join(
        [
            "Decision dynamique WC - V18.3.4 dc018",
            "=======================================",
            f"Recommandations V18.3.3 : {metrics['v18_3_3_recommendations']}",
            f"Recommandations V18.3.4 dc018 : {metrics['v18_3_4_recommendations']}",
            f"Abstentions converties en recommandations : {metrics['switched_to_recommend']}",
            "",
            "Decision :",
            "V18.3.4 dc018 reste une variante experimentale d'audit.",
            "Elle ne doit pas remplacer V18.3.3 tant que les nouveaux matchs recommandes ne sont pas verifies.",
            "Aucune garantie de resultat sportif ne doit etre formulee.",
            "",
        ]
    )


# Point d'entree du script d'audit dynamique compare.
def main() -> None:
    project_root = find_project_root()
    configure_python_path(project_root)

    matches, cache_path = load_wc_matches(project_root)
    rows = run_dynamic_comparison(matches)
    switch_rows = build_switch_rows(rows)

    csv_output_path = project_root / CSV_OUTPUT_RELATIVE_PATH
    switches_output_path = project_root / SWITCHES_OUTPUT_RELATIVE_PATH
    summary_output_path = project_root / SUMMARY_OUTPUT_RELATIVE_PATH
    decision_output_path = project_root / DECISION_OUTPUT_RELATIVE_PATH

    write_csv(csv_output_path, rows)
    write_csv(switches_output_path, switch_rows)

    summary_text = build_summary_text(rows, cache_path, csv_output_path, switches_output_path)
    summary_output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_output_path.write_text(summary_text, encoding="utf-8")
    decision_output_path.write_text(build_decision_text(rows), encoding="utf-8")

    print(summary_text)
    print(f"Summary saved: {summary_output_path}")
    print(f"CSV saved: {csv_output_path}")
    print(f"Switches CSV saved: {switches_output_path}")
    print(f"Decision saved: {decision_output_path}")


if __name__ == "__main__":
    main()


# Schema de communication :
# audit_v18_3_4_dynamic_wc_dc018.py
#   -> lit backend/app/data/cache/matches_wc_scheduled_all_start_dates_all_end_dates.json
#   -> appelle ml_national_v18_3_3_dynamic_inference_service.py pour calculer les predictions dynamiques
#   -> rejoue un selecteur candidat V18.3.4 dc018 sans modifier V18.3.3
#   -> genere les preuves 377/378/379/380 dans reports/evidence/ml_training/
#   -> sert uniquement a mesurer la reduction d'abstention avant toute integration produit
