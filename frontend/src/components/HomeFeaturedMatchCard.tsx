// Ce composant affiche une rencontre mise en avant sur l’accueil avec ses données réelles et un statut lisible.

import { CheckCircle2, Clock3, Eye, Star, type LucideIcon } from "lucide-react";
import { getTeamInitials, getTeamShortName, hasKnownTeams } from "../helpers/displayText";
import type { Competition, Match, Team } from "../models/rubybets";

type HomeFeaturedMatchCardProps = {
  match: Match;
  competition: Competition | null;
  position: number;
  onSelect: (matchId: number) => void;
};

type MatchStatusPresentation = {
  label: string;
  tone: "ready" | "watch" | "pending";
  icon: LucideIcon;
};

// Formate le jour d’une rencontre comme dans la maquette d’accueil validée.
function formatMatchDay(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  const day = new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  })
    .format(date)
    .replace(".", "");

  return day.charAt(0).toUpperCase() + day.slice(1);
}

// Formate l’heure d’une rencontre en conservant le fuseau local du navigateur.
function formatMatchTime(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Retourne le statut public d’une carte sans inventer la disponibilité d’une analyse.
function getMatchStatus(match: Match, position: number): MatchStatusPresentation {
  if (!hasKnownTeams(match)) {
    return {
      label: "Bientôt disponible",
      tone: "pending",
      icon: Clock3,
    };
  }

  if (position === 0) {
    return {
      label: "Prêt à consulter",
      tone: "ready",
      icon: CheckCircle2,
    };
  }

  return {
    label: "À suivre",
    tone: "watch",
    icon: Eye,
  };
}

// Affiche l’emblème d’une équipe ou un fallback propre lorsque la source ne fournit aucun logo.
function TeamBadge({ team }: { team: Team | null | undefined }) {
  const label = getTeamShortName(team);

  return (
    <span className="rb-home-v2-match-team__badge" aria-label={`Logo ${label}`}>
      {team?.crest ? (
        <img src={team.crest} alt="" loading="lazy" decoding="async" />
      ) : (
        <span>{getTeamInitials(team)}</span>
      )}
    </span>
  );
}

// Ce composant restitue une carte cliquable avec compétition, horaire, équipes et état de disponibilité.
function HomeFeaturedMatchCard({
  match,
  competition,
  position,
  onSelect,
}: HomeFeaturedMatchCardProps) {
  const status = getMatchStatus(match, position);
  const StatusIcon = status.icon;
  const homeTeamLabel = getTeamShortName(match.home_team);
  const awayTeamLabel = getTeamShortName(match.away_team);
  const competitionLabel = competition?.name || match.competition.name;

  return (
    <button
      type="button"
      className="rb-home-v2-match-card"
      onClick={() => onSelect(match.id)}
      aria-label={`Ouvrir ${homeTeamLabel} contre ${awayTeamLabel}`}
    >
      <span className="rb-home-v2-match-card__shine" aria-hidden="true" />

      <span className="rb-home-v2-match-card__topline">
        <span className="rb-home-v2-match-card__competition">
          {competition?.emblem ? (
            <img src={competition.emblem} alt="" loading="lazy" decoding="async" />
          ) : (
            <Star aria-hidden="true" size={15} strokeWidth={2} />
          )}
          <span>{competitionLabel}</span>
        </span>

        <span className="rb-home-v2-match-card__datetime">
          <span>{formatMatchDay(match.utc_date)}</span>
          <i aria-hidden="true" />
          <strong>{formatMatchTime(match.utc_date)}</strong>
        </span>
      </span>

      <span className="rb-home-v2-match-card__fixture">
        <span className="rb-home-v2-match-team">
          <TeamBadge team={match.home_team} />
          <strong>{homeTeamLabel}</strong>
        </span>

        <span className="rb-home-v2-match-card__versus" aria-hidden="true">
          VS
        </span>

        <span className="rb-home-v2-match-team">
          <TeamBadge team={match.away_team} />
          <strong>{awayTeamLabel}</strong>
        </span>
      </span>

      <span className={`rb-home-v2-match-card__status rb-home-v2-match-card__status--${status.tone}`}>
        <StatusIcon aria-hidden="true" size={16} strokeWidth={2} />
        {status.label}
      </span>
    </button>
  );
}

export default HomeFeaturedMatchCard;

// Schéma de communication du fichier :
// HomeFeaturedMatchCard.tsx
// ├── reçoit un Match et la Competition active depuis DashboardScreen.tsx
// ├── utilise helpers/displayText.ts pour sécuriser les noms et initiales d’équipes
// ├── utilise les logos réels transmis dans Team.crest et Competition.emblem
// └── renvoie le match sélectionné à DashboardScreen.tsx puis App.tsx
