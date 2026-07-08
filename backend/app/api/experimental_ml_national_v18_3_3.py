# Role du fichier :
# Cette route expose le selecteur national V18.3.3 strict reliability en API experimentale.
# Elle sert a tester le modele national sans utiliser le modele clubs ni les cotes FlashScore.

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.cache_service import (
    build_cache_name,
    build_data_freshness,
    get_cached_football_data,
    is_cache_fresh,
    load_cache,
    save_cache,
)
from app.services.ml_national_v18_3_3_dynamic_inference_service import (
    get_match_last_updated,
    infer_v18_3_3_for_rubybets_match,
)
from app.services.ml_national_v18_3_3_inference_adapter import (
    select_v18_3_3_from_prediction_row,
)
from app.services.match_service import clean_params, format_match
from app.services.archives_service import archive_national_dynamic_predictions
from app.services.rapidapi_flashscore_client import (
    FLASHSCORE_SOURCE,
    get_normalized_flashscore_match_details,
)
from app.services.ml_national_v18_3_3_selector import (
    SELECTOR_PROFILE,
    SELECTOR_VARIANT,
    SELECTOR_VERSION,
    select_market_with_v18_3_3,
)


V18_3_TEST_PREDICTIONS_RELATIVE_PATH = Path(
    "reports/evidence/ml_training/348_v18_3_global_multimarket_test_predictions.csv"
)

MATCH_DETAIL_CACHE_TTL_MINUTES = 30
FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES = 720

router = APIRouter(
    prefix="/api/experimental/ml-national/v18-3-3",
    tags=["Experimental ML National V18.3.3"],
)


# Ce modele decrit les signaux multi-marches attendus par le selecteur V18.3.3.
class V1833SelectorRequest(BaseModel):
    one_x_two_prediction: str | None = None
    one_x_two_max_probability: float | None = None
    one_x_two_prob_team_a_win: float | None = None
    one_x_two_prob_draw: float | None = None
    one_x_two_prob_team_b_win: float | None = None
    over_1_5_prediction: str | None = None
    over_1_5_prob_yes: float | None = None
    over_2_5_prediction: str | None = None
    over_2_5_max_probability: float | None = None
    btts_prediction: str | None = None
    btts_prob_no: float | None = None


# Ce modele decrit les paramètres autorises pour agreger plusieurs signaux ML nationaux.
class V1833NationalSelectionRequest(BaseModel):
    competition_code: str = "WC"
    match_count: int = Field(default=3, ge=1, le=5)
    risk_level: Literal["low", "medium", "high"] = "low"
    date_from: str | None = None
    date_to: str | None = None


# Transforme le format API lisible en format interne attendu par le service.
def build_selector_features_from_request(
    request: V1833SelectorRequest,
) -> dict[str, Any]:
    return {
        "1x2_prediction": request.one_x_two_prediction,
        "1x2_max_probability": request.one_x_two_max_probability,
        "1x2_prob_TEAM_A_WIN": request.one_x_two_prob_team_a_win,
        "1x2_prob_DRAW": request.one_x_two_prob_draw,
        "1x2_prob_TEAM_B_WIN": request.one_x_two_prob_team_b_win,
        "over_1_5_prediction": request.over_1_5_prediction,
        "over_1_5_prob_YES": request.over_1_5_prob_yes,
        "over_2_5_prediction": request.over_2_5_prediction,
        "over_2_5_max_probability": request.over_2_5_max_probability,
        "btts_prediction": request.btts_prediction,
        "btts_prob_NO": request.btts_prob_no,
    }


# Construit un exemple controle pour verifier rapidement le fonctionnement de l'API.
def build_v18_3_3_demo_features() -> dict[str, Any]:
    return {
        "1x2_prediction": "TEAM_A_WIN",
        "1x2_max_probability": 0.81,
        "1x2_prob_TEAM_A_WIN": 0.81,
        "1x2_prob_DRAW": 0.11,
        "1x2_prob_TEAM_B_WIN": 0.08,
        "over_1_5_prediction": "YES",
        "over_1_5_prob_YES": 0.79,
        "over_2_5_prediction": "OVER",
        "over_2_5_max_probability": 0.71,
        "btts_prediction": "NO",
        "btts_prob_NO": 0.76,
    }


