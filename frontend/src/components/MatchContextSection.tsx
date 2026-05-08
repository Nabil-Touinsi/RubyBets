// Ce composant affiche le contexte avant-match du match sélectionné dans RubyBets.
import type { MatchContextResponse, TeamStanding } from "../models/rubybets";
import { cleanTextItems } from "../helpers/displayText";
import DataFreshnessBlock from "./DataFreshnessBlock";

type MatchContextSectionProps = {
  matchContext: MatchContextResponse;
};

// Ce composant affiche une carte de classement simplifiée pour une équipe.
function TeamStandingCard({ standing }: { standing: TeamStanding }) {
  return (
    <article>
      <h5>{standing.team.name}</h5>
      <p>Position : {standing.position}</p>
      <p>Points : {standing.points}</p>
      <p>Matchs joués : {standing.played_games}</p>
      <p>
        Buts pour / contre : {standing.goals_for} / {standing.goals_against}
      </p>
      <p>Différence de buts : {standing.goal_difference}</p>
    </article>
  );
}

// Ce composant présente le contexte du match, le classement des équipes et la fraîcheur des données utilisées.
function MatchContextSection({ matchContext }: MatchContextSectionProps) {
  return (
    <section>
      <h2>Contexte avant-match</h2>

      <h3>{matchContext.context.summary.title}</h3>

      <ul>
        {cleanTextItems(matchContext.context.summary.main_facts).map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>

      <h4>Classement des équipes</h4>

      <div>
        {matchContext.context.home_team_standing && (
          <TeamStandingCard standing={matchContext.context.home_team_standing} />
        )}

        {matchContext.context.away_team_standing && (
          <TeamStandingCard standing={matchContext.context.away_team_standing} />
        )}
      </div>

      <DataFreshnessBlock
        title="Fraîcheur des données utilisées pour le contexte"
        dataFreshness={matchContext.data_freshness}
      />
    </section>
  );
}

export default MatchContextSection;

// Schéma de communication du fichier :
// MatchContextSection.tsx
// ├── reçoit le contexte avant-match depuis App.tsx
// ├── utilise TeamStandingCard pour afficher les classements domicile et extérieur
// ├── utilise DataFreshnessBlock.tsx pour afficher la fraîcheur des données
// └── affiche les données de match et classement fournies par le backend
