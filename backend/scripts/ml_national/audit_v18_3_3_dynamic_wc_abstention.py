# Role du fichier :
# Ce script audite les abstentions du moteur experimental V18.3.3 dynamique
# sur les matchs FIFA World Cup disponibles dans le cache RubyBets.

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
    "reports/evidence/ml_training/370_v18_3_3_dynamic_wc_abstention_audit_summary.txt"
)
CSV_OUTPUT_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/371_v18_3_3_dynamic_wc_abstention_audit_results.csv"
)

STRICT_1X2_THRESHOLD = 0.76
OVER_1_5_YES_THRESHOLD = 0.78
OVER_2_5_THRESHOLD = 0.70
BTTS_NO_THRESHOLD = 0.75
DOUBLE_CHANCE_EXCLUDED_THRESHOLD = 0.15


# Ajoute backend/ au PYTHONPATH pour permettre les imports app.services depuis la racine.
def configure_python_path(project_root: Path) -> None:
    backend_path = project_root / "backend"
    if backend_path.exists() and str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


# Retrouve la racine du projet RubyBets selon le dossier de lancement du script.
def find_project_root() -> Path:
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[3],
        script_path.parents[2],
        Path.cwd(),
        Path.cwd().parent,
    ]

    for candidate in candidates:
        if (candidate / "README.md").exists() or (candidate / "backend").exists():
            return candidate.resolve()

    return Path.cwd().resolve()


# Retourne le chemin du cache World Cup en acceptant les deux structures possibles.
def get_wc_cache_path(project_root: Path) -> Path:
    root_cache_path = project_root / WC_CACHE_RELATIVE_PATH
    if root_cache_path.exists():
        return root_cache_path

    backend_cache_path = project_root / FALLBACK_WC_CACHE_RELATIVE_PATH
    if backend_cache_path.exists():
        return backend_cache_path

    return root_cache_path


# Charge les matchs FIFA World Cup depuis le cache local RubyBets.
def load_wc_matches(project_root: Path) -> tuple[list[dict[str, Any]], Path, dict[str, Any]]:
    cache_path = get_wc_cache_path(project_root)
    if not cache_path.exists():
        raise FileNotFoundError(
            "Cache World Cup introuvable. Ouvre d'abord l'onglet Matchs > FIFA World Cup "
            "ou appelle /api/matches?competition_code=WC pour generer le cache."
        )

    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    data_payload = cache_payload.get("data", {})
    matches = data_payload.get("matches", [])

    if not isinstance(matches, list):
        raise ValueError("Le cache World Cup ne contient pas une liste matches valide.")

    return matches, cache_path, cache_payload


# Recupere le nom d'une equipe en acceptant les champs potentiellement absents.
def get_team_name(match: dict[str, Any], key: str) -> str | None:
    team = match.get(key)
    if not isinstance(team, dict):
        return None

    name = team.get("name")
    return str(name) if name else None


# Retourne une valeur imbriquee sans faire planter l'audit.
def nested_get(payload: dict[str, Any] | None, *keys: str) -> Any:
    current_value: Any = payload
    for key in keys:
        if not isinstance(current_value, dict):
            return None
        current_value = current_value.get(key)
    return current_value


# Convertit une valeur numerique en float ou None pour les colonnes d'audit.
def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# Arrondit une valeur pour rendre le CSV plus lisible.
def rounded(value: Any, digits: int = 6) -> float | None:
    numeric_value = safe_float(value)
    if numeric_value is None:
        return None
    return round(numeric_value, digits)


# Derive l'issue exclue de la double chance pour diagnostiquer les abstentions.
def derive_double_chance_gap(market_predictions: dict[str, Any]) -> dict[str, Any]:
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
            "excluded_outcome": None,
            "excluded_probability": None,
            "double_chance_gap_to_threshold": None,
        }

    excluded_outcome = min(valid_probabilities, key=lambda key: valid_probabilities[key])
    excluded_probability = valid_probabilities[excluded_outcome]

    return {
        "excluded_outcome": excluded_outcome,
        "excluded_probability": round(excluded_probability, 6),
        "double_chance_gap_to_threshold": round(
            excluded_probability - DOUBLE_CHANCE_EXCLUDED_THRESHOLD,
            6,
        ),
    }


