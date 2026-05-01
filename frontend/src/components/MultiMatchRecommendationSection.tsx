// Ce composant affiche le générateur de recommandation multi-matchs de RubyBets.

import type { MultiMatchRecommendationResponse } from "../models/rubybets";
import {
  cleanTextItems,
  formatConfidenceLevel,
  formatRiskLevel,
} from "../helpers/displayText";

type RiskLevel = "low" | "medium" | "high";

type MultiMatchRecommendationSectionProps = {
  recommendationMatchCount: number;
  recommendationRiskLevel: RiskLevel;
  multiMatchRecommendation: MultiMatchRecommendationResponse | null;
  onChangeMatchCount: (count: number) => void;
  onChangeRiskLevel: (riskLevel: RiskLevel) => void;
  onGenerateRecommendation: () => void;
};

function MultiMatchRecommendationSection({
  recommendationMatchCount,
  recommendationRiskLevel,
  multiMatchRecommendation,
  onChangeMatchCount,
  onChangeRiskLevel,
  onGenerateRecommendation,
}: MultiMatchRecommendationSectionProps) {
  return (
    <section>
      <h2>Recommandation multi-matchs</h2>

      <p>
        Cette sélection est générée à partir des matchs disponibles, des
        prédictions calculées et du niveau de risque choisi.
      </p>

      <label htmlFor="match-count">Nombre de matchs : </label>
      <select
        id="match-count"
        value={recommendationMatchCount}
        onChange={(event) => onChangeMatchCount(Number(event.target.value))}
      >
        <option value={1}>1</option>
        <option value={2}>2</option>
        <option value={3}>3</option>
        <option value={4}>4</option>
        <option value={5}>5</option>
      </select>

      <br />

      <label htmlFor="risk-level">Niveau de risque : </label>
      <select
        id="risk-level"
        value={recommendationRiskLevel}
        onChange={(event) => onChangeRiskLevel(event.target.value as RiskLevel)}
      >
        <option value="low">Faible</option>
        <option value="medium">Moyen</option>
        <option value="high">Élevé</option>
      </select>

      <br />

      <button type="button" onClick={onGenerateRecommendation}>
        Générer la recommandation
      </button>

      {multiMatchRecommendation && (
        <div>
          <h3>Sélection recommandée</h3>

          <p>
            Compétition : {multiMatchRecommendation.request.competition_code} —
            Niveau de risque :{" "}
            {formatRiskLevel(multiMatchRecommendation.request.risk_level)} —
            Matchs sélectionnés : {multiMatchRecommendation.selected_count}
          </p>

          {multiMatchRecommendation.recommendations.map((item) => (
            <article key={item.match.id}>
              <h4>
                {item.match.home_team.name} vs {item.match.away_team.name}
              </h4>

              <p>
                {item.match.competition.name} — Journée {item.match.matchday} —{" "}
                {new Date(item.match.utc_date).toLocaleString("fr-FR")}
              </p>

              <p>
                Recommandation :{" "}
                <strong>{item.selected_prediction.label}</strong>
              </p>

              <p>Marché analysé : {item.selected_prediction.market}</p>

              <p>
                Confiance :{" "}
                {formatConfidenceLevel(item.selected_prediction.confidence)}
              </p>

              <p>Risque : {formatRiskLevel(item.selected_prediction.risk)}</p>

              <p>Score de sélection : {item.selection_score}</p>

              <p>Justification : {item.selected_prediction.justification}</p>
            </article>
          ))}

          <h4>Logique de sélection</h4>
          <p>{multiMatchRecommendation.selection_logic.description}</p>

          <h4>Limites</h4>
          <ul>
            {cleanTextItems(multiMatchRecommendation.limits).map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>

          <p>
            Méthode : {multiMatchRecommendation.method} — Source :{" "}
            {multiMatchRecommendation.source}
          </p>
        </div>
      )}
    </section>
  );
}

export default MultiMatchRecommendationSection;