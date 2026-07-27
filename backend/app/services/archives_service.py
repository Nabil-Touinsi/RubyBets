# Rôle du fichier :
# Ce service lit et enregistre les archives de prédictions RubyBets depuis PostgreSQL.
# Il prépare les données utilisées par l'API Archives et calcule le verdict des prédictions terminées.

from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from starlette.concurrency import run_in_threadpool

from app.services.database_service import get_database_connection
from app.services.football_data_client import get_football_data
from app.services.rapidapi_flashscore_client import (
    decode_flashscore_match_id,
    get_flashscore_match_details,
    get_normalized_flashscore_match_details,
    normalize_flashscore_match_for_rubybets,
)
from app.v19.domain.decision_contracts import DecisionResultV1
from app.v19.domain.decision_enums import DecisionStatus
from app.v19.explainability.explanation_builder import build_public_explanation


# Cette fonction produit une justification publique sans métrique ou détail interne.
def sanitize_public_archive_justification(
    justification: Any,
    market_type: Any,
) -> str:
    public_market = str(market_type or "archive").replace("_", " ")
    value = str(justification or "").strip()
    lowered_value = value.lower()

    forbidden_fragments = (
        "probabilité",
        "probability",
        "max_probability",
        "score brut",
        "raw_score",
        "cote",
        "odds",
        "bookmaker",
    )

    if value and not any(fragment in lowered_value for fragment in forbidden_fragments):
        return value

    return (
        f"Prédiction {public_market} archivée par RubyBets à partir des données "
        "disponibles au moment de l’analyse."
    )


# Cette fonction transforme une ligne SQL en dictionnaire Python lisible.
def map_archive_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "rubybets_match_id": row[1],
        "source_match_id": row[2],
        "competition_name": row[3],
        "home_team_name": row[4],
        "away_team_name": row[5],
        "home_team_logo_url": row[6],
        "away_team_logo_url": row[7],
        "home_team_country_code": row[8],
        "away_team_country_code": row[9],
        "match_date": row[10].isoformat() if row[10] else None,
        "prediction_date": row[11].isoformat() if row[11] else None,
        "market_type": row[12],
        "predicted_value": row[13],
        "confidence_level": row[14],
        "risk_level": row[15],
        "justification": sanitize_public_archive_justification(row[16], row[12]),
        "final_home_score": row[18],
        "final_away_score": row[19],
        "match_status": row[20],
        "verdict": row[21],
        "checked_at": row[22].isoformat() if row[22] else None,
    }


