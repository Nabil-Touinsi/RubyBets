# Ce fichier centralise les appels RapidAPI / FlashScore utilisés par RubyBets.
# Il récupère les matchs, les historiques d'équipes et les confrontations directes sans utiliser les cotes.

from datetime import UTC, datetime
from typing import Any
import hashlib
import unicodedata

import httpx

from app.core.config import settings


FLASHSCORE_FOOTBALL_SPORT_ID = 1
FLASHSCORE_DEFAULT_TIMEZONE = "Europe/Berlin"
FLASHSCORE_RESULTS_PAGE_SIZE_LIMIT = 20
FLASHSCORE_MAX_RESULTS_PAGES = 3
FLASHSCORE_H2H_LIMIT = 5
FLASHSCORE_SOURCE = "flashscore_rapidapi"
FLASHSCORE_ID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
FLASHSCORE_ID_MAX_LENGTH = 8
FLASHSCORE_ID_OFFSET_BASE = len(FLASHSCORE_ID_ALPHABET) ** FLASHSCORE_ID_MAX_LENGTH
FLASHSCORE_MVP_COMPETITION_FILTERS = {
    "PL": {
        "required": ["england", "premier league"],
        "excluded": ["women", "u18", "u19", "u21", "premier league 2"],
    },
    "FL1": {
        "required": ["france", "ligue 1"],
        "excluded": ["women", "u19", "u21", "ligue 2"],
    },
    "BL1": {
        "required": ["germany", "bundesliga"],
        "excluded": ["women", "u19", "u21", "2 bundesliga", "3 liga"],
    },
    "SA": {
        "required": ["italy", "serie a"],
        "excluded": ["women", "primavera", "serie a2"],
    },
    "PD": {
        "required": ["spain"],
        "any": ["laliga", "la liga", "primera division"],
        "excluded": ["women", "laliga2", "la liga 2", "segunda"],
    },
    "CL": {
        "required": ["europe", "champions league"],
        "excluded": ["women", "youth", "u19"],
    },
    "WC": {
        "required": ["world"],
        "any": ["world cup", "world championship"],
        "excluded": ["women", "u17", "u20", "u21"],
    },
}


# Cette fonction appelle RapidAPI / FlashScore et retourne la réponse JSON brute.
def get_rapidapi_flashscore_data(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    base_url = settings.rapidapi_flashscore_base_url.rstrip("/")
    clean_endpoint = endpoint.lstrip("/")
    url = f"{base_url}/{clean_endpoint}"

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                url,
                headers=settings.get_rapidapi_headers(),
                params=params,
            )

            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as error:
        return {
            "source": "rapidapi_flashscore",
            "status": "error",
            "status_code": error.response.status_code,
            "message": error.response.text,
        }

    except httpx.RequestError as error:
        return {
            "source": "rapidapi_flashscore",
            "status": "error",
            "message": str(error),
        }


# Cette fonction indique si la réponse RapidAPI correspond à une erreur maîtrisée.
def is_flashscore_error_response(data: Any) -> bool:
    return isinstance(data, dict) and data.get("status") == "error"


# Cette fonction normalise un texte FlashScore pour comparer des noms d'équipes malgré les suffixes pays.
def normalize_flashscore_text(value: str | None) -> str:
    raw_value = str(value or "").strip().lower()

    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", raw_value)
        if not unicodedata.combining(char)
    )

    without_country_suffix = without_accents
    if without_country_suffix.endswith(")") and "(" in without_country_suffix:
        without_country_suffix = without_country_suffix.rsplit("(", 1)[0]

    normalized = (
        without_country_suffix
        .replace(".", " ")
        .replace("-", " ")
        .replace("_", " ")
    )

    return " ".join(normalized.split())


# Cette fonction transforme une date ISO RubyBets en objet datetime UTC.
def parse_rubybets_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        normalized_value = value.replace("Z", "+00:00")
        parsed_datetime = datetime.fromisoformat(normalized_value)

        if parsed_datetime.tzinfo is None:
            return parsed_datetime.replace(tzinfo=UTC)

        return parsed_datetime.astimezone(UTC)

    except ValueError:
        return None


# Cette fonction convertit un timestamp FlashScore en date ISO UTC compatible avec RubyBets.
def convert_flashscore_timestamp_to_utc_date(timestamp: int | None) -> str | None:
    if timestamp is None:
        return None

    try:
        return datetime.fromtimestamp(int(timestamp), tz=UTC).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return None


