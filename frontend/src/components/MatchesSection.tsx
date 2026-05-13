// Ce composant affiche les matchs à venir avec les logos des équipes fournis par l’API actuelle.

import type { Match } from "../models/rubybets";

type MatchesSectionProps = {
  selectedCompetition: string;
  matches: Match[];
  onSelectMatch: (matchId: number) => void;
};

type TeamLogoProps = {
  name: string;
  crest?: string | null;
};

// Cette fonction génère des initiales lisibles si le logo d’une équipe est absent ou indisponible.
function getTeamInitials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");
}

// Ce composant affiche le logo d’une équipe avec un fallback texte propre.
function TeamLogo({ name, crest }: TeamLogoProps) {
  return (
    <span className="rb-team-logo-wrap" aria-label={`Logo ${name}`}>
      <span className="rb-team-logo-placeholder">{getTeamInitials(name)}</span>

      {crest ? (
        <img
          className="rb-team-logo"
          src={crest}
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

// Ce composant affiche la liste des matchs disponibles pour la compétition sélectionnée.
function MatchesSection({
  selectedCompetition,
  matches,
  onSelectMatch,
}: MatchesSectionProps) {
  return (
    <section>
      <h2>Matchs à venir — {selectedCompetition}</h2>

      {matches.length === 0 ? (
        <p>Aucun match disponible pour cette compétition.</p>
      ) : (
        <ul className="rb-match-list">
          {matches.map((match) => (
            <li className="rb-match-card" key={match.id}>
              <button
                className="rb-match-card__button"
                type="button"
                onClick={() => onSelectMatch(match.id)}
              >
                <span className="rb-match-card__teams">
                  <span className="rb-team-block rb-team-block--home">
                    <TeamLogo
                      name={match.home_team.name}
                      crest={match.home_team.crest}
                    />
                    <strong className="rb-team-name">
                      {match.home_team.short_name || match.home_team.name}
                    </strong>
                  </span>

                  <span className="rb-versus">vs</span>

                  <span className="rb-team-block rb-team-block--away">
                    <TeamLogo
                      name={match.away_team.name}
                      crest={match.away_team.crest}
                    />
                    <strong className="rb-team-name">
                      {match.away_team.short_name || match.away_team.name}
                    </strong>
                  </span>
                </span>
              </button>

              <div className="rb-match-card__meta">
                <span>{match.competition.name}</span>
                <span>Journée {match.matchday}</span>
                <span>{new Date(match.utc_date).toLocaleString("fr-FR")}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default MatchesSection;

// Schéma de communication du fichier :
// MatchesSection.tsx
// ├── reçoit matches depuis App.tsx via MatchesScreen.tsx
// ├── utilise le type Match défini dans models/rubybets.ts
// ├── affiche home_team.crest et away_team.crest fournis par l’API backend
// └── utilise App.css pour le style des cartes match et des logos