# Cette fonction construit les filtres SQL autorisés pour la lecture des archives.
def build_archive_filters(
    market_type: str | None = None,
    verdict: str | None = None,
    match_status: str | None = None,
    competition_name: str | None = None,
    search: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    filters = []
    params: dict[str, Any] = {}

    if market_type:
        filters.append("market_type = %(market_type)s")
        params["market_type"] = market_type

    if verdict:
        filters.append("verdict = %(verdict)s")
        params["verdict"] = verdict

    if match_status:
        filters.append("match_status = %(match_status)s")
        params["match_status"] = match_status

    if competition_name:
        filters.append("competition_name = %(competition_name)s")
        params["competition_name"] = competition_name

    if search:
        filters.append(
            """
            (
                home_team_name ILIKE %(search)s
                OR away_team_name ILIKE %(search)s
                OR competition_name ILIKE %(search)s
            )
            """
        )
        params["search"] = f"%{search}%"

    return filters, params


# Cette fonction transforme une liste de filtres en clause WHERE SQL.
def build_where_clause(filters: list[str]) -> str:
    if not filters:
        return ""

    return "WHERE " + " AND ".join(filters)


# Cette fonction compte le nombre total d'archives correspondant aux filtres.
def count_archived_predictions(
    where_clause: str,
    params: dict[str, Any],
) -> int:
    query = f"""
        SELECT COUNT(*)
        FROM archived_predictions
        {where_clause};
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()

    return int(result[0]) if result else 0


# Cette fonction transforme la ligne agrégée SQL en résumé global lisible.
def normalize_archive_summary_row(
    row: tuple[Any, ...] | None,
) -> dict[str, int | float | None]:
    values = row or (0, 0, 0, 0, 0, 0)
    total = int(values[0] or 0)
    evaluated = int(values[1] or 0)
    successful = int(values[2] or 0)
    unsuccessful = int(values[3] or 0)
    pending = int(values[4] or 0)
    not_verifiable = int(values[5] or 0)
    success_rate = (
        round((successful / evaluated) * 100, 1)
        if evaluated > 0
        else None
    )

    return {
        "total": total,
        "evaluated": evaluated,
        "successful": successful,
        "unsuccessful": unsuccessful,
        "pending": pending,
        "not_verifiable": not_verifiable,
        "success_rate": success_rate,
    }


# Cette fonction calcule les indicateurs globaux sur toutes les archives filtrées.
def fetch_archive_summary(
    where_clause: str,
    params: dict[str, Any],
) -> dict[str, int | float | None]:
    query = f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE verdict IN ('correct', 'incorrect')) AS evaluated,
            COUNT(*) FILTER (WHERE verdict = 'correct') AS successful,
            COUNT(*) FILTER (WHERE verdict = 'incorrect') AS unsuccessful,
            COUNT(*) FILTER (WHERE verdict = 'pending') AS pending,
            COUNT(*) FILTER (WHERE verdict = 'not_verifiable') AS not_verifiable
        FROM archived_predictions
        {where_clause};
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()

    return normalize_archive_summary_row(row)


# Cette fonction récupère la liste des compétitions disponibles dans les archives.
def fetch_archive_competitions() -> list[str]:
    query = """
        SELECT DISTINCT competition_name
        FROM archived_predictions
        WHERE competition_name IS NOT NULL
        ORDER BY competition_name ASC;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [str(row[0]) for row in rows if row and row[0]]


# Cette fonction récupère les archives depuis PostgreSQL avec pagination.
def fetch_archived_predictions(
    where_clause: str,
    params: dict[str, Any],
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    query = f"""
        SELECT
            id,
            rubybets_match_id,
            source_match_id,
            competition_name,
            home_team_name,
            away_team_name,
            home_team_logo_url,
            away_team_logo_url,
            home_team_country_code,
            away_team_country_code,
            match_date,
            prediction_date,
            market_type,
            predicted_value,
            confidence_level,
            risk_level,
            justification,
            engine_version,
            final_home_score,
            final_away_score,
            match_status,
            verdict,
            checked_at
        FROM archived_predictions
        {where_clause}
        ORDER BY prediction_date DESC, id DESC
        LIMIT %(limit)s
        OFFSET %(offset)s;
    """

    query_params = {
        **params,
        "limit": limit,
        "offset": offset,
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, query_params)
            rows = cursor.fetchall()

    return [map_archive_row(row) for row in rows]


# Cette fonction prépare la réponse complète utilisée par la route API Archives.
def get_archived_predictions(
    market_type: str | None = None,
    verdict: str | None = None,
    match_status: str | None = None,
    competition_name: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)

    try:
        filters, params = build_archive_filters(
            market_type=market_type,
            verdict=verdict,
            match_status=match_status,
            competition_name=competition_name,
            search=search,
        )
        where_clause = build_where_clause(filters)

        total_count = count_archived_predictions(
            where_clause=where_clause,
            params=params,
        )

        items = fetch_archived_predictions(
            where_clause=where_clause,
            params=params,
            limit=safe_limit,
            offset=safe_offset,
        )
        summary = fetch_archive_summary(
            where_clause=where_clause,
            params=params,
        )
        available_competitions = fetch_archive_competitions()

        return {
            "status": "available",
            "count": total_count,
            "limit": safe_limit,
            "offset": safe_offset,
            "items": items,
            "summary": summary,
            "available_competitions": available_competitions,
        }

    except Exception:
        return {
            "status": "unavailable",
            "count": 0,
            "limit": safe_limit,
            "offset": safe_offset,
            "items": [],
            "summary": normalize_archive_summary_row(None),
            "available_competitions": [],
            "message": "Les archives sont temporairement indisponibles.",
        }


# Cette fonction convertit une valeur de date en datetime compatible PostgreSQL.
def normalize_archive_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None)

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


# Cette fonction transforme une valeur de score en entier exploitable.
def normalize_archive_score(value: Any) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Cette fonction indique si un statut correspond à un match terminé.
def is_archive_match_finished(match_status: str | None) -> bool:
    if not match_status:
        return False

    normalized_status = str(match_status).strip().upper()

    return normalized_status in {
        "FINISHED",
        "FINISH",
        "FINISHED_AET",
        "FINISHED_AP",
        "COMPLETE",
        "COMPLETED",
        "FT",
        "AET",
        "PEN",
    }


# Cette fonction récupère le score final depuis les formats normalisés FlashScore ou Football-Data.
def extract_archive_final_score(
    source_match: dict[str, Any] | None,
) -> tuple[int | None, int | None]:
    if not source_match:
        return None, None

    score = source_match.get("score")

    if isinstance(score, dict):
        full_time = score.get("fullTime") or score.get("full_time")

        if isinstance(full_time, dict):
            home_score = normalize_archive_score(full_time.get("home"))
            away_score = normalize_archive_score(full_time.get("away"))

            if home_score is not None and away_score is not None:
                return home_score, away_score

    scores = source_match.get("scores")

    if isinstance(scores, dict):
        home_score = normalize_archive_score(
            scores.get("home")
            or scores.get("home_score")
            or scores.get("homeScore")
        )
        away_score = normalize_archive_score(
            scores.get("away")
            or scores.get("away_score")
            or scores.get("awayScore")
        )

        if home_score is not None and away_score is not None:
            return home_score, away_score

    home_score = normalize_archive_score(
        source_match.get("home_score")
        or source_match.get("homeScore")
        or source_match.get("final_home_score")
    )
    away_score = normalize_archive_score(
        source_match.get("away_score")
        or source_match.get("awayScore")
        or source_match.get("final_away_score")
    )

    return home_score, away_score


# Cette fonction vérifie une prédiction 1X2 avec le score final.
def compute_1x2_verdict(
    predicted_value: str,
    final_home_score: int,
    final_away_score: int,
) -> str:
    prediction = predicted_value.strip().upper()

    if final_home_score > final_away_score:
        real_result = "TEAM_A_WIN"
    elif final_home_score < final_away_score:
        real_result = "TEAM_B_WIN"
    else:
        real_result = "DRAW"

    home_predictions = {"1", "HOME", "HOME_WIN", "TEAM_A_WIN"}
    away_predictions = {"2", "AWAY", "AWAY_WIN", "TEAM_B_WIN"}
    draw_predictions = {"X", "DRAW"}

    if prediction in home_predictions:
        return "correct" if real_result == "TEAM_A_WIN" else "incorrect"

    if prediction in away_predictions:
        return "correct" if real_result == "TEAM_B_WIN" else "incorrect"

    if prediction in draw_predictions:
        return "correct" if real_result == "DRAW" else "incorrect"

    return "not_verifiable"


# Cette fonction vérifie une prédiction double chance avec le score final.
def compute_double_chance_verdict(
    predicted_value: str,
    final_home_score: int,
    final_away_score: int,
) -> str:
    prediction = predicted_value.strip().upper()

    home_or_draw = {"1X", "HOME_OR_DRAW", "TEAM_A_OR_DRAW"}
    away_or_draw = {"X2", "AWAY_OR_DRAW", "TEAM_B_OR_DRAW"}
    home_or_away = {"12", "HOME_OR_AWAY", "NO_DRAW"}

    home_win = final_home_score > final_away_score
    away_win = final_home_score < final_away_score
    draw = final_home_score == final_away_score

    if prediction in home_or_draw:
        return "correct" if home_win or draw else "incorrect"

    if prediction in away_or_draw:
        return "correct" if away_win or draw else "incorrect"

    if prediction in home_or_away:
        return "correct" if home_win or away_win else "incorrect"

    return "not_verifiable"


# Cette fonction vérifie une prédiction over/under avec le score final.
def compute_over_under_verdict(
    market_type: str,
    predicted_value: str,
    final_home_score: int,
    final_away_score: int,
) -> str:
    market = market_type.strip().upper()
    prediction = predicted_value.strip().upper()
    total_goals = final_home_score + final_away_score

    threshold = None

    if "1_5" in market or "1.5" in market or "15" in market:
        threshold = 1.5

    if "2_5" in market or "2.5" in market or "25" in market:
        threshold = 2.5

    if threshold is None:
        if "1_5" in prediction or "1.5" in prediction:
            threshold = 1.5
        elif "2_5" in prediction or "2.5" in prediction:
            threshold = 2.5

    if threshold is None:
        return "not_verifiable"

    real_is_over = total_goals > threshold

    yes_predictions = {"YES", "TRUE", "OVER", f"OVER_{str(threshold).replace('.', '_')}"}
    no_predictions = {"NO", "FALSE", "UNDER", f"UNDER_{str(threshold).replace('.', '_')}"}

    if prediction in yes_predictions or prediction.startswith("OVER"):
        return "correct" if real_is_over else "incorrect"

    if prediction in no_predictions or prediction.startswith("UNDER"):
        return "correct" if not real_is_over else "incorrect"

    return "not_verifiable"


# Cette fonction vérifie une prédiction BTTS avec le score final.
def compute_btts_verdict(
    predicted_value: str,
    final_home_score: int,
    final_away_score: int,
) -> str:
    prediction = predicted_value.strip().upper()
    real_btts = final_home_score > 0 and final_away_score > 0

    yes_predictions = {"YES", "TRUE", "BTTS_YES"}
    no_predictions = {"NO", "FALSE", "BTTS_NO"}

    if prediction in yes_predictions:
        return "correct" if real_btts else "incorrect"

    if prediction in no_predictions:
        return "correct" if not real_btts else "incorrect"

    return "not_verifiable"


# Cette fonction calcule le verdict final d'une prédiction archivée.
def compute_archive_verdict(
    market_type: str,
    predicted_value: str,
    final_home_score: int | None,
    final_away_score: int | None,
    match_status: str | None = None,
) -> str:
    if final_home_score is None or final_away_score is None:
        terminal_statuses = {
            "CANCELLED",
            "CANCELED",
            "ABANDONED",
            "VOID",
        }
        normalized_status = str(match_status or "").strip().upper()

        if is_archive_match_finished(match_status) or normalized_status in terminal_statuses:
            return "not_verifiable"

        return "pending"

    market = market_type.strip().upper()

    if market == "1X2":
        return compute_1x2_verdict(
            predicted_value=predicted_value,
            final_home_score=final_home_score,
            final_away_score=final_away_score,
        )

    if market in {"DOUBLE_CHANCE", "DC"}:
        return compute_double_chance_verdict(
            predicted_value=predicted_value,
            final_home_score=final_home_score,
            final_away_score=final_away_score,
        )

    if market.startswith("OVER") or market.startswith("UNDER") or market == "GOALS":
        return compute_over_under_verdict(
            market_type=market,
            predicted_value=predicted_value,
            final_home_score=final_home_score,
            final_away_score=final_away_score,
        )

    if market == "BTTS":
        return compute_btts_verdict(
            predicted_value=predicted_value,
            final_home_score=final_home_score,
            final_away_score=final_away_score,
        )

    return "not_verifiable"


# Cette fonction récupère un petit lot d'archives passées encore en attente.
def fetch_pending_archives_for_reconciliation(limit: int) -> list[dict[str, Any]]:
    query = """
        SELECT
            id,
            rubybets_match_id,
            source_match_id,
            market_type,
            predicted_value,
            match_date
        FROM archived_predictions
        WHERE verdict = 'pending'
          AND match_date IS NOT NULL
          AND match_date <= CURRENT_TIMESTAMP
        ORDER BY match_date ASC, id ASC
        LIMIT %(limit)s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, {"limit": limit})
            rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "rubybets_match_id": row[1],
            "source_match_id": row[2],
            "market_type": row[3],
            "predicted_value": row[4],
            "match_date": row[5],
        }
        for row in rows
    ]


# Cette fonction charge le résultat réel depuis la source adaptée à l'identifiant archivé.
async def load_archive_source_match(
    archive: dict[str, Any],
    *,
    flashscore_details_loader: Callable[[str], tuple[dict[str, Any] | None, dict[str, Any]]] | None = None,
    normalized_flashscore_loader: Callable[[int | str | None], tuple[dict[str, Any] | None, dict[str, Any]]] | None = None,
    football_data_loader: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    source_match_id = str(archive.get("source_match_id") or "").strip()
    rubybets_match_id = archive.get("rubybets_match_id")
    details_loader = flashscore_details_loader or get_flashscore_match_details
    normalized_loader = normalized_flashscore_loader or get_normalized_flashscore_match_details
    football_loader = football_data_loader or get_football_data

    if source_match_id and not source_match_id.isdigit():
        raw_match, metadata = await run_in_threadpool(
            details_loader,
            source_match_id,
        )
        normalized_match = (
            normalize_flashscore_match_for_rubybets(raw_match)
            if raw_match
            else None
        )
        return normalized_match, metadata

    decoded_flashscore_id = decode_flashscore_match_id(rubybets_match_id)
    if decoded_flashscore_id:
        return await run_in_threadpool(
            normalized_loader,
            rubybets_match_id,
        )

    football_match_id = source_match_id or str(rubybets_match_id or "").strip()
    if football_match_id.isdigit():
        response = await football_loader(f"/matches/{football_match_id}")
        if isinstance(response, dict) and response.get("status") != "error":
            match = response.get("match", response)
            if isinstance(match, dict) and match:
                return match, {
                    "provider": "football_data",
                    "status": "success",
                    "match_id": football_match_id,
                }

        return None, {
            "provider": "football_data",
            "status": "unavailable",
            "match_id": football_match_id,
        }

    return None, {
        "provider": "unknown",
        "status": "missing_source_match_id",
    }


# Cette fonction prépare les valeurs à enregistrer après vérification du résultat réel.
def build_archive_reconciliation_update(
    archive: dict[str, Any],
    source_match: dict[str, Any],
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    match_status = str(source_match.get("status") or "UNKNOWN").strip().upper()
    final_home_score, final_away_score = extract_archive_final_score(source_match)
    verdict = compute_archive_verdict(
        market_type=str(archive.get("market_type") or ""),
        predicted_value=str(archive.get("predicted_value") or ""),
        final_home_score=final_home_score,
        final_away_score=final_away_score,
        match_status=match_status,
    )

    return {
        "id": archive.get("id"),
        "final_home_score": final_home_score,
        "final_away_score": final_away_score,
        "match_status": match_status,
        "verdict": verdict,
        "checked_at": checked_at or datetime.now(UTC).replace(tzinfo=None),
    }


# Cette fonction enregistre le statut et le verdict actualisés d'une archive.
def update_reconciled_archive(payload: dict[str, Any]) -> int:
    query = """
        UPDATE archived_predictions
        SET
            final_home_score = %(final_home_score)s,
            final_away_score = %(final_away_score)s,
            match_status = %(match_status)s,
            verdict = %(verdict)s,
            checked_at = %(checked_at)s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %(id)s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, payload)
            updated_count = max(0, int(cursor.rowcount or 0))

        connection.commit()

    return updated_count


