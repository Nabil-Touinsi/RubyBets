// Ce composant affiche le contexte avant-match du match sélectionné dans RubyBets.

import type { MatchContextResponse, TeamStanding } from "../models/rubybets";
import { cleanTextItems } from "../helpers/displayText";

type MatchContextSectionProps = {
  matchContext: MatchContextResponse;
};

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
    </section>
  );
}

export default MatchContextSection;