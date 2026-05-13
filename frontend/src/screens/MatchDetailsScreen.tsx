// Ce fichier affiche l’écran Détail match de RubyBets sous forme de dashboard compact proche de la maquette.

import type {
  Match,
  MatchContextResponse,
  MatchDetailsResponse,
  Team,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import { formatDateTime, formatMatchStatus } from "../helpers/displayText";
import MatchDetailsSection from "../components/MatchDetailsSection";
import MatchContextSection from "../components/MatchContextSection";
import MatchNewsSection from "../components/MatchNewsSection";

type MatchDetailsScreenProps = {
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  matchDetailsStatus: string;
  matchContextStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

// Cette fonction récupère le match disponible depuis le détail ou le contexte.
function getSelectedMatch(
  matchDetails: MatchDetailsResponse | null,
  matchContext: MatchContextResponse | null,
): Match | null {
  return matchDetails?.match ?? matchContext?.match ?? null;
}

// Cette fonction formate une date courte pour le hero match.
function formatShortDate(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(date);
}

// Cette fonction formate l’heure du coup d’envoi.
function formatKickoffTime(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Heure à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Cette fonction affiche la fraîcheur la plus pertinente disponible.
function getFreshnessLabel(
  matchDetails: MatchDetailsResponse | null,
  matchContext: MatchContextResponse | null,
) {
  const value =
    matchDetails?.data_freshness.last_updated ??
    matchContext?.data_freshness.match_last_updated ??
    matchDetails?.match.last_updated ??
    matchContext?.match.last_updated ??
    null;

  return value ? formatDateTime(value) : "non disponible";
}

// Cette fonction affiche le classement d’une équipe si disponible.
function getStandingLabel(
  matchContext: MatchContextResponse | null,
  teamType: "home" | "away",
) {
  const standing =
    teamType === "home"
      ? matchContext?.context.home_team_standing
      : matchContext?.context.away_team_standing;

  if (!standing) {
    return "Classement indisponible";
  }

  return `${standing.position}e · ${standing.points} pts`;
}

// Ce composant affiche un logo d’équipe avec un fallback texte.
function TeamLogo({ team }: { team: Team }) {
  const fallback =
    team.tla ??
    team.short_name
      .split(" ")
      .map((word) => word.charAt(0))
      .join("")
      .slice(0, 3)
      .toUpperCase();

  return (
    <span className="rb-detail-team-logo" aria-label={`Logo ${team.name}`}>
      <span className="rb-detail-team-logo__fallback">{fallback}</span>
      {team.crest ? (
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

// Ce composant affiche le hero principal du match sélectionné.
function MatchSummaryHero({
  match,
  matchContext,
}: {
  match: Match;
  matchContext: MatchContextResponse | null;
}) {
  return (
    <section className="rb-detail-hero rb-detail-hero--compact">
      <div className="rb-detail-team rb-detail-team--home">
        <div>
          <h2>{match.home_team.name}</h2>
          <p>{getStandingLabel(matchContext, "home")}</p>
        </div>
        <TeamLogo team={match.home_team} />
      </div>

      <div className="rb-detail-hero-center">
        <p className="rb-detail-kicker">{match.competition.name}</p>
        <span className="rb-detail-vs">VS</span>
        <strong>
          {formatShortDate(match.utc_date)} · {formatKickoffTime(match.utc_date)}
        </strong>
        <p>
          Journée {match.matchday} · {formatMatchStatus(match.status)}
        </p>
        <small>Lieu non disponible dans les données actuelles</small>
      </div>

      <div className="rb-detail-team rb-detail-team--away">
        <TeamLogo team={match.away_team} />
        <div>
          <h2>{match.away_team.name}</h2>
          <p>{getStandingLabel(matchContext, "away")}</p>
        </div>
      </div>
    </section>
  );
}

// Ce composant affiche une carte placeholder pour les absences.
function AvailabilityPlaceholder({ match }: { match: Match }) {
  return (
    <section className="rb-detail-card rb-detail-availability-card">
      <div className="rb-detail-card__header">
        <div>
          <p className="rb-detail-kicker">Absences et incertitudes</p>
          <h3>Disponibilités à brancher plus tard</h3>
        </div>
        <span className="rb-detail-soft-badge">Prévu</span>
      </div>

      <div className="rb-detail-availability-grid">
        <article>
          <strong>{match.home_team.short_name}</strong>
          <p>Aucune donnée d’absence n’est encore reliée côté backend.</p>
        </article>

        <article>
          <strong>{match.away_team.short_name}</strong>
          <p>Zone prévue pour les blessures, suspensions ou incertitudes.</p>
        </article>
      </div>
    </section>
  );
}

// Ce composant affiche une carte d’action vers une étape suivante.
function DetailActionCard({
  icon,
  title,
  description,
  buttonLabel,
  onClick,
}: {
  icon: string;
  title: string;
  description: string;
  buttonLabel: string;
  onClick: () => void;
}) {
  return (
    <article className="rb-detail-action-card">
      <span className="rb-detail-action-card__icon">{icon}</span>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
        <button type="button" onClick={onClick}>
          {buttonLabel}
        </button>
      </div>
    </article>
  );
}

// Ce composant structure l’écran Détail match sans modifier la logique métier existante.
function MatchDetailsScreen({
  matchDetails,
  matchContext,
  matchDetailsStatus,
  matchContextStatus,
  onNavigate,
}: MatchDetailsScreenProps) {
  const selectedMatch = getSelectedMatch(matchDetails, matchContext);

  if (!selectedMatch) {
    return (
      <div className="rb-detail-screen">
        <article className="rb-detail-empty-state">
          <p className="rb-detail-kicker">Détail match</p>
          <h2>Aucun match sélectionné</h2>
          <p>Sélectionnez une rencontre depuis l’écran Matchs.</p>
          <button type="button" onClick={() => onNavigate("matches")}>
            Retour aux matchs
          </button>
        </article>
      </div>
    );
  }

  return (
    <div className="rb-match-details-screen rb-detail-screen rb-detail-screen--mockup">
      <header className="rb-detail-topbar">
        <div className="rb-detail-topbar__left">
          <button type="button" onClick={() => onNavigate("matches")}>
            ← Retour
          </button>
          <span>Fiche détail match</span>
          <strong>3 / 8</strong>
        </div>

        <div className="rb-detail-topbar__freshness">
          <span />
          Données mises à jour : {getFreshnessLabel(matchDetails, matchContext)}
        </div>
      </header>

      <MatchSummaryHero match={selectedMatch} matchContext={matchContext} />

      <section className="rb-detail-dashboard-grid">
        <div className="rb-detail-dashboard-grid__main">
          {matchContext ? (
            <MatchContextSection matchContext={matchContext} />
          ) : (
            <article className="rb-detail-empty-state">
              <p className="rb-detail-kicker">Contexte du match</p>
              <h3>Contexte avant-match indisponible</h3>
              <p>{matchContextStatus}</p>
            </article>
          )}

          {matchDetails ? (
            <MatchDetailsSection
              matchDetails={matchDetails}
              matchContext={matchContext}
            />
          ) : (
            <article className="rb-detail-empty-state">
              <p className="rb-detail-kicker">Informations match</p>
              <h3>Détail indisponible</h3>
              <p>{matchDetailsStatus}</p>
            </article>
          )}

          <div className="rb-detail-bottom-grid">
            <AvailabilityPlaceholder match={selectedMatch} />

            <section className="rb-detail-card rb-detail-responsible-card">
              <p className="rb-detail-kicker">Contexte actuel</p>
              <h3>Lecture avant-match</h3>
              <p>
                Les données disponibles servent à préparer l’analyse. Elles ne
                garantissent aucun résultat sportif et ne constituent pas un
                conseil d’investissement.
              </p>
            </section>

            <MatchNewsSection match={selectedMatch} />
          </div>
        </div>
      </section>

      <section className="rb-detail-actions-grid">
        <DetailActionCard
          icon="↗"
          title="Analyse pré-match"
          description="Découvrir les facteurs clés, tendances et limites de données pour cette rencontre."
          buttonLabel="Voir l’analyse"
          onClick={() => onNavigate("analysis")}
        />

        <DetailActionCard
          icon="◎"
          title="Prédictions"
          description="Accéder aux tendances explicables générées à partir des données disponibles."
          buttonLabel="Voir les prédictions"
          onClick={() => onNavigate("predictions")}
        />
      </section>

      <p className="rb-detail-footer-note">
        Outil d’aide à la décision. Les analyses proposées ne constituent pas un
        conseil d’investissement ou un pari.
      </p>
    </div>
  );
}

export default MatchDetailsScreen;

// Schéma de communication du fichier :
// MatchDetailsScreen.tsx
// ├── reçoit le détail et le contexte depuis App.tsx
// ├── utilise MatchDetailsSection.tsx pour les statistiques et métadonnées
// ├── utilise MatchContextSection.tsx pour le contexte avant-match
// ├── utilise MatchNewsSection.tsx comme zone actualités non branchée
// └── déclenche la navigation vers Matchs, Analyse et Prédictions via onNavigate