# Explique pourquoi un match calcule se retrouve en abstention stricte.
def diagnose_abstention_reason(response: dict[str, Any]) -> str:
    market_predictions = response.get("market_predictions", {})
    one_x_two_prediction = nested_get(market_predictions, "1x2", "prediction")
    one_x_two_max_probability = safe_float(
        nested_get(market_predictions, "1x2", "max_probability")
    )
    over_1_5_prediction = nested_get(market_predictions, "over_1_5", "prediction")
    over_1_5_yes_probability = safe_float(
        nested_get(market_predictions, "over_1_5", "probabilities", "YES")
    )
    over_2_5_max_probability = safe_float(
        nested_get(market_predictions, "over_2_5", "max_probability")
    )
    btts_prediction = nested_get(market_predictions, "btts", "prediction")
    btts_no_probability = safe_float(
        nested_get(market_predictions, "btts", "probabilities", "NO")
    )
    double_chance = derive_double_chance_gap(market_predictions)

    reasons: list[str] = []

    if one_x_two_prediction == "DRAW":
        reasons.append("STRICT_1X2 refuse car prediction DRAW")
    elif (one_x_two_max_probability or 0.0) < STRICT_1X2_THRESHOLD:
        reasons.append("STRICT_1X2 sous seuil 0.76")

    if over_1_5_prediction != "YES":
        reasons.append("OVER_1_5 refuse car prediction NO")
    elif (over_1_5_yes_probability or 0.0) < OVER_1_5_YES_THRESHOLD:
        reasons.append("OVER_1_5 YES sous seuil 0.78")

    if (over_2_5_max_probability or 0.0) < OVER_2_5_THRESHOLD:
        reasons.append("OVER_2_5 sous seuil 0.70")

    if btts_prediction != "NO":
        reasons.append("BTTS refuse car prediction YES")
    elif (btts_no_probability or 0.0) < BTTS_NO_THRESHOLD:
        reasons.append("BTTS NO sous seuil 0.75")

    excluded_probability = double_chance.get("excluded_probability")
    if excluded_probability is None:
        reasons.append("DOUBLE_CHANCE impossible car probabilites 1X2 absentes")
    elif excluded_probability > DOUBLE_CHANCE_EXCLUDED_THRESHOLD:
        reasons.append("DOUBLE_CHANCE au-dessus du seuil exclu 0.15")

    return " | ".join(reasons) if reasons else "Abstention sans raison detaillee"


