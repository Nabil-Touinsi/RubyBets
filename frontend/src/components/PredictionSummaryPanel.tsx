// Ce composant affiche la synthèse globale des prédictions avec un baromètre visuel.

import type { MatchPredictionsResponse, PredictionItem } from "../models/rubybets";
import { formatConfidenceLevel, formatRiskLevel } from "../helpers/displayText";

type PredictionSummaryPanelProps = {
  matchPredictions: MatchPredictionsResponse | null;
};

// Cette fonction transforme un niveau de confiance en score indicatif.
function getConfidenceScore(confidence: string) {
  const scores: Record<string, number> = {
    high: 72,
    medium: 58,
    low: 42,
  };

  return scores[confidence] ?? 50;
}

// Cette fonction ajuste légèrement le score selon le niveau de risque.
function getRiskAdjustment(risk: string) {
  const adjustments: Record<string, number> = {
    low: 6,
    medium: 0,
    high: -8,
  };

  return adjustments[risk] ?? 0;
}

// Cette fonction calcule une synthèse visuelle prudente à partir des prédictions disponibles.
function getGlobalScore(predictions: PredictionItem[]) {
  if (predictions.length === 0) {
    return 0;
  }

  const total = predictions.reduce((sum, prediction) => {
    return (
      sum +
      getConfidenceScore(prediction.confidence) +
      getRiskAdjustment(prediction.risk)
    );
  }, 0);

  return Math.max(0, Math.min(100, Math.round(total / predictions.length)));
}

// Cette fonction retourne les prédictions disponibles dans un tableau stable.
function getPredictionItems(matchPredictions: MatchPredictionsResponse | null) {
  const predictions = matchPredictions?.predictions.predictions;

  if (!predictions) {
    return [];
  }

  return [predictions.one_x_two, predictions.goals, predictions.btts];
}

// Cette fonction retourne un libellé responsable pour le niveau global.
function getGlobalLabel(score: number) {
  if (score >= 68) {
    return "Confiance élevée";
  }

  if (score >= 52) {
    return "Confiance modérée";
  }

  if (score > 0) {
    return "Lecture prudente";
  }

  return "Données insuffisantes";
}

// Ce composant affiche le baromètre et les signaux synthétiques de prédiction.
function PredictionSummaryPanel({
  matchPredictions,
}: PredictionSummaryPanelProps) {
  const predictions = getPredictionItems(matchPredictions);
  const globalScore = getGlobalScore(predictions);
  const scoreStyle = {
    "--rb-prediction-score": `${globalScore}%`,
  } as React.CSSProperties;

  const strongestPrediction =
    predictions.find((prediction) => prediction.confidence === "high") ??
    predictions[0];

  return (
    <section className="rb-prediction-summary-card">
      <div className="rb-prediction-summary-card__header">
        <div>
          <p className="rb-prediction-kicker">Synthèse globale</p>
          <h3>Baromètre du match</h3>
        </div>
      </div>

      <div className="rb-prediction-gauge" style={scoreStyle}>
        <div>
          <strong>{globalScore}%</strong>
          <span>{getGlobalLabel(globalScore)}</span>
        </div>
      </div>

      <p className="rb-prediction-summary-text">
        Cette synthèse agrège visuellement les signaux disponibles. Elle sert à
        faciliter la lecture avant-match, sans garantir l’issue sportive.
      </p>

      <div className="rb-prediction-summary-metrics">
        <p>
          <span>Signal principal</span>
          <strong>{strongestPrediction?.label ?? "Non disponible"}</strong>
        </p>

        <p>
          <span>Confiance dominante</span>
          <strong>
            {strongestPrediction
              ? formatConfidenceLevel(strongestPrediction.confidence)
              : "Non disponible"}
          </strong>
        </p>

        <p>
          <span>Risque associé</span>
          <strong>
            {strongestPrediction
              ? formatRiskLevel(strongestPrediction.risk)
              : "Non disponible"}
          </strong>
        </p>
      </div>
    </section>
  );
}

export default PredictionSummaryPanel;

// Schéma de communication du fichier :
// PredictionSummaryPanel.tsx
// ├── reçoit matchPredictions depuis PredictionsScreen.tsx
// ├── calcule un score visuel frontend à partir des prédictions déjà disponibles
// ├── affiche un baromètre indicatif sans modifier le backend
// └── utilise displayText.ts pour formater confiance et risque