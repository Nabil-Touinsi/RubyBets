// Ce composant affiche les matchs à venir dans une table premium avec logos, statut et action d’ouverture.

import { CheckCircle2, ChevronRight, CircleX, Clock3, LoaderCircle } from "lucide-react";
import type { Competition, Match, Team } from "../models/rubybets";
import {
  formatMatchStatus,
  getTeamDisplayName,
  getTeamInitials,
  hasKnownTeams,
} from "../helpers/displayText";

type MatchesSectionProps = {
  competitions: Competition[];
  selectedCompetition: string;
  matches: Match[];
  onSelectMatch: (matchId: number) => void;
  informationLoading: boolean;
  transitionDirection: "forward" | "backward" | "replace";
};

type TeamLogoProps = {
  team: Team | null | undefined;
};

type MatchInformationStatus = "available" | "loading" | "unavailable";

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


// Cette fonction détermine l’état des informations de base disponibles pour une rencontre.
function getMatchInformationStatus(
  match: Match,
  informationLoading: boolean,
): MatchInformationStatus {
  if (informationLoading) {
    return "loading";
  }

  const status = match.status?.toUpperCase();
  const unavailableStatuses = new Set([
    "CANCELLED",
    "CANCELED",
    "POSTPONED",
    "SUSPENDED",
  ]);

  if (
    !hasKnownTeams(match) ||
    (status ? unavailableStatuses.has(status) : false)
  ) {
    return "unavailable";
  }

  if (!status) {
    return "unavailable";
  }

  return "available";
}

// Cette fonction retourne le libellé accessible associé à l’état des informations.
function getMatchInformationLabel(status: MatchInformationStatus) {
  const labels: Record<MatchInformationStatus, string> = {
    available: "Informations disponibles",
    loading: "Informations en cours de récupération",
    unavailable: "Informations indisponibles",
  };

  return labels[status];
}

// Ce composant affiche une lumière colorée claire pour l’état des informations du match.
function MatchInformationLight({
  status,
}: {
  status: MatchInformationStatus;
}) {
  const label = getMatchInformationLabel(status);

  return (
    <span
      className={`rb-match-info-light rb-match-info-light--${status}`}
      role="img"
      aria-label={label}
      title={label}
    >
      {status === "available" ? (
        <CheckCircle2 size={16} aria-hidden="true" />
      ) : status === "loading" ? (
        <LoaderCircle size={16} aria-hidden="true" />
      ) : (
        <CircleX size={16} aria-hidden="true" />
      )}
    </span>
  );
}

// Cette fonction normalise un nom de compétition pour rapprocher les libellés Football-Data et FlashScore.
function normalizeCompetitionName(value: string | null | undefined) {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/^europe:\s*/, "")
    .replace(/uefa\s+/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

// Cette fonction retrouve la compétition officielle afin d’utiliser son véritable emblème dans le tableau.
function resolveMatchCompetition(
  match: Match,
  competitions: Competition[],
  selectedCompetition: string,
) {
  const matchCode = match.competition.code?.trim().toUpperCase();
  const matchName = normalizeCompetitionName(match.competition.name);

  const directCodeMatch = competitions.find(
    (competition) =>
      competition.code?.trim().toUpperCase() === matchCode &&
      matchCode !== "FS",
  );

  if (directCodeMatch) {
    return directCodeMatch;
  }

  const nameMatch = competitions.find((competition) => {
    const competitionName = normalizeCompetitionName(competition.name);

    return (
      competitionName === matchName ||
      competitionName.includes(matchName) ||
      matchName.includes(competitionName)
    );
  });

  if (nameMatch) {
    return nameMatch;
  }

  return competitions.find(
    (competition) =>
      competition.code?.trim().toUpperCase() ===
      selectedCompetition.trim().toUpperCase(),
  );
}

// Ce composant affiche le logo d’une équipe avec un fallback propre.
function TeamLogo({ team }: TeamLogoProps) {
  const teamLabel = getTeamDisplayName(team);

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
          decoding="async"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
    </span>
  );
}

