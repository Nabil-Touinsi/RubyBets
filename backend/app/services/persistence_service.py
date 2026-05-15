# Role du fichier :
# Ce service persiste progressivement les donnees reelles RubyBets dans PostgreSQL
# sans remplacer les routes API, le cache JSON ou les appels Football-Data existants.

from datetime import datetime
from typing import Any

from app.services.database_service import get_database_connection


# Convertit une date Football-Data en datetime compatible PostgreSQL.
def normalize_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    parsed_date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed_date.replace(tzinfo=None)


# Construit un libelle court de saison compatible avec la colonne competitions.season.
def build_competition_season_label(competition: dict[str, Any]) -> str | None:
    current_season = competition.get("current_season") or competition.get("currentSeason") or {}

    season_id = current_season.get("id")
    if season_id:
        return str(season_id)

    start_date = current_season.get("start_date") or current_season.get("startDate")
    end_date = current_season.get("end_date") or current_season.get("endDate")

    if start_date and end_date:
        return f"{str(start_date)[:4]}/{str(end_date)[:4]}"

    return None


# Normalise une competition issue de Football-Data ou deja formatee par RubyBets.
def normalize_competition(competition: dict[str, Any]) -> dict[str, Any] | None:
    external_id = competition.get("id")
    code = competition.get("code")
    name = competition.get("name")

    if not external_id or not code or not name:
        return None

    country = competition.get("country") or competition.get("area", {}).get("name")

    return {
        "external_id": external_id,
        "code": code,
        "name": name,
        "country": country,
        "season": build_competition_season_label(competition),
        "source": "football-data.org",
        "is_active": True,
    }


# Normalise une equipe issue de Football-Data ou deja formatee par RubyBets.
def normalize_team(team: dict[str, Any]) -> dict[str, Any] | None:
    external_id = team.get("id")
    name = team.get("name")

    if not external_id or not name:
        return None

    return {
        "external_id": external_id,
        "name": name,
        "short_name": team.get("short_name") or team.get("shortName"),
        "tla": team.get("tla"),
        "crest_url": team.get("crest") or team.get("crest_url"),
        "country": team.get("country"),
        "source": "football-data.org",
    }


# Normalise un match Football-Data pour insertion dans PostgreSQL.
def normalize_match(match: dict[str, Any]) -> dict[str, Any] | None:
    external_id = match.get("id")
    competition = match.get("competition") or {}
    home_team = match.get("homeTeam") or {}
    away_team = match.get("awayTeam") or {}
    utc_date = normalize_datetime(match.get("utcDate"))

    if not external_id or not competition.get("id") or not home_team.get("id") or not away_team.get("id") or not utc_date:
        return None

    return {
        "external_id": external_id,
        "competition_external_id": competition.get("id"),
        "home_team_external_id": home_team.get("id"),
        "away_team_external_id": away_team.get("id"),
        "utc_date": utc_date,
        "status": match.get("status") or "UNKNOWN",
        "matchday": match.get("matchday"),
        "stage": match.get("stage"),
        "source": "football-data.org",
        "data_freshness": match.get("lastUpdated"),
    }


