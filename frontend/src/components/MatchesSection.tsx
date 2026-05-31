// Ce composant affiche les matchs à venir sous forme de liste premium avec logos, date, statut et action.

import type { Match, Team } from "../models/rubybets";
import {
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
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(date);
}

// Cette fonction formate l’heure locale du match.
function formatMatchTime(dateValue: string) {
  const date = new Date(dateValue);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Cette fonction détermine si l’analyse peut être proposée pour un match.
function isAnalysisAvailable(match: Match) {
  const status = match.status?.toUpperCase();

  return hasKnownTeams(match) && (status === "SCHEDULED" || status === "TIMED");
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

// Ce composant affiche une ligne de match cliquable via le bouton d’action.
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
            {selectedCompetition}.
          </p>
        </div>
      ) : (
        <div className="rb-match-table" role="list">
          {matches.map((match) => {
            const analysisAvailable = isAnalysisAvailable(match);
            const homeTeamLabel = getTeamShortName(match.home_team);
            const awayTeamLabel = getTeamShortName(match.away_team);

            return (
              <article className="rb-match-row" key={match.id} role="listitem">
                <div className="rb-match-row__competition">
                  <strong>{match.competition.name}</strong>
                  <span>Journée {match.matchday}</span>
                </div>

                <div className="rb-match-row__date">
                  <strong>{formatMatchDate(match.utc_date)}</strong>
                  <span>{formatMatchTime(match.utc_date)}</span>
                </div>

                <div className="rb-match-row__fixture">
                  <div className="rb-match-team rb-match-team--home">
                    <span className="rb-match-team__name">
                      {homeTeamLabel}
                    </span>
                    <TeamLogo team={match.home_team} />
                  </div>

                  <span className="rb-match-versus">VS</span>

                  <div className="rb-match-team rb-match-team--away">
                    <TeamLogo team={match.away_team} />
                    <span className="rb-match-team__name">
                      {awayTeamLabel}
                    </span>
                  </div>
                </div>

                <div className="rb-match-row__status">
                  <span
                    className={
                      analysisAvailable
                        ? "rb-match-status rb-match-status--available"
                        : "rb-match-status rb-match-status--pending"
                    }
                  >
                    {analysisAvailable ? "Analyse disponible" : "Équipes à confirmer"}
                  </span>

                  <button
                    type="button"
                    onClick={() => onSelectMatch(match.id)}
                  >
                    {analysisAvailable ? "Voir l’analyse" : "Voir le match"}
                  </button>
                </div>
              </article>
            );
          })}
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
// └── utilise App.css pour la liste premium de l’écran Matchs
