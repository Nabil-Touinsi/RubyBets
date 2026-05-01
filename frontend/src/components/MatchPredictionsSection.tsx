// Ce composant affiche les prédictions avant-match du match sélectionné dans RubyBets.
import type { MatchPredictionsResponse } from "../models/rubybets";
import {
  cleanTextItems,
  formatConfidenceLevel,
  formatPredictionStatus,
  formatRiskLevel,
} from "../helpers/displayText";

type MatchPredictionsSectionProps = {
  matchPredictions: MatchPredictionsResponse;
};

function MatchPredictionsSection({
  matchPredictions,
}: MatchPredictionsSectionProps) {
  const predictionData = matchPredictions.predictions;
  const predictions = predictionData.predictions;

  return (
    <section>
      <h2>Prédictions avant-match</h2>

      <p>Statut : {formatPredictionStatus(predictionData.status)}</p>

      {predictionData.message && <p>{predictionData.message}</p>}

      {predictions && (
        <>
          <h3>Prédiction 1X2</h3>
          <p>{predictions.one_x_two.label}</p>
          <p>
            Confiance :{" "}
            {formatConfidenceLevel(predictions.one_x_two.confidence)}
          </p>
          <p>Risque : {formatRiskLevel(predictions.one_x_two.risk)}</p>
          <p>Justification : {predictions.one_x_two.justification}</p>

          <h3>Volume de buts</h3>
          <p>{predictions.goals.label}</p>
          <p>
            Confiance : {formatConfidenceLevel(predictions.goals.confidence)}
          </p>
          <p>Risque : {formatRiskLevel(predictions.goals.risk)}</p>
          <p>Justification : {predictions.goals.justification}</p>

          <h3>BTTS</h3>
          <p>{predictions.btts.label}</p>
          <p>
            Confiance : {formatConfidenceLevel(predictions.btts.confidence)}
          </p>
          <p>Risque : {formatRiskLevel(predictions.btts.risk)}</p>
          <p>Justification : {predictions.btts.justification}</p>
        </>
      )}

      {predictionData.limits && (
        <>
          <h4>Limites des prédictions</h4>
          <ul>
            {cleanTextItems(predictionData.limits).map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </>
      )}

      <p>
        Méthode : {predictionData.method || "Non disponible"} — Source :{" "}
        {matchPredictions.source}
      </p>
    </section>
  );
}

export default MatchPredictionsSection;