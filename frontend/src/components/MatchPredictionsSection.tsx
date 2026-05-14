// Ce composant affiche les prédictions avant-match en cartes compactes avec confiance, risque et lecture globale.

import type {
  MatchPredictionsResponse,
  PredictionItem,
} from "../models/rubybets";
import {
  cleanTextItems,
  formatConfidenceLevel,
  formatDateTime,
  formatPredictionStatus,
  formatRiskLevel,
} from "../helpers/displayText";

type MatchPredictionsSectionProps = {
  matchPredictions: MatchPredictionsResponse;
};

type PredictionCardConfig = {
  key: string;
  title: string;
  subtitle: string;
  prediction: PredictionItem;
};

// Cette fonction prépare les trois cartes principales de prédiction.
function buildPredictionCards(
  predictions: MatchPredictionsResponse["predictions"]["predictions"],
): PredictionCardConfig[] {
  if (!predictions) {
    return [];
  }

  return [
    {
      key: "one_x_two",
      title: "1X2",
      subtitle: "Tendance résultat",
      prediction: predictions.one_x_two,
    },
    {
      key: "goals",
      title: "Nombre de buts",
      subtitle: "Volume offensif",
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

// Cette fonction transforme la confiance en pourcentage visuel indicatif.
function getConfidencePercent(confidence: string) {
  const values: Record<string, number> = {
    high: 68,
    medium: 58,
    low: 44,
  };

  return values[confidence] ?? 50;
}

// Cette fonction retourne les limites affichées dans la lecture globale.
function getPredictionLimits(matchPredictions: MatchPredictionsResponse) {
  return cleanTextItems(matchPredictions.predictions.limits ?? []).slice(0, 3);
}

// Ce composant affiche une carte de prédiction individuelle.
function PredictionCard({ card }: { card: PredictionCardConfig }) {
  const confidencePercent = getConfidencePercent(card.prediction.confidence);
  const scoreStyle = {
    "--rb-card-confidence": `${confidencePercent}%`,
  } as React.CSSProperties;

  return (
    <article className="rb-prediction-main-card">
      <div className="rb-prediction-main-card__header">
        <div>
          <h3>{card.title}</h3>
          <span>{card.subtitle}</span>
        </div>
        <span>ⓘ</span>
      </div>

      <div className="rb-prediction-main-card__highlight">
        <span>Notre prédiction</span>
        <strong>{card.prediction.label}</strong>
      </div>

      <div className="rb-prediction-card-gauge" style={scoreStyle}>
        <div>
          <strong>{confidencePercent}%</strong>
          <span>Confiance</span>
        </div>
      </div>

      <p>{card.prediction.justification}</p>

      <div className="rb-prediction-card-tags">
        <span>Confiance {formatConfidenceLevel(card.prediction.confidence)}</span>
        <span>Risque {formatRiskLevel(card.prediction.risk)}</span>
      </div>
    </article>
  );
}

// Ce composant affiche la lecture globale sous les trois cartes de prédiction.
function GlobalReading({ matchPredictions }: { matchPredictions: MatchPredictionsResponse }) {
  const predictions = matchPredictions.predictions.predictions;
  const limits = getPredictionLimits(matchPredictions);

  return (
    <section className="rb-prediction-global-reading">
      <div className="rb-prediction-global-reading__icon">▣</div>

      <div>
        <p className="rb-prediction-kicker">Lecture globale de la rencontre</p>
        <h3>Synthèse des signaux disponibles</h3>

        <p>
          Les prédictions RubyBets regroupent les tendances principales du match
          à partir des données disponibles. La lecture doit rester prudente et
          être comprise comme une aide à l’analyse avant-match.
        </p>

        <div className="rb-prediction-global-tags">
          <span>
            1X2 :{" "}
            <strong>{predictions?.one_x_two.label ?? "Non disponible"}</strong>
          </span>
          <span>
            Buts :{" "}
            <strong>{predictions?.goals.label ?? "Non disponible"}</strong>
          </span>
          <span>
            BTTS :{" "}
            <strong>{predictions?.btts.label ?? "Non disponible"}</strong>
          </span>
          <span>
            Statut :{" "}
            <strong>{formatPredictionStatus(matchPredictions.predictions.status)}</strong>
          </span>
        </div>

        {limits.length > 0 ? (
          <ul className="rb-prediction-limit-list">
            {limits.map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

// Ce composant présente les prédictions principales et leur lecture responsable.
function MatchPredictionsSection({
  matchPredictions,
}: MatchPredictionsSectionProps) {
  const predictionData = matchPredictions.predictions;
  const predictionCards = buildPredictionCards(predictionData.predictions);

  return (
    <section className="rb-prediction-main-section">
      <div className="rb-prediction-section-header">
        <div>
          <p className="rb-prediction-kicker">Prédictions pour ce match</p>
          <h3>Marchés MVP analysés</h3>
          <p>
            Basées sur les modèles statistiques, la dynamique des équipes et le
            contexte disponible du match.
          </p>
        </div>

        <span className="rb-prediction-soft-badge">
          {formatPredictionStatus(predictionData.status)}
        </span>
      </div>

      {predictionData.message ? (
        <div className="rb-prediction-message">
          <p>{predictionData.message}</p>
        </div>
      ) : null}

      {predictionCards.length > 0 ? (
        <div className="rb-prediction-card-grid">
          {predictionCards.map((card) => (
            <PredictionCard card={card} key={card.key} />
          ))}
        </div>
      ) : (
        <div className="rb-prediction-message">
          <p>
            Aucune prédiction exploitable n’est disponible pour ce match pour le
            moment.
          </p>
        </div>
      )}

      <GlobalReading matchPredictions={matchPredictions} />

      <div className="rb-prediction-meta-strip">
        <span>
          Source <strong>{matchPredictions.source || "Non disponible"}</strong>
        </span>
        <span>
          Méthode <strong>{predictionData.method || "Non disponible"}</strong>
        </span>
        <span>
          Match{" "}
          <strong>
            {formatDateTime(matchPredictions.data_freshness.match_last_updated)}
          </strong>
        </span>
      </div>
    </section>
  );
}

export default MatchPredictionsSection;

// Schéma de communication du fichier :
// MatchPredictionsSection.tsx
// ├── reçoit matchPredictions depuis PredictionsScreen.tsx
// ├── affiche les trois cartes MVP : 1X2, buts et BTTS
// ├── affiche une lecture globale sans ajouter de nouvelle donnée backend
// └── utilise displayText.ts pour formater confiance, risque, statut et dates