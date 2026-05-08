// Ce composant affiche la fiche détail du match sélectionné dans RubyBets.
import type { MatchDetailsResponse } from "../models/rubybets";
import { formatDateTime, formatMatchStatus } from "../helpers/displayText";
import DataFreshnessBlock from "./DataFreshnessBlock";

type MatchDetailsSectionProps = {
  matchDetails: MatchDetailsResponse;
};

// Ce composant présente les informations principales d’un match et la fraîcheur des données associées.
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

      <p>Date : {formatDateTime(matchDetails.match.utc_date)}</p>

      <p>Statut : {formatMatchStatus(matchDetails.match.status)}</p>
      <p>Journée : {matchDetails.match.matchday}</p>
      <p>Source : {matchDetails.source}</p>

      <p>
        Dernière mise à jour source :{" "}
        {formatDateTime(matchDetails.data_freshness.last_updated)}
      </p>

      <DataFreshnessBlock
        title="Fraîcheur des données de la fiche match"
        dataFreshness={matchDetails.data_freshness}
      />
    </section>
  );
}

export default MatchDetailsSection;

// Schéma de communication du fichier :
// MatchDetailsSection.tsx
// ├── reçoit la fiche détail depuis App.tsx
// ├── utilise displayText.ts pour formater la date et le statut du match
// ├── utilise DataFreshnessBlock.tsx pour afficher la fraîcheur des données
// └── affiche les informations de match fournies par le backend
