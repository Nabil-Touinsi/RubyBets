# Ce fichier construit les statistiques avancées avant-match à partir des cinq derniers matchs FlashScore terminés.
# Il oriente les données par identifiant d'équipe, agrège uniquement les valeurs disponibles et conserve les limites de couverture.

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.services.rapidapi_flashscore_client import (
    FLASHSCORE_MATCH_STATS_CACHE_TTL_MINUTES,
    FLASHSCORE_SOURCE,
    find_flashscore_match,
    get_flashscore_match_stats,
    get_normalized_flashscore_team_results,
)
from app.services.team_history_service import (
    get_flashscore_source_team_id,
    get_match_data_for_team_history,
)


ADVANCED_STATS_SAMPLE_SIZE = 5
ADVANCED_STATS_MAX_CONCURRENCY = 4
ADVANCED_STATS_EXPECTED_METRICS = {
    "goals_for",
    "goals_against",
    "expected_goals_for",
    "expected_goals_against",
    "xgot_for",
    "xgot_against",
    "ball_possession",
    "total_shots",
    "shots_on_target",
    "shots_off_target",
    "blocked_shots",
    "big_chances",
    "corner_kicks",
    "touches_in_opposition_box",
    "pass_accuracy",
    "final_third_pass_accuracy",
    "expected_assists",
    "fouls",
    "yellow_cards",
    "red_cards",
    "tackle_success",
    "duels_won",
    "clearances",
    "interceptions",
    "errors_leading_to_shot",
    "errors_leading_to_goal",
    "goalkeeper_saves",
    "xgot_faced",
    "goals_prevented",
}
ADVANCED_STATS_DIRECT_METRICS = {
    "expected_goals": ("expected_goals_for", "expected_goals_against", "per_match"),
    "xg_on_target": ("xgot_for", "xgot_against", "per_match"),
    "ball_possession": ("ball_possession", None, "percent"),
    "total_shots": ("total_shots", "shots_conceded", "per_match"),
    "shots_on_target": ("shots_on_target", "shots_on_target_conceded", "per_match"),
    "shots_off_target": ("shots_off_target", None, "per_match"),
    "blocked_shots": ("blocked_shots", None, "per_match"),
    "shots_inside_box": ("shots_inside_box", None, "per_match"),
    "shots_outside_box": ("shots_outside_box", None, "per_match"),
    "hit_woodwork": ("hit_woodwork", None, "per_match"),
    "big_chances": ("big_chances", None, "per_match"),
    "corner_kicks": ("corner_kicks", None, "per_match"),
    "touches_in_opposition_box": ("touches_in_opposition_box", None, "per_match"),
    "accurate_through_passes": ("accurate_through_passes", None, "per_match"),
    "offsides": ("offsides", None, "per_match"),
    "free_kicks": ("free_kicks", None, "per_match"),
    "passes": ("pass_accuracy", None, "percent"),
    "long_passes": ("long_pass_accuracy", None, "percent"),
    "passes_in_final_third": ("final_third_pass_accuracy", None, "percent"),
    "crosses": ("cross_accuracy", None, "percent"),
    "expected_assists": ("expected_assists", None, "per_match"),
    "throw_ins": ("throw_ins", None, "per_match"),
    "fouls": ("fouls", None, "per_match"),
    "yellow_cards": ("yellow_cards", None, "per_match"),
    "red_cards": ("red_cards", None, "per_match"),
    "tackles": ("tackle_success", None, "percent"),
    "duels_won": ("duels_won", None, "per_match"),
    "clearances": ("clearances", None, "per_match"),
    "interceptions": ("interceptions", None, "per_match"),
    "errors_leading_to_shot": ("errors_leading_to_shot", None, "per_match"),
    "errors_leading_to_goal": ("errors_leading_to_goal", None, "per_match"),
    "goalkeeper_saves": ("goalkeeper_saves", None, "per_match"),
    "xgot_faced": ("xgot_faced", None, "per_match"),
    "goals_prevented": ("goals_prevented", None, "per_match"),
}


# Cette fonction retourne un horodatage UTC stable pour la fraîcheur de la réponse publique.
def get_advanced_stats_now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# Cette fonction compare deux identifiants d'équipe sans dépendre de leur type source.
def are_source_ids_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False

    return str(left).strip() == str(right).strip()