# Cette fonction actualise un lot limité d'archives sans bloquer les autres éléments.
async def reconcile_pending_archives(limit: int = 25) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 100))

    try:
        archives = fetch_pending_archives_for_reconciliation(safe_limit)
    except Exception:
        return {
            "status": "unavailable",
            "checked_count": 0,
            "updated_count": 0,
            "resolved_count": 0,
            "pending_count": 0,
            "error_count": 0,
            "message": "L'actualisation des archives est temporairement indisponible.",
        }

    updated_count = 0
    resolved_count = 0
    pending_count = 0
    error_count = 0

    for archive in archives:
        try:
            source_match, _metadata = await load_archive_source_match(archive)
            if not source_match:
                error_count += 1
                continue

            payload = build_archive_reconciliation_update(
                archive=archive,
                source_match=source_match,
            )
            updated_count += update_reconciled_archive(payload)

            if payload["verdict"] == "pending":
                pending_count += 1
            else:
                resolved_count += 1

        except Exception:
            error_count += 1

    return {
        "status": "updated",
        "checked_count": len(archives),
        "updated_count": updated_count,
        "resolved_count": resolved_count,
        "pending_count": pending_count,
        "error_count": error_count,
        "message": (
            "Les archives ont été actualisées."
            if archives
            else "Aucune archive à actualiser pour le moment."
        ),
    }