// Ce composant affiche l’emblème de la compétition avec un fallback textuel.
function CompetitionLogo({
  emblem,
  code,
}: {
  emblem: string | undefined;
  code: string;
}) {
  const normalizedCode = code.trim().toUpperCase();
  const needsLightLogo = normalizedCode === "CL";
  const isPremierLeague = normalizedCode === "PL";
  const logoClassName = [
    "rb-match-competition-logo",
    needsLightLogo ? "rb-match-competition-logo--high-contrast" : "",
    isPremierLeague ? "rb-match-competition-logo--premier-league" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span
      className={logoClassName}
      aria-hidden="true"
    >
      <span>{code.slice(0, 2)}</span>
      {emblem ? (
        <img
          src={emblem}
          alt=""
          loading="lazy"
          decoding="async"
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
  competitions,
  onSelectMatch,
  informationLoading,
  selectedCompetition,
}: {
  match: Match;
  competitions: Competition[];
  onSelectMatch: (matchId: number) => void;
  informationLoading: boolean;
  selectedCompetition: string;
}) {
  const analysisAvailable = isAnalysisAvailable(match);
  const homeTeamLabel = getTeamDisplayName(match.home_team);
  const awayTeamLabel = getTeamDisplayName(match.away_team);
  const statusLabel = getReadableStatusLabel(match);
  const resolvedCompetition = resolveMatchCompetition(
    match,
    competitions,
    selectedCompetition,
  );
  const competitionEmblem = resolvedCompetition?.emblem;
  const competitionCode =
    resolvedCompetition?.code ?? match.competition.code ?? selectedCompetition;
  const informationStatus = getMatchInformationStatus(
    match,
    informationLoading,
  );

  return (
    <article className="rb-match-row" role="listitem">
      <div className="rb-match-row__date">
        <strong>{formatMatchDate(match.utc_date)}</strong>
        <span>{formatMatchTime(match.utc_date)}</span>
      </div>

      <div className="rb-match-row__competition">
        <CompetitionLogo
          emblem={competitionEmblem}
          code={competitionCode}
        />
        <div>
          <strong>{match.competition.name}</strong>
          <span>
            {match.stage
              ? match.stage
              : match.matchday
                ? `Journée ${match.matchday}`
                : "Phase à confirmer"}
          </span>
        </div>
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
          <Clock3 size={13} aria-hidden="true" />
          {statusLabel}
        </span>
        <small>{formatMatchCountdown(match.utc_date)}</small>
      </div>

      <div className="rb-match-row__info">
        <MatchInformationLight status={informationStatus} />
      </div>

      <div className="rb-match-row__action">
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
          <ChevronRight size={17} aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}

// Ce composant affiche la liste complète des matchs ou un état vide exploitable.
function MatchesSection({
  competitions,
  selectedCompetition,
  matches,
  onSelectMatch,
  informationLoading,
  transitionDirection,
}: MatchesSectionProps) {
  return (
    <section
      className={`rb-matches-section rb-matches-section--${transitionDirection}`}
    >
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
            <span>Action</span>
          </div>

          {matches.map((match) => (
            <MatchRow
              key={match.id}
              match={match}
              competitions={competitions}
              onSelectMatch={onSelectMatch}
              informationLoading={informationLoading}
              selectedCompetition={selectedCompetition}
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
// ├── reçoit matches et competitions depuis MatchesScreen.tsx
// ├── utilise les types Match, Team et Competition de models/rubybets.ts
// ├── sécurise les équipes inconnues via helpers/displayText.ts
// ├── déclenche onSelectMatch pour ouvrir la fiche du match
// ├── affiche la disponibilité des informations avec un voyant vert, jaune ou rouge
// ├── anime le remplacement de la liste selon le sens de navigation
// └── utilise styles/MatchesScreen.css pour la table premium de l’écran Matchs