# Cette fonction extrait l'identifiant FlashScore source d'une équipe normalisée.
def extract_match_team_source_id(team: dict[str, Any]) -> str | None:
    source_team_id = team.get("sourceTeamId") or team.get("source_team_id") or team.get("id")
    return str(source_team_id) if source_team_id is not None else None


# Cette fonction détermine le côté de l'équipe étudiée uniquement avec les identifiants source.
def resolve_team_side(match: dict[str, Any], source_team_id: str) -> str | None:
    home_team_id = extract_match_team_source_id(match.get("homeTeam", {}) or {})
    away_team_id = extract_match_team_source_id(match.get("awayTeam", {}) or {})

    if are_source_ids_equal(home_team_id, source_team_id):
        return "home"

    if are_source_ids_equal(away_team_id, source_team_id):
        return "away"

    return None


# Cette fonction extrait l'identifiant source du match récent utilisé pour appeler FlashScore Stats.
def extract_source_match_id(match: dict[str, Any]) -> str | None:
    source_match_id = match.get("sourceMatchId") or match.get("source_match_id")

    if source_match_id:
        return str(source_match_id)

    match_id = match.get("id")

    if isinstance(match_id, str) and match_id.startswith("flashscore_"):
        return match_id.removeprefix("flashscore_")

    return None


# Cette fonction extrait les buts pour et contre selon le côté réel de l'équipe étudiée.
def extract_goals_for_against(match: dict[str, Any], side: str) -> tuple[int | float | None, int | float | None]:
    full_time = match.get("score", {}).get("fullTime", {}) or {}
    home_score = full_time.get("home")
    away_score = full_time.get("away")

    if home_score is None or away_score is None:
        return None, None

    if side == "home":
        return home_score, away_score

    return away_score, home_score


# Cette fonction retourne la valeur normalisée correspondant au côté demandé.
def extract_oriented_stat_value(stat: dict[str, Any], side: str) -> dict[str, Any] | None:
    return stat.get("home_team" if side == "home" else "away_team")


# Cette fonction retourne la valeur adverse d'une statistique normalisée.
def extract_opponent_stat_value(stat: dict[str, Any], side: str) -> dict[str, Any] | None:
    return stat.get("away_team" if side == "home" else "home_team")


# Cette fonction ajoute une valeur exploitable à l'échantillon d'un match sans créer de zéro artificiel.
def add_sample_metric(
    sample: dict[str, Any],
    metric_name: str | None,
    normalized_value: dict[str, Any] | None,
) -> None:
    if not metric_name or not normalized_value:
        return

    if normalized_value.get("value") is None:
        return

    sample[metric_name] = normalized_value