# Cette fonction construit une justification publique sans probabilité interne.
def build_archive_justification(
    market_type: str,
    prediction: dict[str, Any],
) -> str:
    _ = prediction

    return (
        f"Prédiction {market_type} générée par RubyBets à partir des données "
        "disponibles au moment de l’analyse."
    )


V19_ARCHIVE_RESPONSIBLE_NOTE = (
    "Décision analytique expérimentale avant-match. "
    "RubyBets ne garantit aucun résultat sportif et ne permet aucune prise de pari."
)


# Cette fonction normalise un niveau V19 pour respecter les contraintes PostgreSQL des archives.
def normalize_v19_archive_level(value: Any) -> str | None:
    normalized_value = str(value or "").strip().lower()

    if normalized_value in {"low", "medium", "high"}:
        return normalized_value

    return None


# Cette fonction traduit les marchés V19 vers les libellés déjà utilisés par l'écran Archives.
def normalize_v19_archive_market_type(value: Any) -> str:
    market_map = {
        "STRICT_1X2": "1X2",
        "DOUBLE_CHANCE": "DOUBLE_CHANCE",
        "OVER_1_5": "OVER_1_5",
        "BTTS": "BTTS",
    }
    normalized_value = str(getattr(value, "value", value) or "").strip().upper()
    return market_map.get(normalized_value, normalized_value)


