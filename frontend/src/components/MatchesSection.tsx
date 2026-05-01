// Ce composant affiche les matchs à venir disponibles pour la compétition sélectionnée.

import type { Match } from "../models/rubybets";

type MatchesSectionProps = {
  selectedCompetition: string;
  matches: Match[];
  onSelectMatch: (matchId: number) => void;
};

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
        <ul>
          {matches.map((match) => (
            <li key={match.id}>
              <button type="button" onClick={() => onSelectMatch(match.id)}>
                <strong>{match.home_team.name}</strong> vs{" "}
                <strong>{match.away_team.name}</strong>
              </button>
              <br />
              <span>
                {match.competition.name} — Journée {match.matchday} —{" "}
                {new Date(match.utc_date).toLocaleString("fr-FR")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default MatchesSection;