# Retourne les emplacements possibles du projet selon le dossier de lancement du backend.
def get_project_root_candidates() -> list[Path]:
    api_file_path = Path(__file__).resolve()

    candidates = [
        api_file_path.parents[3],
        Path.cwd(),
        Path.cwd().parent,
    ]

    unique_candidates: list[Path] = []
    for candidate in candidates:
        resolved_candidate = candidate.resolve()
        if resolved_candidate not in unique_candidates:
            unique_candidates.append(resolved_candidate)

    return unique_candidates


# Retrouve le fichier CSV 348 qui contient les predictions V18.3 globales de test.
def get_v18_3_predictions_csv_path() -> Path:
    for project_root in get_project_root_candidates():
        csv_path = project_root / V18_3_TEST_PREDICTIONS_RELATIVE_PATH
        if csv_path.exists():
            return csv_path

    return get_project_root_candidates()[0] / V18_3_TEST_PREDICTIONS_RELATIVE_PATH


# Cette fonction indique si FlashScore RapidAPI peut être utilisé pour l'inférence nationale dynamique.
def is_flashscore_available_for_dynamic_inference() -> bool:
    return bool(settings.rapidapi_key.strip())


# Cette fonction construit le nom de cache utilisé pour les fiches match FlashScore.
def build_flashscore_match_detail_cache_name(match_id: int) -> str:
    return build_cache_name("flashscore_match", match_id)