# Cette fonction construit une justification V19 publique à partir de l'explication déjà validée.
def build_v19_archive_justification(result: DecisionResultV1) -> str:
    explanation = build_public_explanation(
        result=result,
        responsible_note=V19_ARCHIVE_RESPONSIBLE_NOTE,
    )
    summary = str(explanation.get("summary") or "").strip()
    supporting_factors = explanation.get("supporting_factors") or []

    first_factor = ""
    if isinstance(supporting_factors, list) and supporting_factors:
        first_factor = str(supporting_factors[0] or "").strip()

    if summary and first_factor:
        return f"{summary} {first_factor}"

    if summary:
        return summary

    return (
        "Décision V19 archivée à partir des données disponibles "
        "au moment de l’analyse."
    )


# Cette fonction transforme une décision V19 RECOMMEND en une ligne d'archive unique.
def build_v19_archived_prediction_payload(
    result: DecisionResultV1,
) -> dict[str, Any] | None:
    candidate = result.selected_candidate

    if result.status is not DecisionStatus.RECOMMEND or candidate is None:
        return None

    metadata = dict(result.metadata)
    home_team_name = str(
        metadata.get("archive_home_team_name") or "Équipe domicile"
    )
    away_team_name = str(
        metadata.get("archive_away_team_name") or "Équipe extérieure"
    )

    return {
        "rubybets_match_id": str(result.match_id),
        "source_match_id": metadata.get("archive_source_match_id"),
        "competition_name": metadata.get("archive_competition_name"),
        "home_team_name": home_team_name,
        "away_team_name": away_team_name,
        "home_team_logo_url": metadata.get("archive_home_team_logo_url"),
        "away_team_logo_url": metadata.get("archive_away_team_logo_url"),
        "home_team_country_code": metadata.get(
            "archive_home_team_country_code"
        ),
        "away_team_country_code": metadata.get(
            "archive_away_team_country_code"
        ),
        "match_date": normalize_archive_datetime(
            metadata.get("archive_match_date")
        ),
        "market_type": normalize_v19_archive_market_type(
            candidate.market_type
        ),
        "predicted_value": str(
            candidate.recommendation_value or "UNKNOWN"
        ),
        "confidence_level": normalize_v19_archive_level(
            candidate.confidence_level
        ),
        "risk_level": normalize_v19_archive_level(
            candidate.local_risk_level
        ),
        "justification": build_v19_archive_justification(result),
        "engine_version": str(result.engine_version),
        "final_home_score": None,
        "final_away_score": None,
        "match_status": str(
            metadata.get("archive_match_status") or "SCHEDULED"
        ),
        "verdict": "pending",
        "checked_at": None,
    }