# Transforme une reponse d'inference en ligne CSV d'audit.
def build_audit_row(match: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    selector_result = response.get("selector_result") or {}
    market_predictions = response.get("market_predictions", {})
    double_chance = derive_double_chance_gap(market_predictions)
    selector_status = selector_result.get("status")

    abstention_reason = ""
    if response.get("status") == "unavailable":
        abstention_reason = str(response.get("unavailable_reason") or "")
    elif selector_status == "ABSTAIN":
        abstention_reason = diagnose_abstention_reason(response)

    return {
        "match_id": match.get("id"),
        "utc_date": match.get("utcDate"),
        "competition_code": nested_get(match, "competition", "code"),
        "stage": match.get("stage"),
        "group_name": match.get("group"),
        "home_team": get_team_name(match, "homeTeam"),
        "away_team": get_team_name(match, "awayTeam"),
        "dynamic_status": response.get("status"),
        "selector_status": selector_status,
        "selected_market": selector_result.get("selected_market"),
        "selected_prediction": selector_result.get("selected_prediction"),
        "selected_confidence": rounded(selector_result.get("selected_confidence")),
        "risk_level": selector_result.get("risk_level"),
        "unavailable_reason": response.get("unavailable_reason"),
        "abstention_reason": abstention_reason,
        "1x2_prediction": nested_get(market_predictions, "1x2", "prediction"),
        "1x2_max_probability": rounded(
            nested_get(market_predictions, "1x2", "max_probability")
        ),
        "1x2_prob_team_a_win": rounded(
            nested_get(market_predictions, "1x2", "probabilities", "TEAM_A_WIN")
        ),
        "1x2_prob_draw": rounded(
            nested_get(market_predictions, "1x2", "probabilities", "DRAW")
        ),
        "1x2_prob_team_b_win": rounded(
            nested_get(market_predictions, "1x2", "probabilities", "TEAM_B_WIN")
        ),
        "over_1_5_prediction": nested_get(market_predictions, "over_1_5", "prediction"),
        "over_1_5_prob_yes": rounded(
            nested_get(market_predictions, "over_1_5", "probabilities", "YES")
        ),
        "over_2_5_prediction": nested_get(market_predictions, "over_2_5", "prediction"),
        "over_2_5_max_probability": rounded(
            nested_get(market_predictions, "over_2_5", "max_probability")
        ),
        "btts_prediction": nested_get(market_predictions, "btts", "prediction"),
        "btts_prob_no": rounded(
            nested_get(market_predictions, "btts", "probabilities", "NO")
        ),
        "double_chance_excluded_outcome": double_chance.get("excluded_outcome"),
        "double_chance_excluded_probability": double_chance.get("excluded_probability"),
        "double_chance_gap_to_threshold": double_chance.get(
            "double_chance_gap_to_threshold"
        ),
    }


# Execute l'inference V18.3.3 dynamique sur tous les matchs WC du cache.
def run_dynamic_wc_audit(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.services.ml_national_v18_3_3_dynamic_inference_service import (
        infer_v18_3_3_for_rubybets_match,
    )

    audit_rows: list[dict[str, Any]] = []

    for match in matches:
        try:
            response = infer_v18_3_3_for_rubybets_match(match)
            audit_rows.append(build_audit_row(match, response))
        except Exception as error:  # noqa: BLE001 - audit volontairement robuste.
            audit_rows.append(
                {
                    "match_id": match.get("id"),
                    "utc_date": match.get("utcDate"),
                    "competition_code": nested_get(match, "competition", "code"),
                    "stage": match.get("stage"),
                    "group_name": match.get("group"),
                    "home_team": get_team_name(match, "homeTeam"),
                    "away_team": get_team_name(match, "awayTeam"),
                    "dynamic_status": "error",
                    "selector_status": None,
                    "selected_market": None,
                    "selected_prediction": None,
                    "selected_confidence": None,
                    "risk_level": None,
                    "unavailable_reason": None,
                    "abstention_reason": str(error),
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
                    "double_chance_excluded_outcome": None,
                    "double_chance_excluded_probability": None,
                    "double_chance_gap_to_threshold": None,
                }
            )

    return audit_rows


# Sauvegarde les lignes d'audit dans un CSV exploitable pour analyse.
def write_audit_csv(project_root: Path, audit_rows: list[dict[str, Any]]) -> Path:
    output_path = project_root / CSV_OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(audit_rows[0].keys()) if audit_rows else ["status"]

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)

    return output_path


# Construit le contenu textuel de synthese de l'audit.
def build_summary_text(
    audit_rows: list[dict[str, Any]],
    cache_path: Path,
    csv_output_path: Path,
) -> str:
    total_rows = len(audit_rows)
    dynamic_status_counts = Counter(row.get("dynamic_status") for row in audit_rows)
    selector_status_counts = Counter(row.get("selector_status") for row in audit_rows)
    selected_market_counts = Counter(row.get("selected_market") for row in audit_rows)
    abstention_reason_counts = Counter(
        row.get("abstention_reason")
        for row in audit_rows
        if row.get("abstention_reason")
    )

    recommended_rows = selector_status_counts.get("RECOMMEND", 0)
    abstained_rows = selector_status_counts.get("ABSTAIN", 0)
    unavailable_rows = dynamic_status_counts.get("unavailable", 0)
    error_rows = dynamic_status_counts.get("error", 0)

    recommendation_rate = recommended_rows / total_rows if total_rows else 0.0
    strict_abstention_rate = abstained_rows / total_rows if total_rows else 0.0
    unavailable_rate = unavailable_rows / total_rows if total_rows else 0.0

    lines = [
        "Audit V18.3.3 dynamique - abstention World Cup",
        "================================================",
        f"Cache analyse : {cache_path}",
        f"CSV detaille : {csv_output_path}",
        "",
        f"Matchs analyses : {total_rows}",
        f"Recommandations : {recommended_rows} ({recommendation_rate:.4f})",
        f"Abstentions strictes : {abstained_rows} ({strict_abstention_rate:.4f})",
        f"Indisponibles : {unavailable_rows} ({unavailable_rate:.4f})",
        f"Erreurs techniques : {error_rows}",
        "",
        "Repartition dynamic_status :",
    ]

    for status, count in dynamic_status_counts.most_common():
        lines.append(f"- {status}: {count}")

    lines.append("")
    lines.append("Repartition selector_status :")
    for status, count in selector_status_counts.most_common():
        lines.append(f"- {status}: {count}")

    lines.append("")
    lines.append("Repartition selected_market :")
    for market, count in selected_market_counts.most_common():
        lines.append(f"- {market}: {count}")

    lines.append("")
    lines.append("Principales raisons d'abstention ou d'indisponibilite :")
    for reason, count in abstention_reason_counts.most_common(12):
        lines.append(f"- {count} x {reason}")

    lines.append("")
    lines.append("Decision recommandee :")
    lines.append(
        "Ne pas modifier V18.3.3 directement. Utiliser cet audit pour definir "
        "une variante experimentale V18.3.4 plus souple, puis comparer couverture "
        "et prudence avant integration produit."
    )

    return "\n".join(lines) + "\n"


# Sauvegarde la synthese texte de l'audit.
def write_summary(project_root: Path, summary_text: str) -> Path:
    output_path = project_root / SUMMARY_OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary_text, encoding="utf-8")
    return output_path


# Point d'entree du script d'audit.
def main() -> None:
    project_root = find_project_root()
    configure_python_path(project_root)

    matches, cache_path, _cache_payload = load_wc_matches(project_root)
    audit_rows = run_dynamic_wc_audit(matches)
    csv_output_path = write_audit_csv(project_root, audit_rows)
    summary_text = build_summary_text(audit_rows, cache_path, csv_output_path)
    summary_output_path = write_summary(project_root, summary_text)

    print(summary_text)
    print(f"Summary saved: {summary_output_path}")
    print(f"CSV saved: {csv_output_path}")


if __name__ == "__main__":
    main()


# Schema de communication :
# audit_v18_3_3_dynamic_wc_abstention.py
#   -> lit backend/app/data/cache/matches_wc_scheduled_all_start_dates_all_end_dates.json
#   -> appelle backend/app/services/ml_national_v18_3_3_dynamic_inference_service.py
#   -> utilise indirectement les modeles models/ml_national/v18_3_global_multimarket/*.joblib
#   -> ecrit reports/evidence/ml_training/370_*_summary.txt et 371_*_results.csv