# Cette fonction récupère une fiche match FlashScore depuis le cache ou RapidAPI.
def get_cached_flashscore_match_detail_for_dynamic_inference(
    match_id: int,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    cache_name = build_flashscore_match_detail_cache_name(match_id)
    cached_payload = load_cache(cache_name)

    if cached_payload and is_cache_fresh(
        cached_payload,
        ttl_minutes=FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
    ):
        cached_data = cached_payload.get("data", {})
        return (
            cached_data.get("match"),
            cached_data.get("metadata", {}),
            build_data_freshness(
                cache_payload=cached_payload,
                from_cache=True,
                ttl_minutes=FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
            ),
        )

    match, metadata = get_normalized_flashscore_match_details(match_id)

    if metadata.get("status") != "success" or not match:
        return match, metadata, {
            "source": FLASHSCORE_SOURCE,
            "from_cache": False,
            "updated_at": None,
            "ttl_minutes": FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
        }

    saved_payload = save_cache(
        cache_name,
        {"match": match, "metadata": metadata},
        source=FLASHSCORE_SOURCE,
    )

    return (
        saved_payload["data"].get("match"),
        saved_payload["data"].get("metadata", metadata),
        build_data_freshness(
            cache_payload=saved_payload,
            from_cache=False,
            ttl_minutes=FLASHSCORE_MATCH_DETAIL_CACHE_TTL_MINUTES,
        ),
    )


# Cette fonction vérifie si une compétition FlashScore correspond au périmètre national World Cup.
def is_flashscore_world_cup_like_competition(competition: dict[str, Any]) -> bool:
    competition_code = str(competition.get("code") or "").upper()
    competition_name = str(competition.get("name") or "").lower()

    if competition_code == "WC":
        return True

    return "world cup" in competition_name or "world championship" in competition_name


# Cette fonction déduit une phase groupe prudente depuis le libellé FlashScore quand le stage est absent.
def infer_stage_from_flashscore_competition_name(competition_name: str | None) -> str | None:
    normalized_name = str(competition_name or "").lower()

    if "round 1" in normalized_name or "group" in normalized_name:
        return "GROUP_STAGE"

    return None


# Cette fonction normalise une fiche FlashScore pour l'inférence nationale sans modifier les données sportives.
def normalize_flashscore_match_for_national_dynamic_inference(
    match: dict[str, Any],
) -> dict[str, Any]:
    normalized_match = dict(match)
    competition = dict(normalized_match.get("competition") or {})

    if is_flashscore_world_cup_like_competition(competition):
        competition["original_code"] = competition.get("code")
        competition["code"] = "WC"
        normalized_match["competition"] = competition

    if not normalized_match.get("stage"):
        inferred_stage = infer_stage_from_flashscore_competition_name(
            competition.get("name")
        )
        if inferred_stage:
            normalized_match["stage"] = inferred_stage

    return normalized_match


# Cette fonction construit les métadonnées de fraîcheur FlashScore pour la route expérimentale nationale.
def build_flashscore_dynamic_freshness(
    freshness: dict[str, Any],
    metadata: dict[str, Any],
    match: dict[str, Any],
) -> dict[str, Any]:
    return {
        "match_cache": {
            **freshness,
            "provider": FLASHSCORE_SOURCE,
            "metadata": metadata,
        },
        "match_last_updated": get_match_last_updated(match),
    }


# Charge la ligne CSV correspondant au clean_match_id demande.
def load_v18_3_prediction_row_by_clean_match_id(
    clean_match_id: str,
) -> dict[str, Any] | None:
    csv_path = get_v18_3_predictions_csv_path()

    if not csv_path.exists():
        raise HTTPException(
            status_code=503,
            detail={
                "status": "CSV_UNAVAILABLE",
                "message": (
                    "Le fichier de predictions V18.3 globales est introuvable. "
                    "La route experimentale ne peut pas calculer V18.3.3."
                ),
                "expected_file": str(V18_3_TEST_PREDICTIONS_RELATIVE_PATH),
            },
        )

    requested_id = str(clean_match_id).strip()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            row_match_id = str(row.get("clean_match_id", "")).strip()
            if row_match_id == requested_id:
                return row

    return None


# Cette fonction verifie que la selection nationale reste dans le perimetre experimental WC.
def ensure_national_selection_competition_supported(competition_code: str) -> None:
    if competition_code != "WC":
        raise HTTPException(
            status_code=400,
            detail=(
                "La selection ML nationale V18.3.4 dc018 est limitee a la "
                "competition WC dans cette phase experimentale."
            ),
        )


# Cette fonction construit le nom de cache utilise pour les matchs de la selection nationale.
def build_national_selection_matches_cache_name(
    competition_code: str,
    date_from: str | None,
    date_to: str | None,
) -> str:
    return build_cache_name(
        "national_selection_matches",
        competition_code,
        "scheduled",
        date_from or "all_start_dates",
        date_to or "all_end_dates",
    )


# Cette fonction convertit prudemment une valeur numerique de selecteur.
def safe_selector_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


# Cette fonction calcule la cle de tri d'un candidat de selection nationale.
def build_national_selection_sort_key(candidate: dict[str, Any]) -> tuple[float, float]:
    return (
        safe_selector_float(candidate.get("selected_confidence")),
        safe_selector_float(candidate.get("reference_reliability")),
    )


# Cette fonction transforme l'inference d'un match en candidat exploitable pour l'ecran Selection.
def build_national_selection_candidate(
    match: dict[str, Any],
    inference_response: dict[str, Any],
) -> dict[str, Any] | None:
    selector_result = inference_response.get("selector_result")

    if not isinstance(selector_result, dict):
        return None

    if selector_result.get("status") != "RECOMMEND":
        return None

    selected_confidence = safe_selector_float(
        selector_result.get("selected_confidence")
    )
    reference_reliability = safe_selector_float(
        selector_result.get("reference_reliability")
    )

    return {
        "match": format_match(match),
        "selected_market": selector_result.get("selected_market"),
        "selected_prediction": selector_result.get("selected_prediction"),
        "selected_confidence": selected_confidence,
        "risk_level": selector_result.get("risk_level"),
        "selector_rule": selector_result.get("selector_rule"),
        "reference_reliability": reference_reliability,
        "reference_coverage": selector_result.get("reference_coverage"),
        "reference_selected_rows": selector_result.get("reference_selected_rows"),
        "selector_version": selector_result.get("selector_version"),
        "selector_profile": selector_result.get("selector_profile"),
        "selector_variant": selector_result.get("selector_variant"),
        "model_family": "national",
        "model_variant": "v18_3_4_dc018",
        "odds_used": False,
        "source_match_prediction": inference_response.get("source"),
        "consistency_checks": inference_response.get("consistency_checks"),
        "responsible_note": selector_result.get("responsible_note"),
    }


# Cette fonction garde les candidats compatibles avec le niveau de risque demande.
def filter_national_selection_candidates_by_risk(
    candidates: list[dict[str, Any]],
    risk_level: str,
) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if candidate.get("risk_level") == risk_level
    ]