# Cette fonction transforme les statistiques d'un match en indicateurs orientés pour une équipe précise.
def build_oriented_match_sample(
    match: dict[str, Any],
    stats_payload: dict[str, Any],
    source_team_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    side = resolve_team_side(match, source_team_id)

    if side is None:
        return None, [
            {
                "code": "team_orientation_failed",
                "match_id": extract_source_match_id(match),
                "message": "L'équipe étudiée n'a pas pu être orientée avec son identifiant source.",
            }
        ]

    sample: dict[str, Any] = {
        "source_match_id": extract_source_match_id(match),
        "utc_date": match.get("utcDate"),
        "team_side": side,
    }
    goals_for, goals_against = extract_goals_for_against(match, side)

    if goals_for is not None:
        sample["goals_for"] = {
            "value": goals_for,
            "percentage": None,
            "successful": None,
            "attempted": None,
            "value_type": "number",
        }

    if goals_against is not None:
        sample["goals_against"] = {
            "value": goals_against,
            "percentage": None,
            "successful": None,
            "attempted": None,
            "value_type": "number",
        }

    normalized_metrics = stats_payload.get("metrics", {}) or {}

    for source_metric, (team_metric, opponent_metric, _) in ADVANCED_STATS_DIRECT_METRICS.items():
        stat = normalized_metrics.get(source_metric)

        if not isinstance(stat, dict):
            continue

        add_sample_metric(sample, team_metric, extract_oriented_stat_value(stat, side))
        add_sample_metric(sample, opponent_metric, extract_opponent_stat_value(stat, side))

    return sample, list(stats_payload.get("limitations", []) or [])


# Cette fonction calcule une moyenne simple sur les valeurs réellement disponibles.
def aggregate_numeric_metric(
    samples: list[dict[str, Any]],
    metric_name: str,
    matches_requested: int,
    unit: str,
) -> dict[str, Any] | None:
    values = [
        float(sample[metric_name]["value"])
        for sample in samples
        if isinstance(sample.get(metric_name), dict)
        and sample[metric_name].get("value") is not None
    ]

    if not values:
        return None

    return {
        "value": round(sum(values) / len(values), 2),
        "unit": unit,
        "matches_used": len(values),
        "matches_requested": matches_requested,
        "coverage": round(len(values) / matches_requested, 2) if matches_requested else 0.0,
    }


# Cette fonction agrège un pourcentage en privilégiant les volumes réussis/tentés disponibles.
def aggregate_percentage_metric(
    samples: list[dict[str, Any]],
    metric_name: str,
    matches_requested: int,
) -> dict[str, Any] | None:
    ratio_values = [
        sample[metric_name]
        for sample in samples
        if isinstance(sample.get(metric_name), dict)
        and sample[metric_name].get("successful") is not None
        and sample[metric_name].get("attempted") is not None
    ]

    if ratio_values:
        successful = sum(int(value["successful"]) for value in ratio_values)
        attempted = sum(int(value["attempted"]) for value in ratio_values)

        if attempted > 0:
            return {
                "value": round((successful / attempted) * 100, 2),
                "unit": "percent",
                "matches_used": len(ratio_values),
                "matches_requested": matches_requested,
                "coverage": round(len(ratio_values) / matches_requested, 2) if matches_requested else 0.0,
                "successful": successful,
                "attempted": attempted,
                "aggregation": "weighted_by_attempts",
            }

    percentage_values = [
        float(sample[metric_name].get("percentage", sample[metric_name].get("value")))
        for sample in samples
        if isinstance(sample.get(metric_name), dict)
        and sample[metric_name].get("percentage", sample[metric_name].get("value")) is not None
    ]

    if not percentage_values:
        return None

    return {
        "value": round(sum(percentage_values) / len(percentage_values), 2),
        "unit": "percent",
        "matches_used": len(percentage_values),
        "matches_requested": matches_requested,
        "coverage": round(len(percentage_values) / matches_requested, 2) if matches_requested else 0.0,
        "aggregation": "mean_available_percentages",
    }


# Cette fonction calcule un ratio transparent uniquement sur les matchs où numérateur et dénominateur existent.
def aggregate_calculated_ratio(
    samples: list[dict[str, Any]],
    numerator_metric: str,
    denominator_metric: str,
    matches_requested: int,
) -> tuple[dict[str, Any] | None, int]:
    paired_values: list[tuple[float, float]] = []
    zero_denominator_matches = 0

    for sample in samples:
        numerator = sample.get(numerator_metric)
        denominator = sample.get(denominator_metric)

        if not isinstance(numerator, dict) or not isinstance(denominator, dict):
            continue

        numerator_value = numerator.get("value")
        denominator_value = denominator.get("value")

        if numerator_value is None or denominator_value is None:
            continue

        denominator_float = float(denominator_value)

        if denominator_float <= 0:
            zero_denominator_matches += 1
            continue

        paired_values.append((float(numerator_value), denominator_float))

    if not paired_values:
        return None, zero_denominator_matches

    numerator_total = sum(value[0] for value in paired_values)
    denominator_total = sum(value[1] for value in paired_values)

    if denominator_total <= 0:
        return None, zero_denominator_matches

    return {
        "value": round((numerator_total / denominator_total) * 100, 2),
        "unit": "percent",
        "matches_used": len(paired_values),
        "matches_requested": matches_requested,
        "coverage": round(len(paired_values) / matches_requested, 2) if matches_requested else 0.0,
        "numerator_total": round(numerator_total, 2),
        "denominator_total": round(denominator_total, 2),
        "formula": f"{numerator_metric} / {denominator_metric}",
    }, zero_denominator_matches


# Cette fonction agrège tous les indicateurs directs et calculés d'une équipe.
def aggregate_team_samples(
    samples: list[dict[str, Any]],
    matches_requested: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metrics: dict[str, Any] = {}
    limitations: list[dict[str, Any]] = []
    numeric_metric_units = {
        "goals_for": "per_match",
        "goals_against": "per_match",
    }

    for _, (team_metric, opponent_metric, unit) in ADVANCED_STATS_DIRECT_METRICS.items():
        if team_metric:
            numeric_metric_units[team_metric] = unit

        if opponent_metric:
            numeric_metric_units[opponent_metric] = unit

    for metric_name, unit in numeric_metric_units.items():
        aggregated_metric = (
            aggregate_percentage_metric(samples, metric_name, matches_requested)
            if unit == "percent"
            else aggregate_numeric_metric(samples, metric_name, matches_requested, unit)
        )

        if aggregated_metric is not None:
            metrics[metric_name] = aggregated_metric

    shot_conversion, conversion_zero_denominators = aggregate_calculated_ratio(
        samples=samples,
        numerator_metric="goals_for",
        denominator_metric="total_shots",
        matches_requested=matches_requested,
    )
    shot_accuracy, accuracy_zero_denominators = aggregate_calculated_ratio(
        samples=samples,
        numerator_metric="shots_on_target",
        denominator_metric="total_shots",
        matches_requested=matches_requested,
    )

    if shot_conversion is not None:
        metrics["shot_conversion"] = shot_conversion

    if shot_accuracy is not None:
        metrics["shot_accuracy"] = shot_accuracy

    if conversion_zero_denominators:
        limitations.append(
            {
                "code": "zero_denominator_excluded",
                "metric": "shot_conversion",
                "matches_count": conversion_zero_denominators,
                "message": "Les matchs sans tir total exploitable sont exclus du ratio de conversion.",
            }
        )

    if accuracy_zero_denominators:
        limitations.append(
            {
                "code": "zero_denominator_excluded",
                "metric": "shot_accuracy",
                "matches_count": accuracy_zero_denominators,
                "message": "Les matchs sans tir total exploitable sont exclus du ratio de précision.",
            }
        )

    return metrics, limitations


# Cette fonction récupère les statistiques d'un match sous un sémaphore de concurrence limité.
async def fetch_match_stats_with_limit(
    semaphore: asyncio.Semaphore,
    match: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    source_match_id = extract_source_match_id(match)

    if not source_match_id:
        return match, None, {
            "provider": FLASHSCORE_SOURCE,
            "status": "missing_match_id",
            "match_id": None,
        }

    async with semaphore:
        payload, metadata = await asyncio.to_thread(get_flashscore_match_stats, source_match_id)

    return match, payload, metadata


# Cette fonction construit le bloc avancé d'une équipe en poursuivant malgré les erreurs unitaires.
async def build_team_advanced_stats(
    team: dict[str, Any],
    source_team_id: str,
    target_utc_date: str | None,
    semaphore: asyncio.Semaphore,
    sample_size: int = ADVANCED_STATS_SAMPLE_SIZE,
) -> dict[str, Any]:
    recent_matches, history_metadata = await asyncio.to_thread(
        get_normalized_flashscore_team_results,
        source_team_id,
        target_utc_date,
        sample_size,
    )
    oriented_matches = [
        match
        for match in recent_matches
        if resolve_team_side(match, source_team_id) is not None
        and extract_source_match_id(match) is not None
    ][:sample_size]
    fetch_results = await asyncio.gather(
        *(fetch_match_stats_with_limit(semaphore, match) for match in oriented_matches),
        return_exceptions=True,
    )
    samples: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    fetch_metadata: list[dict[str, Any]] = []

    for result in fetch_results:
        if isinstance(result, Exception):
            limitations.append(
                {
                    "code": "match_stats_call_failed",
                    "message": str(result),
                }
            )
            continue

        match, stats_payload, metadata = result
        fetch_metadata.append(metadata)

        if (
            not stats_payload
            or metadata.get("status") not in {"success", "empty"}
            or not stats_payload.get("metrics")
        ):
            limitations.append(
                {
                    "code": "match_stats_unavailable",
                    "match_id": extract_source_match_id(match),
                    "status": metadata.get("status"),
                    "message": "Les statistiques détaillées de ce match ne sont pas exploitables.",
                }
            )
            continue

        sample, sample_limitations = build_oriented_match_sample(
            match=match,
            stats_payload=stats_payload,
            source_team_id=source_team_id,
        )
        limitations.extend(sample_limitations)

        if sample and len(sample) > 3:
            samples.append(sample)

    metrics, aggregation_limitations = aggregate_team_samples(samples, sample_size)
    limitations.extend(aggregation_limitations)

    if len(oriented_matches) < sample_size:
        limitations.append(
            {
                "code": "insufficient_recent_matches",
                "matches_found": len(oriented_matches),
                "matches_requested": sample_size,
                "message": "Moins de cinq matchs terminés exploitables ont été trouvés avant la rencontre cible.",
            }
        )

    missing_expected_metrics = sorted(ADVANCED_STATS_EXPECTED_METRICS.difference(metrics))

    if missing_expected_metrics:
        limitations.append(
            {
                "code": "metric_coverage_partial",
                "metrics": missing_expected_metrics,
                "message": "Certaines statistiques attendues ne sont pas fournies par FlashScore sur cet échantillon.",
            }
        )

    return {
        "team_id": source_team_id,
        "team_name": team.get("name"),
        "matches_requested": sample_size,
        "matches_found": len(oriented_matches),
        "matches_with_stats": len(samples),
        "metrics": metrics,
        "limitations": limitations,
        "source_metadata": {
            "team_results": history_metadata,
            "match_stats": fetch_metadata,
        },
    }


# Cette fonction complète les identifiants source en rapprochant le match cible avec FlashScore si nécessaire.
async def resolve_target_flashscore_context(
    match: dict[str, Any],
) -> tuple[str | None, str | None, dict[str, Any]]:
    home_team = match.get("homeTeam", {}) or {}
    away_team = match.get("awayTeam", {}) or {}
    home_source_team_id = get_flashscore_source_team_id(home_team)
    away_source_team_id = get_flashscore_source_team_id(away_team)

    if home_source_team_id and away_source_team_id:
        return home_source_team_id, away_source_team_id, {
            "status": "success",
            "strategy": "target_match_source_ids",
            "source_match_id": match.get("sourceMatchId"),
        }

    flashscore_match, metadata = await asyncio.to_thread(
        find_flashscore_match,
        home_team.get("name"),
        away_team.get("name"),
        match.get("utcDate"),
    )

    if not flashscore_match:
        return None, None, metadata

    return (
        str(flashscore_match.get("home_team", {}).get("team_id") or "") or None,
        str(flashscore_match.get("away_team", {}).get("team_id") or "") or None,
        {
            **metadata,
            "status": "success",
            "strategy": "flashscore_match_lookup",
            "source_match_id": flashscore_match.get("match_id"),
        },
    )


# Cette fonction transforme les métriques d'une équipe en bloc de couverture public.
def build_team_metric_coverage(team_stats: dict[str, Any]) -> dict[str, Any]:
    return {
        metric_name: {
            "matches_used": metric.get("matches_used"),
            "matches_requested": metric.get("matches_requested"),
            "coverage": metric.get("coverage"),
        }
        for metric_name, metric in team_stats.get("metrics", {}).items()
    }


# Cette fonction détermine le statut public selon la couverture réelle des deux équipes.
def determine_advanced_stats_status(
    home_team_stats: dict[str, Any],
    away_team_stats: dict[str, Any],
) -> str:
    if not home_team_stats.get("metrics") and not away_team_stats.get("metrics"):
        return "unavailable"

    for team_stats in (home_team_stats, away_team_stats):
        if team_stats.get("matches_with_stats", 0) < ADVANCED_STATS_SAMPLE_SIZE:
            return "partial"

        metrics = team_stats.get("metrics", {})

        if not ADVANCED_STATS_EXPECTED_METRICS.issubset(metrics):
            return "partial"

        if any(
            metrics[name].get("matches_used", 0) < ADVANCED_STATS_SAMPLE_SIZE
            for name in ADVANCED_STATS_EXPECTED_METRICS
        ):
            return "partial"

    return "available"


# Cette fonction résume la fraîcheur des caches de statistiques individuels utilisés.
def build_advanced_stats_freshness(
    home_team_stats: dict[str, Any],
    away_team_stats: dict[str, Any],
) -> dict[str, Any]:
    metadata_items = [
        metadata
        for team_stats in (home_team_stats, away_team_stats)
        for metadata in team_stats.get("source_metadata", {}).get("match_stats", [])
        if isinstance(metadata, dict)
    ]
    freshness_items = [
        metadata.get("data_freshness")
        for metadata in metadata_items
        if isinstance(metadata.get("data_freshness"), dict)
    ]

    return {
        "source": FLASHSCORE_SOURCE,
        "generated_at": get_advanced_stats_now_utc_iso(),
        "match_stats_cache_ttl_minutes": FLASHSCORE_MATCH_STATS_CACHE_TTL_MINUTES,
        "match_stats_requests": len(metadata_items),
        "match_stats_from_cache": sum(1 for item in freshness_items if item.get("from_cache") is True),
        "updated_at_values": sorted(
            {
                str(item.get("updated_at"))
                for item in freshness_items
                if item.get("updated_at")
            }
        ),
    }


# Cette fonction retire les métadonnées internes avant exposition du contrat public.
def build_public_team_stats(team_stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_id": team_stats.get("team_id"),
        "team_name": team_stats.get("team_name"),
        "matches_requested": team_stats.get("matches_requested"),
        "matches_found": team_stats.get("matches_found"),
        "matches_with_stats": team_stats.get("matches_with_stats"),
        "metrics": team_stats.get("metrics", {}),
    }


# Cette fonction construit la réponse complète de la route advanced-stats sans bloquer sur une couverture partielle.
async def build_match_advanced_stats_response(
    match_id: int,
    sample_size: int = ADVANCED_STATS_SAMPLE_SIZE,
) -> dict[str, Any]:
    match_data, _match_lookup_metadata = await get_match_data_for_team_history(match_id)
    match = match_data.get("match", {}) or {}
    home_team = match.get("homeTeam", {}) or {}
    away_team = match.get("awayTeam", {}) or {}
    home_source_team_id, away_source_team_id, _flashscore_lookup_metadata = await resolve_target_flashscore_context(match)

    if not home_source_team_id or not away_source_team_id:
        return {
            "match_id": match_id,
            "status": "unavailable",
            "sample_size_requested": sample_size,
            "home_team": {
                "team_id": home_source_team_id,
                "team_name": home_team.get("name"),
                "matches_requested": sample_size,
                "matches_found": 0,
                "matches_with_stats": 0,
                "metrics": {},
            },
            "away_team": {
                "team_id": away_source_team_id,
                "team_name": away_team.get("name"),
                "matches_requested": sample_size,
                "matches_found": 0,
                "matches_with_stats": 0,
                "metrics": {},
            },
            "data_quality": {
                "status": "unavailable",
                "limitations": [
                    {
                        "code": "flashscore_team_ids_unavailable",
                        "message": "Les identifiants FlashScore nécessaires à l'historique avancé sont indisponibles.",
                    }
                ],
                "metric_coverage": {"home_team": {}, "away_team": {}},
            },
            "data_freshness": {
                "source": FLASHSCORE_SOURCE,
                "generated_at": get_advanced_stats_now_utc_iso(),
                "match_stats_cache_ttl_minutes": FLASHSCORE_MATCH_STATS_CACHE_TTL_MINUTES,
                "match_stats_requests": 0,
                "match_stats_from_cache": 0,
                "updated_at_values": [],
            },
        }

    semaphore = asyncio.Semaphore(ADVANCED_STATS_MAX_CONCURRENCY)
    home_team_stats, away_team_stats = await asyncio.gather(
        build_team_advanced_stats(
            team=home_team,
            source_team_id=home_source_team_id,
            target_utc_date=match.get("utcDate"),
            semaphore=semaphore,
            sample_size=sample_size,
        ),
        build_team_advanced_stats(
            team=away_team,
            source_team_id=away_source_team_id,
            target_utc_date=match.get("utcDate"),
            semaphore=semaphore,
            sample_size=sample_size,
        ),
    )
    status = determine_advanced_stats_status(home_team_stats, away_team_stats)
    limitations = [
        {**limitation, "team": "home"}
        for limitation in home_team_stats.get("limitations", [])
    ] + [
        {**limitation, "team": "away"}
        for limitation in away_team_stats.get("limitations", [])
    ]

    return {
        "match_id": match_id,
        "status": status,
        "sample_size_requested": sample_size,
        "home_team": build_public_team_stats(home_team_stats),
        "away_team": build_public_team_stats(away_team_stats),
        "data_quality": {
            "status": status,
            "limitations": limitations,
            "metric_coverage": {
                "home_team": build_team_metric_coverage(home_team_stats),
                "away_team": build_team_metric_coverage(away_team_stats),
            },
        },
        "data_freshness": build_advanced_stats_freshness(home_team_stats, away_team_stats),
    }


# Flux :
# matches.py
#   └── match_advanced_stats_service.py
#         ├── team_history_service.py pour retrouver le match cible sans modifier son contrat public
#         ├── rapidapi_flashscore_client.py pour /teams/results et /matches/match/stats
#         └── cache_service.py indirectement pour le cache individuel 30 jours
