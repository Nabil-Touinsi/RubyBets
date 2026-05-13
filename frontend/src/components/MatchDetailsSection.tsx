// Ce composant affiche les statistiques disponibles et les métadonnées techniques du match.

import type {
  MatchContextResponse,
  MatchDetailsResponse,
  TeamStanding,
} from "../models/rubybets";
import { formatDateTime, formatMatchStatus } from "../helpers/displayText";

type MatchDetailsSectionProps = {
  matchDetails: MatchDetailsResponse;
  matchContext: MatchContextResponse | null;
};

// Cette fonction affiche une valeur ou un état indisponible.
function displayValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  return value;
}

// Cette fonction calcule une moyenne de buts par match.
function getGoalsAverage(standing: TeamStanding | null) {
  if (!standing || standing.played_games === 0) {
    return "—";
  }

  return (standing.goals_for / standing.played_games).toFixed(2);
}

// Cette fonction calcule une possession indicative non disponible dans la V1.
function getUnavailableMetric() {
  return "Non disponible";
}

// Ce composant affiche une carte statistique comparable entre les deux équipes.
function StatComparisonCard({
  label,
  homeValue,
  awayValue,
  helper,
}: {
  label: string;
  homeValue: string | number;
  awayValue: string | number;
  helper?: string;
}) {
  return (
    <article className="rb-detail-stat-card">
      <div className="rb-detail-stat-card__header">
        <strong>{label}</strong>
        <span>ⓘ</span>
      </div>

      <div className="rb-detail-stat-card__values">
        <p>
          <strong>{homeValue}</strong>
          <span>Dom.</span>
        </p>
        <p>
          <strong>{awayValue}</strong>
          <span>Ext.</span>
        </p>
      </div>

      {helper ? <small>{helper}</small> : null}
    </article>
  );
}

// Ce composant affiche les statistiques disponibles sans inventer de données absentes.
function MatchDetailsSection({
  matchDetails,
  matchContext,
}: MatchDetailsSectionProps) {
  const match = matchDetails.match;
  const homeStanding = matchContext?.context.home_team_standing ?? null;
  const awayStanding = matchContext?.context.away_team_standing ?? null;

  return (
    <section className="rb-detail-card rb-detail-stats-section">
      <div className="rb-detail-card__header">
        <div>
          <p className="rb-detail-kicker">Statistiques disponibles</p>
          <h3>Repères issus des données match et classement</h3>
        </div>

        <span className="rb-detail-soft-badge">
          {formatMatchStatus(match.status)}
        </span>
      </div>

      <div className="rb-detail-stat-grid">
        <StatComparisonCard
          label="Classement"
          homeValue={displayValue(homeStanding?.position)}
          awayValue={displayValue(awayStanding?.position)}
          helper="Position actuelle"
        />

        <StatComparisonCard
          label="Points"
          homeValue={displayValue(homeStanding?.points)}
          awayValue={displayValue(awayStanding?.points)}
          helper="Total en championnat"
        />

        <StatComparisonCard
          label="Buts / match"
          homeValue={getGoalsAverage(homeStanding)}
          awayValue={getGoalsAverage(awayStanding)}
          helper="Moyenne offensive"
        />

        <StatComparisonCard
          label="Différence de buts"
          homeValue={displayValue(homeStanding?.goal_difference)}
          awayValue={displayValue(awayStanding?.goal_difference)}
          helper="Écart buts pour / contre"
        />

        <StatComparisonCard
          label="Matchs joués"
          homeValue={displayValue(homeStanding?.played_games)}
          awayValue={displayValue(awayStanding?.played_games)}
          helper="Volume disponible"
        />

        <StatComparisonCard
          label="Possession / tirs"
          homeValue={getUnavailableMetric()}
          awayValue={getUnavailableMetric()}
          helper="Prévu pour enrichissement data"
        />
      </div>

      <div className="rb-detail-meta-strip">
        <span>
          Source <strong>{matchDetails.source}</strong>
        </span>
        <span>
          Compétition <strong>{match.competition.code}</strong>
        </span>
        <span>
          Journée <strong>{match.matchday}</strong>
        </span>
        <span>
          Dernière mise à jour{" "}
          <strong>{formatDateTime(matchDetails.data_freshness.last_updated)}</strong>
        </span>
      </div>
    </section>
  );
}

export default MatchDetailsSection;

// Schéma de communication du fichier :
// MatchDetailsSection.tsx
// ├── reçoit matchDetails depuis MatchDetailsScreen.tsx
// ├── reçoit matchContext pour comparer les classements disponibles
// ├── affiche uniquement les données disponibles ou signale les données absentes
// └── ne modifie aucun appel API ni contrat backend