# Cette fonction construit une reponse stable pour l'ecran Selection ML nationale.
def build_national_selection_response(
    request: V1833NationalSelectionRequest,
    available_matches_count: int,
    computed_matches_count: int,
    skipped_matches_count: int,
    selected_recommendations: list[dict[str, Any]],
    matches_freshness: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": "rubybets_ml_national_v18_3_4_selection",
        "scope": "experimental_backend",
        "status": "computed" if selected_recommendations else "empty",
        "method": "national_ml_selector_aggregation_v1",
        "request": {
            "competition_code": request.competition_code.upper(),
            "match_count": request.match_count,
            "risk_level": request.risk_level,
            "date_from": request.date_from,
            "date_to": request.date_to,
        },
        "available_matches_count": available_matches_count,
        "computed_matches_count": computed_matches_count,
        "skipped_matches_count": skipped_matches_count,
        "selected_count": len(selected_recommendations),
        "recommendations": selected_recommendations,
        "selection_logic": {
            "description": (
                "RubyBets agrege les selector_result deja produits par le modele "
                "national experimental V18.3.4 dc018 pour chaque match compatible."
            ),
            "risk_filter": (
                "La selection conserve uniquement les signaux dont le risk_level "
                "correspond au niveau demande."
            ),
            "sorting": (
                "Les signaux sont tries par selected_confidence decroissante, "
                "puis par reference_reliability decroissante."
            ),
        },
        "limits": [
            "Selection analytique experimentale sans garantie de resultat sportif.",
            "RubyBets ne permet aucun pari reel.",
            "Les signaux proviennent du meme moteur que l'ecran Predictions.",
            "Aucune cote FlashScore n'est utilisee.",
        ],
        "data_freshness": {
            "provider": "football-data.org",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "matches_cache": matches_freshness,
        },
    }


# Expose le statut technique du profil V18.3.3 strict reliability.
@router.get("/status")
async def get_v18_3_3_selector_status() -> dict[str, Any]:
    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "available",
        "selector_version": SELECTOR_VERSION,
        "selector_profile": SELECTOR_PROFILE,
        "selector_variant": SELECTOR_VARIANT,
        "message": (
            "Selecteur national V18.3.3 strict reliability disponible en API "
            "experimentale. Non integre au frontend."
        ),
        "responsible_note": (
            "Profil analytique experimental sans garantie de resultat sportif."
        ),
    }


# Expose une demonstration controlee du selecteur V18.3.3.
@router.get("/demo")
async def get_v18_3_3_selector_demo() -> dict[str, Any]:
    demo_features = build_v18_3_3_demo_features()
    result = select_market_with_v18_3_3(demo_features)

    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "demo_only",
        "demo_features_profile": "controlled_strict_1x2_case",
        "result": result,
    }


# Applique le selecteur V18.3.3 a un match reel du CSV 348.
@router.get("/matches/{clean_match_id}")
async def get_v18_3_3_prediction_by_clean_match_id(
    clean_match_id: str,
) -> dict[str, Any]:
    prediction_row = load_v18_3_prediction_row_by_clean_match_id(clean_match_id)

    if prediction_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "MATCH_NOT_FOUND",
                "message": (
                    "Aucune ligne V18.3 globale ne correspond au clean_match_id fourni."
                ),
                "clean_match_id": clean_match_id,
                "data_source_file": V18_3_TEST_PREDICTIONS_RELATIVE_PATH.name,
            },
        )

    adapter_response = select_v18_3_3_from_prediction_row(prediction_row)

    if adapter_response.get("status") != "computed":
        raise HTTPException(
            status_code=422,
            detail={
                "status": "INVALID_PREDICTION_ROW",
                "message": (
                    "La ligne V18.3 existe, mais elle est incomplete ou incompatible "
                    "avec le selecteur V18.3.3."
                ),
                "clean_match_id": clean_match_id,
                "adapter_response": adapter_response,
            },
        )

    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "computed",
        "data_source_file": V18_3_TEST_PREDICTIONS_RELATIVE_PATH.name,
        "match": adapter_response["match"],
        "selector_result": adapter_response["selector_result"],
        "responsible_note": (
            "Resultat experimental de laboratoire ML. Ne remplace pas les predictions "
            "officielles RubyBets et ne garantit aucun resultat sportif."
        ),
    }