# Cette fonction convertit un score FlashScore en entier quand la valeur est exploitable.
def normalize_flashscore_score_value(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Cette fonction retourne une date ISO UTC utilisée comme horodatage technique interne.
def get_flashscore_now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# Cette fonction transforme un identifiant FlashScore court en identifiant numérique stable RubyBets.
def encode_flashscore_match_id(source_match_id: str | None) -> int | None:
    if not source_match_id:
        return None

    clean_source_match_id = str(source_match_id).strip()

    if len(clean_source_match_id) > FLASHSCORE_ID_MAX_LENGTH:
        return None

    value = 0
    base = len(FLASHSCORE_ID_ALPHABET)

    for char in clean_source_match_id:
        if char not in FLASHSCORE_ID_ALPHABET:
            return None

        value = value * base + FLASHSCORE_ID_ALPHABET.index(char)

    return len(clean_source_match_id) * FLASHSCORE_ID_OFFSET_BASE + value


# Cette fonction retrouve l'identifiant FlashScore depuis l'identifiant numérique RubyBets.
def decode_flashscore_match_id(rubybets_match_id: int | str | None) -> str | None:
    if rubybets_match_id is None:
        return None

    try:
        numeric_id = int(rubybets_match_id)
    except (TypeError, ValueError):
        return None

    source_id_length = numeric_id // FLASHSCORE_ID_OFFSET_BASE
    encoded_value = numeric_id % FLASHSCORE_ID_OFFSET_BASE

    if source_id_length <= 0 or source_id_length > FLASHSCORE_ID_MAX_LENGTH:
        return None

    base = len(FLASHSCORE_ID_ALPHABET)
    chars: list[str] = []

    for _ in range(source_id_length):
        encoded_value, remainder = divmod(encoded_value, base)
        chars.append(FLASHSCORE_ID_ALPHABET[remainder])

    if encoded_value != 0:
        return None

    return "".join(reversed(chars))


# Cette fonction crée un identifiant numérique stable non réversible pour les entités FlashScore secondaires.
def build_flashscore_stable_numeric_id(value: Any, namespace: str) -> int | None:
    if value is None or value == "":
        return None

    raw_value = f"{namespace}:{value}"
    digest = hashlib.sha1(raw_value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


# Cette fonction extrait proprement le tournoi FlashScore attaché à un match.
def extract_flashscore_tournament(match: dict[str, Any]) -> dict[str, Any]:
    tournament = match.get("_flashscore_tournament") or match.get("tournament") or {}

    if isinstance(tournament, dict):
        return tournament

    return {}


# Cette fonction normalise le statut d'un match FlashScore vers les statuts attendus par RubyBets.
def normalize_flashscore_match_status(match: dict[str, Any]) -> str:
    match_status = match.get("match_status") or {}

    if not isinstance(match_status, dict):
        match_status = {}

    if match_status.get("is_cancelled"):
        return "CANCELLED"

    if match_status.get("is_postponed"):
        return "POSTPONED"

    if match_status.get("is_finished"):
        return "FINISHED"

    if match_status.get("is_in_progress") or match_status.get("is_started"):
        return "IN_PLAY"

    return "SCHEDULED"


# Cette fonction transforme un nom de tournoi FlashScore en code court exploitable côté interface.
def build_flashscore_competition_code(tournament: dict[str, Any]) -> str | None:
    tournament_id = tournament.get("tournament_id") or tournament.get("id")

    if tournament_id:
        return f"FS_{str(tournament_id).upper()}"

    name = tournament.get("name") or tournament.get("full_name")
    normalized_name = normalize_flashscore_text(name).replace(" ", "_").upper()

    if normalized_name:
        return f"FS_{normalized_name[:16]}"

    return None


# Cette fonction normalise la zone géographique d'un match FlashScore dans un format proche de Football-Data.
def normalize_flashscore_area_for_rubybets(tournament: dict[str, Any]) -> dict[str, Any]:
    country_name = (
        tournament.get("country_name")
        or tournament.get("country")
        or tournament.get("category_name")
    )
    country_code = tournament.get("country_code") or tournament.get("category_code")

    return {
        "id": build_flashscore_stable_numeric_id(country_name or country_code, "area"),
        "name": country_name,
        "code": country_code,
        "flag": tournament.get("country_flag") or tournament.get("flag"),
    }


# Cette fonction normalise la compétition FlashScore dans un format proche de Football-Data.
def normalize_flashscore_competition_for_rubybets(
    tournament: dict[str, Any],
) -> dict[str, Any]:
    tournament_id = tournament.get("tournament_id") or tournament.get("id")
    competition_name = (
        tournament.get("full_name")
        or tournament.get("name")
        or tournament.get("tournament_name")
    )

    return {
        "id": build_flashscore_stable_numeric_id(tournament_id or competition_name, "competition"),
        "code": build_flashscore_competition_code(tournament),
        "name": competition_name,
        "type": tournament.get("type"),
        "emblem": tournament.get("image_path") or tournament.get("logo") or tournament.get("emblem"),
        "sourceCompetitionId": tournament_id,
    }


# Cette fonction normalise une équipe FlashScore pour les routes matchs RubyBets.
def normalize_flashscore_team_for_rubybets(team: dict[str, Any]) -> dict[str, Any]:
    source_team_id = team.get("team_id") or team.get("id")
    source_event_participant_id = (
        team.get("event_participant_id")
        or team.get("eventParticipantId")
    )
    team_name = team.get("name")
    short_name = team.get("short_name") or team.get("shortName") or team_name

    return {
        "id": build_flashscore_stable_numeric_id(source_team_id or team_name, "team"),
        "name": team_name,
        "shortName": short_name,
        "tla": team.get("tla") or team.get("short_name") or team.get("shortName"),
        "crest": team.get("small_image_path") or team.get("image_path") or team.get("logo"),
        "sourceTeamId": source_team_id,
        "sourceEventParticipantId": source_event_participant_id,
    }


# Cette fonction calcule le vainqueur Football-Data compatible à partir d'un score FlashScore.
def build_flashscore_winner(home_score: int | None, away_score: int | None) -> str | None:
    if home_score is None or away_score is None:
        return None

    if home_score > away_score:
        return "HOME_TEAM"

    if away_score > home_score:
        return "AWAY_TEAM"

    return "DRAW"


# Cette fonction extrait les scores principaux d'un match FlashScore.
def extract_flashscore_full_time_score(match: dict[str, Any]) -> dict[str, int | None]:
    scores = match.get("scores") or match.get("score") or {}

    if not isinstance(scores, dict):
        return {"home": None, "away": None}

    return {
        "home": normalize_flashscore_score_value(scores.get("home")),
        "away": normalize_flashscore_score_value(scores.get("away")),
    }


# Cette fonction normalise un match FlashScore dans le format brut attendu par match_service.format_match.
def normalize_flashscore_match_for_rubybets(match: dict[str, Any]) -> dict[str, Any] | None:
    source_match_id = match.get("match_id") or match.get("id")
    rubybets_match_id = encode_flashscore_match_id(source_match_id)
    utc_date = convert_flashscore_timestamp_to_utc_date(match.get("timestamp"))

    if rubybets_match_id is None or utc_date is None:
        return None

    tournament = extract_flashscore_tournament(match)
    full_time_score = extract_flashscore_full_time_score(match)
    match_status = match.get("match_status") or {}

    if not isinstance(match_status, dict):
        match_status = {}

    return {
        "id": rubybets_match_id,
        "sourceMatchId": source_match_id,
        "source": FLASHSCORE_SOURCE,
        "data_source": FLASHSCORE_SOURCE,
        "utcDate": utc_date,
        "status": normalize_flashscore_match_status(match),
        "matchday": match.get("round") or match.get("matchday"),
        "stage": match_status.get("stage") or match.get("stage"),
        "group": match.get("group"),
        "lastUpdated": get_flashscore_now_utc_iso(),
        "area": normalize_flashscore_area_for_rubybets(tournament),
        "competition": normalize_flashscore_competition_for_rubybets(tournament),
        "season": {
            "id": build_flashscore_stable_numeric_id(tournament.get("season_id"), "season"),
            "startDate": None,
            "endDate": None,
            "currentMatchday": None,
            "winner": None,
            "sourceSeasonId": tournament.get("season_id"),
        },
        "homeTeam": normalize_flashscore_team_for_rubybets(match.get("home_team", {}) or {}),
        "awayTeam": normalize_flashscore_team_for_rubybets(match.get("away_team", {}) or {}),
        "score": {
            "winner": build_flashscore_winner(
                home_score=full_time_score.get("home"),
                away_score=full_time_score.get("away"),
            ),
            "duration": "REGULAR",
            "fullTime": full_time_score,
            "halfTime": {
                "home": None,
                "away": None,
            },
        },
        "referees": [],
    }


# Cette fonction filtre des matchs FlashScore normalisés selon le statut demandé par l'API RubyBets.
def filter_flashscore_matches_by_status(
    matches: list[dict[str, Any]],
    status: str | None,
) -> list[dict[str, Any]]:
    if not status:
        return matches

    expected_status = status.upper()

    return [match for match in matches if match.get("status") == expected_status]


# Cette fonction filtre des matchs FlashScore normalisés selon un nom d'équipe recherché.
def filter_flashscore_matches_by_team(
    matches: list[dict[str, Any]],
    team: str | None,
) -> list[dict[str, Any]]:
    if not team:
        return matches

    searched_team = normalize_flashscore_text(team)

    return [
        match
        for match in matches
        if searched_team in normalize_flashscore_text(match.get("homeTeam", {}).get("name"))
        or searched_team in normalize_flashscore_text(match.get("awayTeam", {}).get("name"))
    ]


# Cette fonction construit le texte de comparaison utilisé pour filtrer une compétition FlashScore.
def build_flashscore_competition_search_text(match: dict[str, Any]) -> str:
    area = match.get("area") or {}
    competition = match.get("competition") or {}
    values = [
        area.get("name"),
        area.get("code"),
        competition.get("name"),
        competition.get("code"),
        competition.get("sourceCompetitionId"),
    ]
    return normalize_flashscore_text(" ".join(str(value) for value in values if value))


# Cette fonction vérifie si un match FlashScore appartient à la compétition MVP demandée.
def does_flashscore_match_belong_to_competition(
    match: dict[str, Any],
    competition_code: str | None,
) -> bool:
    if not competition_code:
        return True

    rule = FLASHSCORE_MVP_COMPETITION_FILTERS.get(competition_code.upper())

    if not rule:
        return True

    search_text = build_flashscore_competition_search_text(match)
    required_terms = [normalize_flashscore_text(term) for term in rule.get("required", [])]
    any_terms = [normalize_flashscore_text(term) for term in rule.get("any", [])]
    excluded_terms = [normalize_flashscore_text(term) for term in rule.get("excluded", [])]

    if any(term and term in search_text for term in excluded_terms):
        return False

    if any(term and term not in search_text for term in required_terms):
        return False

    if any_terms and not any(term and term in search_text for term in any_terms):
        return False

    return True


# Cette fonction filtre les matchs FlashScore selon le code compétition MVP demandé par le frontend.
def filter_flashscore_matches_by_competition(
    matches: list[dict[str, Any]],
    competition_code: str | None,
) -> list[dict[str, Any]]:
    if not competition_code:
        return matches

    return [
        match
        for match in matches
        if does_flashscore_match_belong_to_competition(match, competition_code)
    ]


# Cette fonction retourne une liste de matchs FlashScore déjà normalisés pour /api/matches.
def get_normalized_flashscore_matches_by_day(
    day_offset: int,
    status: str | None = "SCHEDULED",
    team: str | None = None,
    timezone: str = FLASHSCORE_DEFAULT_TIMEZONE,
    competition_code: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_matches, metadata = get_flashscore_matches_by_day(
        day_offset=day_offset,
        timezone=timezone,
    )

    if metadata.get("status") != "success":
        return [], metadata

    normalized_matches = [
        normalized_match
        for normalized_match in (
            normalize_flashscore_match_for_rubybets(match) for match in raw_matches
        )
        if normalized_match is not None
    ]

    status_filtered_matches = filter_flashscore_matches_by_status(normalized_matches, status)
    competition_filtered_matches = filter_flashscore_matches_by_competition(
        status_filtered_matches,
        competition_code,
    )
    filtered_matches = filter_flashscore_matches_by_team(competition_filtered_matches, team)

    return filtered_matches, {
        **metadata,
        "status": "success" if filtered_matches else "empty",
        "source": FLASHSCORE_SOURCE,
        "normalized_count": len(normalized_matches),
        "status_filtered_count": len(status_filtered_matches),
        "competition_filtered_count": len(competition_filtered_matches),
        "filtered_count": len(filtered_matches),
        "requested_status": status,
        "requested_competition_code": competition_code,
        "team_filter": team,
    }


# Cette fonction extrait le match depuis la réponse brute /matches/details de FlashScore.
def extract_flashscore_match_details_payload(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        if data.get("match_id") or data.get("id"):
            return data

        for key in ("match", "details", "data"):
            value = data.get(key)

            if isinstance(value, dict) and (value.get("match_id") or value.get("id")):
                return value

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and (item.get("match_id") or item.get("id")):
                return item

    return None


# Cette fonction récupère le détail brut d'un match FlashScore depuis son identifiant source.
def get_flashscore_match_details(
    flashscore_match_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not flashscore_match_id:
        return None, {
            "provider": FLASHSCORE_SOURCE,
            "status": "missing_match_id",
            "endpoint": "/matches/details",
        }

    data = get_rapidapi_flashscore_data(
        "/matches/details",
        {
            "match_id": flashscore_match_id,
        },
    )

    if is_flashscore_error_response(data):
        return None, {
            "provider": FLASHSCORE_SOURCE,
            "status": "error",
            "endpoint": "/matches/details",
            "match_id": flashscore_match_id,
            "message": data.get("message"),
            "status_code": data.get("status_code"),
        }

    match = extract_flashscore_match_details_payload(data)

    if not match:
        return None, {
            "provider": FLASHSCORE_SOURCE,
            "status": "unexpected_response",
            "endpoint": "/matches/details",
            "match_id": flashscore_match_id,
        }

    return match, {
        "provider": FLASHSCORE_SOURCE,
        "status": "success",
        "endpoint": "/matches/details",
        "match_id": flashscore_match_id,
    }


# Cette fonction récupère et normalise le détail d'un match FlashScore à partir de l'id numérique RubyBets.
def get_normalized_flashscore_match_details(
    rubybets_match_id: int | str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    flashscore_match_id = decode_flashscore_match_id(rubybets_match_id)

    if not flashscore_match_id:
        return None, {
            "provider": FLASHSCORE_SOURCE,
            "status": "not_flashscore_match_id",
            "endpoint": "/matches/details",
            "rubybets_match_id": rubybets_match_id,
        }

    raw_match, metadata = get_flashscore_match_details(flashscore_match_id)

    if not raw_match:
        return None, metadata

    normalized_match = normalize_flashscore_match_for_rubybets(raw_match)

    if not normalized_match:
        return None, {
            **metadata,
            "status": "normalization_failed",
            "rubybets_match_id": rubybets_match_id,
        }

    return normalized_match, {
        **metadata,
        "status": "success",
        "rubybets_match_id": rubybets_match_id,
    }


# Cette fonction calcule le paramètre day attendu par /matches/list à partir de la date du match RubyBets.
def build_flashscore_day_offset(target_utc_date: str | None) -> int | None:
    target_datetime = parse_rubybets_utc_datetime(target_utc_date)

    if target_datetime is None:
        return None

    today_utc = datetime.now(UTC).date()
    return (target_datetime.date() - today_utc).days


# Cette fonction récupère les matchs FlashScore d'une journée relative à la date courante.
def get_flashscore_matches_by_day(
    day_offset: int,
    timezone: str = FLASHSCORE_DEFAULT_TIMEZONE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = get_rapidapi_flashscore_data(
        "/matches/list",
        {
            "sport_id": FLASHSCORE_FOOTBALL_SPORT_ID,
            "day": day_offset,
            "timezone": timezone,
        },
    )

    if is_flashscore_error_response(data):
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "error",
            "endpoint": "/matches/list",
            "message": data.get("message"),
            "status_code": data.get("status_code"),
        }

    if not isinstance(data, list):
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "unexpected_response",
            "endpoint": "/matches/list",
        }

    matches: list[dict[str, Any]] = []

    for tournament in data:
        if not isinstance(tournament, dict):
            continue

        for match in tournament.get("matches", []) or []:
            if not isinstance(match, dict):
                continue

            match["_flashscore_tournament"] = tournament
            matches.append(match)

    return matches, {
        "provider": "flashscore_rapidapi",
        "status": "success",
        "endpoint": "/matches/list",
        "day_offset": day_offset,
        "matches_count": len(matches),
    }


# Cette fonction vérifie si deux noms d'équipes correspondent suffisamment pour retrouver le match FlashScore.
def does_flashscore_team_name_match(expected_name: str | None, actual_name: str | None) -> bool:
    expected = normalize_flashscore_text(expected_name)
    actual = normalize_flashscore_text(actual_name)

    if not expected or not actual:
        return False

    return expected == actual or expected in actual or actual in expected


# Cette fonction vérifie une équipe H2H en acceptant les variantes FlashScore comme "Levski Sofia (Bul)".
def does_flashscore_h2h_team_match(expected_name: str | None, actual_name: str | None) -> bool:
    expected = normalize_flashscore_text(expected_name)
    actual = normalize_flashscore_text(actual_name)

    if not expected or not actual:
        return False

    if expected == actual:
        return True

    if len(expected) >= 5 and len(actual) >= 5:
        return expected in actual or actual in expected

    return False


# Cette fonction calcule un score de correspondance entre un match RubyBets et un match FlashScore.
def score_flashscore_match_candidate(
    match: dict[str, Any],
    home_team_name: str,
    away_team_name: str,
) -> int:
    flashscore_home_name = match.get("home_team", {}).get("name")
    flashscore_away_name = match.get("away_team", {}).get("name")

    direct_home_match = does_flashscore_team_name_match(home_team_name, flashscore_home_name)
    direct_away_match = does_flashscore_team_name_match(away_team_name, flashscore_away_name)
    reversed_home_match = does_flashscore_team_name_match(home_team_name, flashscore_away_name)
    reversed_away_match = does_flashscore_team_name_match(away_team_name, flashscore_home_name)

    if direct_home_match and direct_away_match:
        return 100

    if reversed_home_match and reversed_away_match:
        return 80

    if direct_home_match or direct_away_match or reversed_home_match or reversed_away_match:
        return 40

    return 0


# Cette fonction retrouve dans FlashScore le match correspondant à un match RubyBets donné.
def find_flashscore_match(
    home_team_name: str,
    away_team_name: str,
    target_utc_date: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    day_offset = build_flashscore_day_offset(target_utc_date)

    if day_offset is None:
        return None, {
            "provider": "flashscore_rapidapi",
            "status": "missing_target_date",
            "endpoint": "/matches/list",
        }

    matches, metadata = get_flashscore_matches_by_day(day_offset=day_offset)

    if metadata.get("status") != "success":
        return None, metadata

    scored_matches = [
        (
            score_flashscore_match_candidate(
                match=match,
                home_team_name=home_team_name,
                away_team_name=away_team_name,
            ),
            match,
        )
        for match in matches
    ]

    best_score, best_match = max(scored_matches, default=(0, None), key=lambda item: item[0])

    if not best_match or best_score < 80:
        return None, {
            **metadata,
            "status": "not_found",
            "home_team_name": home_team_name,
            "away_team_name": away_team_name,
            "best_score": best_score,
        }

    return best_match, {
        **metadata,
        "status": "matched",
        "match_id": best_match.get("match_id"),
        "home_team_id": best_match.get("home_team", {}).get("team_id"),
        "away_team_id": best_match.get("away_team", {}).get("team_id"),
        "best_score": best_score,
    }


# Cette fonction récupère une page de résultats terminés pour une équipe FlashScore.
def get_flashscore_team_results_page(
    team_id: str,
    page: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = get_rapidapi_flashscore_data(
        "/teams/results",
        {
            "team_id": team_id,
            "page": page,
        },
    )

    if is_flashscore_error_response(data):
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "error",
            "endpoint": "/teams/results",
            "team_id": team_id,
            "page": page,
            "message": data.get("message"),
            "status_code": data.get("status_code"),
        }

    if not isinstance(data, list):
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "unexpected_response",
            "endpoint": "/teams/results",
            "team_id": team_id,
            "page": page,
        }

    matches: list[dict[str, Any]] = []

    for tournament in data:
        if not isinstance(tournament, dict):
            continue

        for match in tournament.get("matches", []) or []:
            if not isinstance(match, dict):
                continue

            match["_flashscore_tournament"] = tournament
            matches.append(match)

    return matches, {
        "provider": "flashscore_rapidapi",
        "status": "success",
        "endpoint": "/teams/results",
        "team_id": team_id,
        "page": page,
        "matches_count": len(matches),
    }


# Cette fonction normalise une équipe FlashScore dans un format proche de Football-Data.
def normalize_flashscore_team(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": team.get("team_id"),
        "name": team.get("name"),
        "shortName": team.get("short_name"),
        "tla": team.get("short_name"),
        "crest": team.get("small_image_path") or team.get("image_path"),
    }


# Cette fonction normalise un match FlashScore dans un format compatible avec team_history_service.py.
def normalize_flashscore_result_match(match: dict[str, Any]) -> dict[str, Any] | None:
    scores = match.get("scores", {}) or {}
    home_score = normalize_flashscore_score_value(scores.get("home"))
    away_score = normalize_flashscore_score_value(scores.get("away"))
    utc_date = convert_flashscore_timestamp_to_utc_date(match.get("timestamp"))

    if home_score is None or away_score is None or utc_date is None:
        return None

    tournament = match.get("_flashscore_tournament", {}) or {}

    return {
        "id": f"flashscore_{match.get('match_id')}",
        "utcDate": utc_date,
        "status": "FINISHED",
        "competition": {
            "id": tournament.get("tournament_id"),
            "code": None,
            "name": tournament.get("full_name") or tournament.get("name"),
            "type": None,
            "emblem": tournament.get("image_path"),
        },
        "homeTeam": normalize_flashscore_team(match.get("home_team", {}) or {}),
        "awayTeam": normalize_flashscore_team(match.get("away_team", {}) or {}),
        "score": {
            "winner": None,
            "duration": "REGULAR",
            "fullTime": {
                "home": home_score,
                "away": away_score,
            },
            "halfTime": {
                "home": None,
                "away": None,
            },
        },
        "data_source": "flashscore_rapidapi",
    }


# Cette fonction normalise une confrontation directe FlashScore dans le format interne RubyBets.
def normalize_flashscore_h2h_match(match: dict[str, Any]) -> dict[str, Any] | None:
    scores = match.get("scores", {}) or {}
    home_score = normalize_flashscore_score_value(scores.get("home"))
    away_score = normalize_flashscore_score_value(scores.get("away"))
    utc_date = convert_flashscore_timestamp_to_utc_date(match.get("timestamp"))

    if home_score is None or away_score is None or utc_date is None:
        return None

    return {
        "id": f"flashscore_{match.get('match_id')}",
        "utcDate": utc_date,
        "status": "FINISHED",
        "competition": {
            "id": None,
            "code": match.get("tournament_name_short"),
            "name": match.get("tournament_name"),
            "type": None,
            "emblem": None,
        },
        "homeTeam": normalize_flashscore_team(match.get("home_team", {}) or {}),
        "awayTeam": normalize_flashscore_team(match.get("away_team", {}) or {}),
        "score": {
            "winner": None,
            "duration": "REGULAR",
            "fullTime": {
                "home": home_score,
                "away": away_score,
            },
            "halfTime": {
                "home": None,
                "away": None,
            },
        },
        "data_source": "flashscore_rapidapi",
    }


# Cette fonction vérifie qu'un élément H2H correspond uniquement aux deux équipes analysées.
def is_direct_flashscore_h2h_match(
    match: dict[str, Any],
    home_team_name: str,
    away_team_name: str,
) -> bool:
    flashscore_home_name = match.get("home_team", {}).get("name")
    flashscore_away_name = match.get("away_team", {}).get("name")

    direct_match = (
        does_flashscore_h2h_team_match(home_team_name, flashscore_home_name)
        and does_flashscore_h2h_team_match(away_team_name, flashscore_away_name)
    )

    reversed_match = (
        does_flashscore_h2h_team_match(home_team_name, flashscore_away_name)
        and does_flashscore_h2h_team_match(away_team_name, flashscore_home_name)
    )

    return direct_match or reversed_match


# Cette fonction récupère et filtre strictement les confrontations directes FlashScore.
def get_flashscore_head_to_head(
    flashscore_match_id: str | None,
    home_team_name: str,
    away_team_name: str,
    limit: int = FLASHSCORE_H2H_LIMIT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not flashscore_match_id:
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "missing_match_id",
            "endpoint": "/matches/h2h",
            "results": 0,
        }

    data = get_rapidapi_flashscore_data(
        "/matches/h2h",
        {
            "match_id": flashscore_match_id,
        },
    )

    if is_flashscore_error_response(data):
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "error",
            "endpoint": "/matches/h2h",
            "match_id": flashscore_match_id,
            "message": data.get("message"),
            "status_code": data.get("status_code"),
            "results": 0,
        }

    if not isinstance(data, list):
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "unexpected_response",
            "endpoint": "/matches/h2h",
            "match_id": flashscore_match_id,
            "results": 0,
        }

    direct_matches = [
        match
        for match in data
        if isinstance(match, dict)
        and is_direct_flashscore_h2h_match(
            match=match,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
        )
    ]

    normalized_matches = [
        normalized_match
        for normalized_match in (
            normalize_flashscore_h2h_match(match) for match in direct_matches
        )
        if normalized_match is not None
    ]

    normalized_matches = sorted(
        normalized_matches,
        key=lambda match: match.get("utcDate") or "",
        reverse=True,
    )[:limit]

    return normalized_matches, {
        "provider": "flashscore_rapidapi",
        "status": "success" if normalized_matches else "empty",
        "endpoint": "/matches/h2h",
        "match_id": flashscore_match_id,
        "raw_items": len(data),
        "direct_items": len(direct_matches),
        "results": len(normalized_matches),
    }


# Cette fonction récupère et normalise les résultats récents d'une équipe FlashScore.
def get_normalized_flashscore_team_results(
    team_id: str | None,
    target_utc_date: str | None,
    limit: int = FLASHSCORE_RESULTS_PAGE_SIZE_LIMIT,
    max_pages: int = FLASHSCORE_MAX_RESULTS_PAGES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not team_id:
        return [], {
            "provider": "flashscore_rapidapi",
            "status": "missing_team_id",
            "endpoint": "/teams/results",
            "results": 0,
        }

    target_datetime = parse_rubybets_utc_datetime(target_utc_date)
    normalized_matches: list[dict[str, Any]] = []
    page_metadata: list[dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        raw_matches, metadata = get_flashscore_team_results_page(team_id=team_id, page=page)
        page_metadata.append(metadata)

        if metadata.get("status") != "success":
            break

        for raw_match in raw_matches:
            normalized_match = normalize_flashscore_result_match(raw_match)

            if not normalized_match:
                continue

            match_datetime = parse_rubybets_utc_datetime(normalized_match.get("utcDate"))

            if target_datetime and match_datetime and match_datetime >= target_datetime:
                continue

            normalized_matches.append(normalized_match)

        if len(normalized_matches) >= limit:
            break

    normalized_matches = sorted(
        normalized_matches,
        key=lambda match: match.get("utcDate") or "",
        reverse=True,
    )[:limit]

    return normalized_matches, {
        "provider": "flashscore_rapidapi",
        "status": "success" if normalized_matches else "empty",
        "endpoint": "/teams/results",
        "team_id": team_id,
        "results": len(normalized_matches),
        "pages_checked": len(page_metadata),
        "pages": page_metadata,
    }


# Cette fonction retrouve un match FlashScore puis récupère les historiques et le H2H des deux équipes.
def get_flashscore_histories_for_match(
    home_team_name: str,
    away_team_name: str,
    target_utc_date: str | None,
    limit: int = FLASHSCORE_RESULTS_PAGE_SIZE_LIMIT,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    flashscore_match, match_metadata = find_flashscore_match(
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        target_utc_date=target_utc_date,
    )

    if not flashscore_match:
        return {
            "home": [],
            "away": [],
            "head_to_head": [],
        }, {
            "provider": "flashscore_rapidapi",
            "status": match_metadata.get("status", "not_found"),
            "match_lookup": match_metadata,
        }

    flashscore_match_id = flashscore_match.get("match_id")
    home_team_id = flashscore_match.get("home_team", {}).get("team_id")
    away_team_id = flashscore_match.get("away_team", {}).get("team_id")

    home_results, home_metadata = get_normalized_flashscore_team_results(
        team_id=home_team_id,
        target_utc_date=target_utc_date,
        limit=limit,
    )
    away_results, away_metadata = get_normalized_flashscore_team_results(
        team_id=away_team_id,
        target_utc_date=target_utc_date,
        limit=limit,
    )
    head_to_head, head_to_head_metadata = get_flashscore_head_to_head(
        flashscore_match_id=flashscore_match_id,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )

    return {
        "home": home_results,
        "away": away_results,
        "head_to_head": head_to_head,
    }, {
        "provider": "flashscore_rapidapi",
        "status": "success" if home_results or away_results or head_to_head else "empty",
        "match_lookup": match_metadata,
        "home_team_results": home_metadata,
        "away_team_results": away_metadata,
        "head_to_head": head_to_head_metadata,
    }


# Schéma de communication du fichier :
# rapidapi_flashscore_client.py
# ├── lit la configuration RapidAPI dans app/core/config.py
# ├── appelle FlashScore via /matches/list pour récupérer et normaliser les matchs à venir
# ├── appelle FlashScore via /matches/details pour préparer les fiches match
# ├── appelle FlashScore via /teams/results pour récupérer les résultats récents
# ├── appelle FlashScore via /matches/h2h pour récupérer les confrontations directes
# ├── fournit des matchs normalisés aux futures routes /api/matches et /api/matches/{match_id}
# └── fournit des historiques réels à l'API /api/matches/{match_id}/team-history