# Cette fonction supprime une ancienne décision V19 encore en attente lorsque le moteur s'abstient désormais.
def delete_pending_v19_archive(result: DecisionResultV1) -> int:
    query = """
        DELETE FROM archived_predictions
        WHERE rubybets_match_id = %(rubybets_match_id)s
          AND engine_version = %(engine_version)s
          AND verdict = 'pending';
    """
    params = {
        "rubybets_match_id": str(result.match_id),
        "engine_version": str(result.engine_version),
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            removed_count = max(0, int(cursor.rowcount or 0))

        connection.commit()

    return removed_count


# Cette fonction insère ou remplace l'unique décision V19 active d'un match et d'une version moteur.
def upsert_v19_archived_prediction(payload: dict[str, Any]) -> int:
    select_query = """
        SELECT id
        FROM archived_predictions
        WHERE rubybets_match_id = %(rubybets_match_id)s
          AND engine_version = %(engine_version)s
        ORDER BY id DESC
        LIMIT 1;
    """

    update_query = """
        UPDATE archived_predictions
        SET
            source_match_id = %(source_match_id)s,
            competition_name = %(competition_name)s,
            home_team_name = %(home_team_name)s,
            away_team_name = %(away_team_name)s,
            home_team_logo_url = %(home_team_logo_url)s,
            away_team_logo_url = %(away_team_logo_url)s,
            home_team_country_code = %(home_team_country_code)s,
            away_team_country_code = %(away_team_country_code)s,
            match_date = %(match_date)s,
            prediction_date = CURRENT_TIMESTAMP,
            market_type = %(market_type)s,
            predicted_value = %(predicted_value)s,
            confidence_level = %(confidence_level)s,
            risk_level = %(risk_level)s,
            justification = %(justification)s,
            final_home_score = %(final_home_score)s,
            final_away_score = %(final_away_score)s,
            match_status = %(match_status)s,
            verdict = %(verdict)s,
            checked_at = %(checked_at)s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %(id)s;
    """

    insert_query = """
        INSERT INTO archived_predictions (
            rubybets_match_id,
            source_match_id,
            competition_name,
            home_team_name,
            away_team_name,
            home_team_logo_url,
            away_team_logo_url,
            home_team_country_code,
            away_team_country_code,
            match_date,
            market_type,
            predicted_value,
            confidence_level,
            risk_level,
            justification,
            engine_version,
            final_home_score,
            final_away_score,
            match_status,
            verdict,
            checked_at
        )
        VALUES (
            %(rubybets_match_id)s,
            %(source_match_id)s,
            %(competition_name)s,
            %(home_team_name)s,
            %(away_team_name)s,
            %(home_team_logo_url)s,
            %(away_team_logo_url)s,
            %(home_team_country_code)s,
            %(away_team_country_code)s,
            %(match_date)s,
            %(market_type)s,
            %(predicted_value)s,
            %(confidence_level)s,
            %(risk_level)s,
            %(justification)s,
            %(engine_version)s,
            %(final_home_score)s,
            %(final_away_score)s,
            %(match_status)s,
            %(verdict)s,
            %(checked_at)s
        );
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(select_query, payload)
            existing_archive = cursor.fetchone()

            if existing_archive:
                cursor.execute(
                    update_query,
                    {
                        **payload,
                        "id": existing_archive[0],
                    },
                )
            else:
                cursor.execute(insert_query, payload)

        connection.commit()

    return 1


# Cette fonction archive la décision officielle V19 sans bloquer la réponse produit en cas d'indisponibilité PostgreSQL.
def archive_v19_decision(
    result: DecisionResultV1,
) -> dict[str, Any]:
    try:
        if result.status is not DecisionStatus.RECOMMEND:
            removed_count = delete_pending_v19_archive(result)
            return {
                "status": "removed" if removed_count else "skipped",
                "archived_count": 0,
                "removed_count": removed_count,
            }

        payload = build_v19_archived_prediction_payload(result)
        if payload is None:
            return {
                "status": "skipped",
                "archived_count": 0,
                "removed_count": 0,
            }

        archived_count = upsert_v19_archived_prediction(payload)
        return {
            "status": "archived",
            "archived_count": archived_count,
            "removed_count": 0,
        }

    except Exception:
        return {
            "status": "unavailable",
            "archived_count": 0,
            "removed_count": 0,
            "message": (
                "Archive V19 persistence failed without blocking "
                "the prediction response."
            ),
        }


# Schéma de communication :
# backend/app/api/experimental_ml_v19.py / backend/app/api/archives.py
#     ↓
# archives_service.py
#     ↓
# database_service.py
#     ↓
# PostgreSQL archived_predictions
#     ↓
# api/archives.py (lecture + actualisation)
#     ↓
# frontend ArchivesScreen.tsx