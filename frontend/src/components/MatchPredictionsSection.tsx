// Ce composant affiche les prédictions avant-match du match sélectionné dans RubyBets.
import type { MatchPredictionsResponse } from "../models/rubybets";
import {
  cleanTextItems,
  formatConfidenceLevel,
  formatPredictionStatus,
  formatRiskLevel,
} from "../helpers/displayText";
import DataFreshnessBlock from "./DataFreshnessBlock";

type MatchPredictionsSectionProps = {
  matchPredictions: MatchPredictionsResponse;
};

// Cette fonction prépare les trois cartes principales de prédiction affichées dans l'interface.
function buildPredictionCards(
  predictions: MatchPredictionsResponse["predictions"]["predictions"],
) {
  if (!predictions) {
    return [];
  }

  return [
    {
      key: "one_x_two",
      title: "Prédiction 1X2",
      subtitle: "Tendance résultat",
      prediction: predictions.one_x_two,
    },
    {
      key: "goals",
      title: "Volume de buts",
      subtitle: "Lecture offensive",
      prediction: predictions.goals,
    },
    {
      key: "btts",
      title: "BTTS",
      subtitle: "Les deux équipes marquent",
      prediction: predictions.btts,
    },
  ];
}

// Ce composant présente les tendances prédictives, leurs justifications et la fraîcheur des données utilisées.
function MatchPredictionsSection({
  matchPredictions,
}: MatchPredictionsSectionProps) {
  const predictionData = matchPredictions.predictions;
  const predictionCards = buildPredictionCards(predictionData.predictions);

  return (
    <section className="rb-predictions-section">
      <div className="rb-section-header">
        <span className="rb-eyebrow">Scoring explicable</span>
        <h2>Prédictions avant-match</h2>
        <p className="rb-section-intro">
          RubyBets affiche ici les tendances calculées par le moteur d’analyse
          avant-match. Ces résultats sont des indications analytiques, pas des
          certitudes sportives.
        </p>
      </div>

      <div className="rb-predictions-status">
        <span className="rb-status-pill">
          Statut : {formatPredictionStatus(predictionData.status)}
        </span>

        <span className="rb-status-pill">
          Source : {matchPredictions.source || "Non disponible"}
        </span>

        <span className="rb-status-pill">
          Méthode : {predictionData.method || "Non disponible"}
        </span>
      </div>

      {predictionData.message && (
        <div className="rb-empty-state">
          <p>{predictionData.message}</p>
        </div>
      )}

      {predictionCards.length > 0 ? (
        <div className="rb-predictions-grid">
          {predictionCards.map((card) => (
            <article className="rb-prediction-card" key={card.key}>
              <div className="rb-card-topline">
                <div>
                  <span>{card.subtitle}</span>
                  <h3>{card.title}</h3>
                </div>
              </div>

              <div className="rb-prediction-highlight">
                <span>Recommandation analytique</span>
                <strong>{card.prediction.label}</strong>
              </div>

              <div className="rb-metrics-row">
                <p>
                  Confiance
                  <strong>
                    {formatConfidenceLevel(card.prediction.confidence)}
                  </strong>
                </p>

                <p>
                  Risque
                  <strong>{formatRiskLevel(card.prediction.risk)}</strong>
                </p>
              </div>

              <p className="rb-justification">
                {card.prediction.justification}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <div className="rb-empty-state">
          <p>
            Aucune prédiction exploitable n’est disponible pour ce match pour le
            moment.
          </p>
        </div>
      )}

      <div className="rb-analysis-note">
        <h4>Cadre de lecture responsable</h4>
        <p>
          Les prédictions RubyBets servent à structurer l’analyse avant-match.
          Elles ne garantissent aucun résultat et ne déclenchent aucune prise de
          pari réelle.
        </p>
      </div>

      {predictionData.limits && (
        <div className="rb-analysis-note">
          <h4>Limites des prédictions</h4>
          <ul>
            {cleanTextItems(predictionData.limits).map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </div>
      )}

      <DataFreshnessBlock
        title="Fraîcheur des données utilisées pour les prédictions"
        dataFreshness={matchPredictions.data_freshness}
      />
    </section>
  );
}

export default MatchPredictionsSection;

// Schéma de communication du fichier :
// MatchPredictionsSection.tsx
// ├── reçoit les prédictions depuis App.tsx
// ├── utilise displayText.ts pour formater confiance, risque et statuts
// ├── utilise DataFreshnessBlock.tsx pour afficher la fraîcheur des données
// └── affiche les tendances 1X2, buts et BTTS fournies par le backend