# Insere ou met a jour les competitions dans PostgreSQL.
def persist_competitions(competitions: list[dict[str, Any]]) -> int:
    normalized_competitions = [
        normalized_competition
        for competition in competitions
        if (normalized_competition := normalize_competition(competition)) is not None
    ]

    if not normalized_competitions:
        return 0

    query = """
        INSERT INTO competitions (
            external_id,
            code,
            name,
            country,
            season,
            source,
            is_active
        )
        VALUES (
            %(external_id)s,
            %(code)s,
            %(name)s,
            %(country)s,
            %(season)s,
            %(source)s,
            %(is_active)s
        )
        ON CONFLICT (external_id)
        DO UPDATE SET
            code = EXCLUDED.code,
            name = EXCLUDED.name,
            country = EXCLUDED.country,
            season = EXCLUDED.season,
            source = EXCLUDED.source,
            is_active = EXCLUDED.is_active,
            updated_at = CURRENT_TIMESTAMP;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(query, normalized_competitions)
        connection.commit()

    return len(normalized_competitions)


# Insere ou met a jour les equipes dans PostgreSQL.
def persist_teams(teams: list[dict[str, Any]]) -> int:
    normalized_teams = [
        normalized_team
        for team in teams
        if (normalized_team := normalize_team(team)) is not None
    ]

    if not normalized_teams:
        return 0

    query = """
        INSERT INTO teams (
            external_id,
            name,
            short_name,
            tla,
            crest_url,
            country,
            source
        )
        VALUES (
            %(external_id)s,
            %(name)s,
            %(short_name)s,
            %(tla)s,
            %(crest_url)s,
            %(country)s,
            %(source)s
        )
        ON CONFLICT (external_id)
        DO UPDATE SET
            name = EXCLUDED.name,
            short_name = EXCLUDED.short_name,
            tla = EXCLUDED.tla,
            crest_url = EXCLUDED.crest_url,
            country = EXCLUDED.country,
            source = EXCLUDED.source,
            updated_at = CURRENT_TIMESTAMP;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(query, normalized_teams)
        connection.commit()

    return len(normalized_teams)


# Insere ou met a jour les matchs dans PostgreSQL en reliant competition et equipes.
def persist_matches(matches: list[dict[str, Any]]) -> int:
    normalized_matches = [
        normalized_match
        for match in matches
        if (normalized_match := normalize_match(match)) is not None
    ]

    if not normalized_matches:
        return 0

    query = """
        INSERT INTO matches (
            external_id,
            competition_id,
            home_team_id,
            away_team_id,
            utc_date,
            status,
            matchday,
            stage,
            source,
            data_freshness
        )
        SELECT
            %(external_id)s,
            competition.id,
            home_team.id,
            away_team.id,
            %(utc_date)s,
            %(status)s,
            %(matchday)s,
            %(stage)s,
            %(source)s,
            %(data_freshness)s
        FROM competitions AS competition
        JOIN teams AS home_team
            ON home_team.external_id = %(home_team_external_id)s
        JOIN teams AS away_team
            ON away_team.external_id = %(away_team_external_id)s
        WHERE competition.external_id = %(competition_external_id)s
        ON CONFLICT (external_id)
        DO UPDATE SET
            competition_id = EXCLUDED.competition_id,
            home_team_id = EXCLUDED.home_team_id,
            away_team_id = EXCLUDED.away_team_id,
            utc_date = EXCLUDED.utc_date,
            status = EXCLUDED.status,
            matchday = EXCLUDED.matchday,
            stage = EXCLUDED.stage,
            source = EXCLUDED.source,
            data_freshness = EXCLUDED.data_freshness,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id;
    """

    persisted_count = 0

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            for match in normalized_matches:
                cursor.execute(query, match)
                if cursor.fetchone():
                    persisted_count += 1
        connection.commit()

    return persisted_count


# Execute la persistance des competitions sans casser la route appelante si la base est indisponible.
def try_persist_competitions(competitions: list[dict[str, Any]]) -> int:
    try:
        return persist_competitions(competitions)
    except Exception:
        return 0


# Execute la persistance des equipes sans casser la route appelante si la base est indisponible.
def try_persist_teams(teams: list[dict[str, Any]]) -> int:
    try:
        return persist_teams(teams)
    except Exception:
        return 0


# Execute la persistance des matchs sans casser la route appelante si la base est indisponible.
def try_persist_matches(matches: list[dict[str, Any]]) -> int:
    try:
        return persist_matches(matches)
    except Exception:
        return 0


# Schema de communication :
# competitions.py / matches.py
#     ↓
# persistence_service.py
#     ↓
# database_service.py
#     ↓
# PostgreSQL rubybets_db