# Applique V18.3.4 dc018 dynamiquement au match RubyBets selectionne dans le frontend.
@router.get("/rubybets-matches/{match_id}")
async def get_v18_3_3_dynamic_prediction_by_rubybets_match_id(
    match_id: int,
) -> dict[str, Any]:
    if is_flashscore_available_for_dynamic_inference():
        flashscore_match, flashscore_metadata, flashscore_freshness = (
            get_cached_flashscore_match_detail_for_dynamic_inference(match_id)
        )

        if flashscore_match and flashscore_metadata.get("status") == "success":
            normalized_match = normalize_flashscore_match_for_national_dynamic_inference(
                flashscore_match
            )
            inference_response = infer_v18_3_3_for_rubybets_match(normalized_match)
            archive_status = archive_national_dynamic_predictions(
                inference_response=inference_response,
                rubybets_match_id=match_id,
                source_match=normalized_match,
            )

            return {
                **inference_response,
                "archive": archive_status,
                "rubybets_match_id": match_id,
                "source_used_for_match": FLASHSCORE_SOURCE,
                "model_family": "national",
                "model_variant": "v18_3_4_dc018",
                "odds_used": False,
                "data_freshness": build_flashscore_dynamic_freshness(
                    freshness=flashscore_freshness,
                    metadata=flashscore_metadata,
                    match=normalized_match,
                ),
            }

    data, data_freshness = await get_cached_football_data(
        cache_name=build_cache_name("match", match_id),
        endpoint=f"/matches/{match_id}",
        ttl_minutes=MATCH_DETAIL_CACHE_TTL_MINUTES,
    )
    match = data.get("match", data)
    inference_response = infer_v18_3_3_for_rubybets_match(match)
    archive_status = archive_national_dynamic_predictions(
        inference_response=inference_response,
        rubybets_match_id=match_id,
        source_match=match,
    )

    return {
        **inference_response,
        "archive": archive_status,
        "rubybets_match_id": match_id,
        "source_used_for_match": "football-data.org",
        "model_family": "national",
        "model_variant": "v18_3_4_dc018",
        "odds_used": False,
        "data_freshness": {
            "match_cache": data_freshness,
            "match_last_updated": get_match_last_updated(match),
        },
    }


# Genere une selection multi-matchs depuis les selector_result du modele national dynamique.
@router.post("/selection")
async def generate_v18_3_3_national_selection(
    request: V1833NationalSelectionRequest,
) -> dict[str, Any]:
    competition_code = request.competition_code.upper()
    ensure_national_selection_competition_supported(competition_code)

    matches_data, matches_freshness = await get_cached_football_data(
        cache_name=build_national_selection_matches_cache_name(
            competition_code=competition_code,
            date_from=request.date_from,
            date_to=request.date_to,
        ),
        endpoint=f"/competitions/{competition_code}/matches",
        params=clean_params(
            {
                "status": "SCHEDULED",
                "dateFrom": request.date_from,
                "dateTo": request.date_to,
            }
        ),
        ttl_minutes=MATCH_DETAIL_CACHE_TTL_MINUTES,
    )

    matches = matches_data.get("matches", [])
    candidates: list[dict[str, Any]] = []
    computed_matches_count = 0
    skipped_matches_count = 0

    for match in matches:
        inference_response = infer_v18_3_3_for_rubybets_match(match)

        if inference_response.get("status") != "computed":
            skipped_matches_count += 1
            continue

        computed_matches_count += 1
        candidate = build_national_selection_candidate(
            match=match,
            inference_response=inference_response,
        )

        if candidate:
            candidates.append(candidate)

    matching_risk_candidates = filter_national_selection_candidates_by_risk(
        candidates=candidates,
        risk_level=request.risk_level,
    )
    matching_risk_candidates.sort(
        key=build_national_selection_sort_key,
        reverse=True,
    )
    selected_recommendations = matching_risk_candidates[: request.match_count]

    return build_national_selection_response(
        request=request,
        available_matches_count=len(matches),
        computed_matches_count=computed_matches_count,
        skipped_matches_count=skipped_matches_count,
        selected_recommendations=selected_recommendations,
        matches_freshness=matches_freshness,
    )


# Applique le selecteur V18.3.3 a des features envoyees manuellement.
@router.post("/select")
async def select_with_v18_3_3(
    request: V1833SelectorRequest,
) -> dict[str, Any]:
    features = build_selector_features_from_request(request)
    result = select_market_with_v18_3_3(features)

    return {
        "source": "rubybets_ml_national_v18_3_3_api",
        "scope": "experimental_backend",
        "status": "computed",
        "result": result,
    }


# Schema de communication :
# experimental_ml_national_v18_3_3.py
#   -> expose /status, /demo, /select, /matches/{clean_match_id} et /rubybets-matches/{match_id}
#   -> lit le CSV reports/evidence/ml_training/348_v18_3_global_multimarket_test_predictions.csv
#   -> appelle backend/app/services/ml_national_v18_3_3_inference_adapter.py pour les tests CSV
#   -> appelle backend/app/services/ml_national_v18_3_3_dynamic_inference_service.py pour le match frontend
#   -> appelle indirectement backend/app/services/ml_national_v18_3_3_selector.py
#   -> retourne match + selector_result pour un lab experimental sans toucher aux routes officielles