// Ce composant affiche la fiche détail du match sélectionné dans RubyBets.

import type { MatchDetailsResponse } from "../models/rubybets";
import { formatMatchStatus } from "../helpers/displayText";

type MatchDetailsSectionProps = {
  matchDetails: MatchDetailsResponse;
};

function MatchDetailsSection({ matchDetails }: MatchDetailsSectionProps) {
  return (
    <section>
      <h2>Fiche détail match</h2>

      <h3>
        {matchDetails.match.home_team.name} vs {matchDetails.match.away_team.name}
      </h3>

      <p>
        Compétition : {matchDetails.match.competition.name} (
        {matchDetails.match.competition.code})
      </p>

      <p>
        Date : {new Date(matchDetails.match.utc_date).toLocaleString("fr-FR")}
      </p>

      <p>Statut : {formatMatchStatus(matchDetails.match.status)}</p>
      <p>Journée : {matchDetails.match.matchday}</p>
      <p>Source : {matchDetails.source}</p>

      <p>
        Dernière mise à jour : {matchDetails.data_freshness.last_updated}
      </p>
    </section>
  );
}

export default MatchDetailsSection;