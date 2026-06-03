// Ce composant affiche les matchs à venir dans une table premium avec logos, statut, compte à rebours et action d’ouverture.

import { BarChart3, ChevronRight, Clock3 } from "lucide-react";
import type { Match, Team } from "../models/rubybets";
import {
  formatMatchStatus,
  getTeamInitials,
  getTeamShortName,
  hasKnownTeams,
} from "../helpers/displayText";

type MatchesSectionProps = {
  selectedCompetition: string;
  matches: Match[];
  onSelectMatch: (matchId: number) => void;
};

type TeamLogoProps = {
  team: Team | null | undefined;
};

// Cette fonction formate la date pour une lecture compacte dans la liste des matchs.
function formatMatchDate(dateValue: string) {
  const date = new Date(dateValue);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

// Cette fonction formate l’heure locale du match.
function formatMatchTime(dateValue: string) {
  const date = new Date(dateValue);

  if (Number.isNaN(date.getTime())) {
    return "Heure à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Cette fonction calcule un compte à rebours lisible pour les matchs programmés.
function formatMatchCountdown(dateValue: string) {
  const matchTime = new Date(dateValue).getTime();
  const now = Date.now();

  if (!Number.isFinite(matchTime)) {
    return "horaire à confirmer";
  }

  const diff = matchTime - now;

  if (diff <= 0) {
    return "horaire atteint";
  }

  const totalMinutes = Math.floor(diff / (1000 * 60));
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;

  if (days > 0) {
    return `${days}j ${hours}h`;
  }

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }

  return `${minutes}m`;
}

// Cette fonction détermine si l’analyse peut être proposée pour un match.
function isAnalysisAvailable(match: Match) {
  const status = match.status?.toUpperCase();

  return hasKnownTeams(match) && (status === "SCHEDULED" || status === "TIMED");
}

// Cette fonction retourne une classe visuelle selon la disponibilité de l’analyse.
function getAvailabilityClass(match: Match) {
  return isAnalysisAvailable(match)
    ? "rb-match-status rb-match-status--available"
    : "rb-match-status rb-match-status--pending";
}

// Cette fonction retourne un statut utilisateur sobre sans promettre de résultat sportif.
function getReadableStatusLabel(match: Match) {
  if (isAnalysisAvailable(match)) {
    return "à venir";
  }

  if (hasKnownTeams(match)) {
    return formatMatchStatus(match.status);
  }

  return "données partielles";
}

// Ce composant affiche le logo d’une équipe avec un fallback propre.
function TeamLogo({ team }: TeamLogoProps) {
  const teamLabel = getTeamShortName(team);

  return (
    <span className="rb-match-team-logo" aria-label={`Logo ${teamLabel}`}>
      <span className="rb-match-team-logo__fallback">
        {getTeamInitials(team)}
      </span>

      {team?.crest ? (
        <img
          src={team.crest}
          alt=""
          loading="lazy"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
    </span>
  );
}

// Ce composant affiche une ligne de match avec une action claire vers la fiche d’analyse.
function MatchRow({
  match,
  onSelectMatch,
}: {
  match: Match;
  onSelectMatch: (matchId: number) => void;
}) {
  const analysisAvailable = isAnalysisAvailable(match);
  const homeTeamLabel = getTeamShortName(match.home_team);
  const awayTeamLabel = getTeamShortName(match.away_team);
  const statusLabel = getReadableStatusLabel(match);

  return (
    <article className="rb-match-row" role="listitem">
      <div className="rb-match-row__date">
        <strong>{formatMatchDate(match.utc_date)}</strong>
        <span>{formatMatchTime(match.utc_date)}</span>
      </div>

      <div className="rb-match-row__competition">
        <strong>{match.competition.name}</strong>
        <span>
          {match.stage ? match.stage : match.matchday ? `Journée ${match.matchday}` : "Phase à confirmer"}
        </span>
      </div>

      <div className="rb-match-row__fixture">
        <div className="rb-match-team rb-match-team--home">
          <span className="rb-match-team__name">{homeTeamLabel}</span>
          <TeamLogo team={match.home_team} />
        </div>

        <span className="rb-match-versus">VS</span>

        <div className="rb-match-team rb-match-team--away">
          <TeamLogo team={match.away_team} />
          <span className="rb-match-team__name">{awayTeamLabel}</span>
        </div>
      </div>

      <div className="rb-match-row__status">
        <span className={getAvailabilityClass(match)}>
          <Clock3 size={14} aria-hidden="true" />
          {statusLabel}
        </span>
        <small>{formatMatchCountdown(match.utc_date)}</small>
      </div>

      <div className="rb-match-row__info">
        <span title="Analyse avant-match disponible selon les données reçues">
          <BarChart3 size={17} aria-hidden="true" />
        </span>

        <button
          className={
            analysisAvailable
              ? "rb-match-action-button rb-match-action-button--analysis"
              : "rb-match-action-button rb-match-action-button--view"
          }
          type="button"
          onClick={() => onSelectMatch(match.id)}
          aria-label={`Ouvrir l’analyse du match ${homeTeamLabel} contre ${awayTeamLabel}`}
        >
          <span>{analysisAvailable ? "Analyser" : "Voir"}</span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}

// Ce composant affiche la liste complète des matchs ou un état vide exploitable.
function MatchesSection({
  selectedCompetition,
  matches,
  onSelectMatch,
}: MatchesSectionProps) {
  return (
    <section className="rb-matches-section">
      {matches.length === 0 ? (
        <div className="rb-matches-empty-state">
          <h3>Aucun match trouvé</h3>
          <p>
            Aucun match ne correspond aux filtres appliqués pour la compétition{" "}
            {selectedCompetition}. Ajustez la date, le statut ou la recherche.
          </p>
        </div>
      ) : (
        <div className="rb-match-table" role="list">
          <div className="rb-match-table__head" aria-hidden="true">
            <span>Date</span>
            <span>Compétition</span>
            <span>Match</span>
            <span>Statut</span>
            <span>Infos</span>
          </div>

          {matches.map((match) => (
            <MatchRow
              key={match.id}
              match={match}
              onSelectMatch={onSelectMatch}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default MatchesSection;

// Schéma de communication du fichier :
// MatchesSection.tsx
// ├── reçoit matches depuis MatchesScreen.tsx
// ├── utilise le type Match défini dans models/rubybets.ts
// ├── sécurise les équipes inconnues via helpers/displayText.ts
// ├── déclenche onSelectMatch pour ouvrir la fiche du match
// └── utilise App.css pour la table premium de l’écran Matchs
