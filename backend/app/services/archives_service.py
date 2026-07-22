# Rôle du fichier :
# Ce service lit et enregistre les archives de prédictions RubyBets depuis PostgreSQL.
# Il prépare les données utilisées par l'API Archives et calcule le verdict des prédictions terminées.

from datetime import datetime
from typing import Any

from app.services.database_service import get_database_connection
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
        available_competitions = fetch_archive_competitions()

        return {
            "status": "available",
            "count": total_count,
            "limit": safe_limit,
            "offset": safe_offset,
            "items": items,
            "available_competitions": available_competitions,
        }

    except Exception:
        return {
            "status": "unavailable",
            "count": 0,
            "limit": safe_limit,
            "offset": safe_offset,
            "items": [],
            "available_competitions": [],
            "message": "Archives database is unavailable or not initialized yet.",
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
        return "not_verifiable" if is_archive_match_finished(match_status) else "pending"

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


# Cette fonction transforme une probabilité modèle en niveau de confiance lisible.
def compute_confidence_level(probability: Any) -> str:
    try:
        score = float(probability)
    except (TypeError, ValueError):
        return "low"

    if score >= 0.85:
        return "high"

    if score >= 0.75:
        return "medium"

    return "low"


# Cette fonction déduit un niveau de risque simple à partir du niveau de confiance.
def compute_risk_level_from_confidence(confidence_level: str) -> str:
    if confidence_level == "high":
        return "low"

    if confidence_level == "medium":
        return "medium"

    return "high"


# Cette fonction récupère une équipe dans les formats Football-Data ou FlashScore normalisés.
def extract_archive_team(
    source_match: dict[str, Any] | None,
    raw_key: str,
    formatted_key: str,
) -> dict[str, Any]:
    if not source_match:
        return {}

    raw_team = source_match.get(raw_key)
    if isinstance(raw_team, dict):
        return raw_team

    formatted_team = source_match.get(formatted_key)
    if isinstance(formatted_team, dict):
        return formatted_team

    return {}


# Cette fonction récupère le logo disponible pour une équipe.
def extract_archive_team_logo(team: dict[str, Any]) -> str | None:
    return (
        team.get("crest")
        or team.get("crest_url")
        or team.get("logo")
        or team.get("flag")
    )


# Cette fonction récupère un code court exploitable pour un futur affichage de drapeau.
def extract_archive_team_country_code(team: dict[str, Any]) -> str | None:
    return (
        team.get("country_code")
        or team.get("countryCode")
        or team.get("tla")
    )


# Cette fonction normalise les clés internes du modèle en marchés lisibles.
def normalize_archive_market_type(market_key: str) -> str:
    market_map = {
        "1x2": "1X2",
        "over_1_5": "OVER_1_5",
        "over_2_5": "OVER_2_5",
        "btts": "BTTS",
    }

    return market_map.get(market_key, market_key.upper())


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


# Cette fonction transforme une réponse ML nationale en lignes prêtes à archiver.
def build_archived_prediction_payloads(
    inference_response: dict[str, Any],
    rubybets_match_id: int,
    source_match: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if inference_response.get("status") != "computed":
        return []

    match_metadata = inference_response.get("match") or {}
    market_predictions = inference_response.get("market_predictions") or {}

    home_team = extract_archive_team(source_match, "homeTeam", "home_team")
    away_team = extract_archive_team(source_match, "awayTeam", "away_team")

    home_team_name = (
        home_team.get("name")
        or match_metadata.get("team_a_name")
        or "Équipe domicile"
    )
    away_team_name = (
        away_team.get("name")
        or match_metadata.get("team_b_name")
        or "Équipe extérieure"
    )

    competition = source_match.get("competition", {}) if source_match else {}
    match_status = str(source_match.get("status") or "scheduled") if source_match else "scheduled"
    final_home_score, final_away_score = extract_archive_final_score(source_match)

    payloads = []

    for market_key, prediction in market_predictions.items():
        if not isinstance(prediction, dict):
            continue

        market_type = normalize_archive_market_type(market_key)
        predicted_value = str(prediction.get("prediction") or "UNKNOWN")
        confidence_level = compute_confidence_level(prediction.get("max_probability"))
        risk_level = compute_risk_level_from_confidence(confidence_level)

        verdict = compute_archive_verdict(
            market_type=market_type,
            predicted_value=predicted_value,
            final_home_score=final_home_score,
            final_away_score=final_away_score,
            match_status=match_status,
        )

        payloads.append(
            {
                "rubybets_match_id": str(rubybets_match_id),
                "source_match_id": str(source_match.get("id")) if source_match and source_match.get("id") else None,
                "competition_name": (
                    competition.get("name")
                    or match_metadata.get("competition_name")
                ),
                "home_team_name": home_team_name,
                "away_team_name": away_team_name,
                "home_team_logo_url": extract_archive_team_logo(home_team),
                "away_team_logo_url": extract_archive_team_logo(away_team),
                "home_team_country_code": extract_archive_team_country_code(home_team),
                "away_team_country_code": extract_archive_team_country_code(away_team),
                "match_date": normalize_archive_datetime(
                    source_match.get("utcDate") if source_match else match_metadata.get("match_date_utc")
                ),
                "market_type": market_type,
                "predicted_value": predicted_value,
                "confidence_level": confidence_level,
                "risk_level": risk_level,
                "justification": build_archive_justification(market_type, prediction),
                "engine_version": str(
                    inference_response.get("source")
                    or "rubybets_ml_national_v18_3_4_dynamic_inference"
                ),
                "final_home_score": final_home_score,
                "final_away_score": final_away_score,
                "match_status": match_status,
                "verdict": verdict,
                "checked_at": datetime.utcnow() if verdict != "pending" else None,
            }
        )

    return payloads


# Cette fonction insère ou met à jour une archive sans créer de doublon inutile.
def upsert_archived_prediction(payload: dict[str, Any]) -> int:
    select_query = """
        SELECT id
        FROM archived_predictions
        WHERE rubybets_match_id = %(rubybets_match_id)s
          AND market_type = %(market_type)s
          AND engine_version = %(engine_version)s
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


# Cette fonction archive toutes les prédictions calculées pour un match RubyBets.
def archive_national_dynamic_predictions(
    inference_response: dict[str, Any],
    rubybets_match_id: int,
    source_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        payloads = build_archived_prediction_payloads(
            inference_response=inference_response,
            rubybets_match_id=rubybets_match_id,
            source_match=source_match,
        )

        archived_count = 0

        for payload in payloads:
            archived_count += upsert_archived_prediction(payload)

        return {
            "status": "archived" if archived_count else "skipped",
            "archived_count": archived_count,
        }

    except Exception:
        return {
            "status": "unavailable",
            "archived_count": 0,
            "message": "Archive persistence failed without blocking prediction response.",
        }


# Schéma de communication :
# backend/app/api/experimental_ml_v19.py / experimental_ml_national_v18_3_3.py
#     ↓
# archives_service.py
#     ↓
# database_service.py
#     ↓
# PostgreSQL archived_predictions
#     ↓
# api/archives.py
#     ↓
# frontend ArchivesScreen.tsx