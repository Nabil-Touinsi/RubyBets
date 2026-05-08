// Ce composant affiche le générateur de recommandation multi-matchs de RubyBets.
import type { MultiMatchRecommendationResponse } from "../models/rubybets";
import {
  cleanTextItems,
  formatConfidenceLevel,
  formatDateTime,
  formatRiskLevel,
} from "../helpers/displayText";
import DataFreshnessBlock from "./DataFreshnessBlock";

type RiskLevel = "low" | "medium" | "high";

type MultiMatchRecommendationSectionProps = {
  recommendationMatchCount: number;
  recommendationRiskLevel: RiskLevel;
  multiMatchRecommendation: MultiMatchRecommendationResponse | null;
  multiMatchStatus: string;
  onChangeMatchCount: (count: number) => void;
  onChangeRiskLevel: (riskLevel: RiskLevel) => void;
  onGenerateRecommendation: () => void;
};

// Ce composant permet de paramétrer, générer et afficher une recommandation multi-matchs explicable.
function MultiMatchRecommendationSection({
  recommendationMatchCount,
  recommendationRiskLevel,
  multiMatchRecommendation,
  multiMatchStatus,
  onChangeMatchCount,
  onChangeRiskLevel,
  onGenerateRecommendation,
}: MultiMatchRecommendationSectionProps) {
  const isGenerating = multiMatchStatus.includes("Génération");

  return (
    <section className="rb-recommendation-section">
      <div className="rb-section-header">
        <p className="rb-eyebrow">Aide à la décision</p>
        <h2>Recommandation multi-matchs</h2>
        <p className="rb-section-intro">
          Cette sélection est générée à partir des matchs disponibles, des
          prédictions calculées et du niveau de risque choisi.
        </p>
      </div>

      <div className="rb-recommendation-controls">
        <div className="rb-control-group">
          <label htmlFor="match-count">Nombre de matchs</label>
          <select
            id="match-count"
            value={recommendationMatchCount}
            onChange={(event) => onChangeMatchCount(Number(event.target.value))}
            disabled={isGenerating}
          >
            <option value={1}>1 match</option>
            <option value={2}>2 matchs</option>
            <option value={3}>3 matchs</option>
            <option value={4}>4 matchs</option>
            <option value={5}>5 matchs</option>
          </select>
        </div>

        <div className="rb-control-group">
          <label htmlFor="risk-level">Niveau de risque</label>
          <select
            id="risk-level"
            value={recommendationRiskLevel}
            onChange={(event) =>
              onChangeRiskLevel(event.target.value as RiskLevel)
            }
            disabled={isGenerating}
          >
            <option value="low">Faible</option>
            <option value="medium">Moyen</option>
            <option value="high">Élevé</option>
          </select>
        </div>

        <div className="rb-recommendation-actions">
          <button
            type="button"
            onClick={onGenerateRecommendation}
            disabled={isGenerating}
          >
            {isGenerating ? "Génération en cours..." : "Générer la recommandation"}
          </button>

          <p className="rb-status-pill" role="status">
            {multiMatchStatus}
          </p>
        </div>
      </div>

      {multiMatchRecommendation &&
        multiMatchRecommendation.recommendations.length === 0 && (
          <div className="rb-empty-state">
            <h3>Aucune recommandation disponible</h3>
            <p>
              Aucun match ne correspond aux paramètres sélectionnés. Vous pouvez
              choisir un niveau de risque différent ou réduire le nombre de
              matchs demandés.
            </p>
          </div>
        )}

      {multiMatchRecommendation &&
        multiMatchRecommendation.recommendations.length > 0 && (
          <div className="rb-recommendation-results">
            <div className="rb-results-summary">
              <div>
                <p className="rb-eyebrow">Sélection générée</p>
                <h3>Sélection recommandée</h3>
              </div>

              <p>
                Compétition :{" "}
                <strong>{multiMatchRecommendation.request.competition_code}</strong>{" "}
                — Risque :{" "}
                <strong>
                  {formatRiskLevel(multiMatchRecommendation.request.risk_level)}
                </strong>{" "}
                — Matchs :{" "}
                <strong>{multiMatchRecommendation.selected_count}</strong>
              </p>
            </div>

            <div className="rb-recommendation-grid">
              {multiMatchRecommendation.recommendations.map((item) => (
                <article className="rb-recommendation-card" key={item.match.id}>
                  <div className="rb-card-topline">
                    <span>{item.match.competition.name}</span>
                    <span>Journée {item.match.matchday}</span>
                  </div>

                  <h4>
                    {item.match.home_team.name} vs {item.match.away_team.name}
                  </h4>

                  <p className="rb-match-date">
                    {formatDateTime(item.match.utc_date)}
                  </p>

                  <div className="rb-prediction-highlight">
                    <span>Recommandation</span>
                    <strong>{item.selected_prediction.label}</strong>
                  </div>

                  <div className="rb-metrics-row">
                    <p>
                      Marché
                      <strong>{item.selected_prediction.market}</strong>
                    </p>
                    <p>
                      Confiance
                      <strong>
                        {formatConfidenceLevel(
                          item.selected_prediction.confidence
                        )}
                      </strong>
                    </p>
                    <p>
                      Risque
                      <strong>
                        {formatRiskLevel(item.selected_prediction.risk)}
                      </strong>
                    </p>
                  </div>

                  <p className="rb-selection-score">
                    Score de sélection : <strong>{item.selection_score}</strong>
                  </p>

                  <p className="rb-justification">
                    {item.selected_prediction.justification}
                  </p>
                </article>
              ))}
            </div>

            <div className="rb-analysis-note">
              <h4>Logique de sélection</h4>
              <p>{multiMatchRecommendation.selection_logic.description}</p>
            </div>

            <div className="rb-analysis-note">
              <h4>Limites</h4>
              <ul>
                {cleanTextItems(multiMatchRecommendation.limits).map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </div>

            <p className="rb-technical-note">
              Méthode : {multiMatchRecommendation.method} — Source :{" "}
              {multiMatchRecommendation.source}
            </p>

            <DataFreshnessBlock
              title="Fraîcheur des données utilisées pour la recommandation"
              dataFreshness={multiMatchRecommendation.data_freshness}
            />
          </div>
        )}
    </section>
  );
}

export default MultiMatchRecommendationSection;

// Schéma de communication du fichier :
// MultiMatchRecommendationSection.tsx
// ├── reçoit la recommandation multi-matchs depuis App.tsx
// ├── reçoit le statut de génération depuis App.tsx
// ├── utilise displayText.ts pour formater risque, confiance et dates
// ├── utilise DataFreshnessBlock.tsx pour afficher la fraîcheur des données
// └── affiche les sélections recommandées générées par le backend