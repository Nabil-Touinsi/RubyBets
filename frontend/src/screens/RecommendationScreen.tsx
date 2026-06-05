// Ce fichier affiche l’écran Recommandation multi-matchs avec hero décoratif, générateur et sidebar responsable.

import type { MultiMatchRecommendationResponse } from "../models/rubybets";
import MultiMatchRecommendationSection from "../components/MultiMatchRecommendationSection";
import RecommendationHeroVisual from "../components/RecommendationHeroVisual";
import RecommendationSidePanel from "../components/RecommendationSidePanel";

type RecommendationScreenProps = {
  recommendationMatchCount: number;
  recommendationRiskLevel: "low" | "medium" | "high";
  multiMatchRecommendation: MultiMatchRecommendationResponse | null;
  multiMatchStatus: string;
  onChangeMatchCount: (matchCount: number) => void;
  onChangeRiskLevel: (riskLevel: "low" | "medium" | "high") => void;
  onGenerateRecommendation: () => void;
};

// Ce composant structure l’écran Recommandation sans modifier les appels existants.
function RecommendationScreen({
  recommendationMatchCount,
  recommendationRiskLevel,
  multiMatchRecommendation,
  multiMatchStatus,
  onChangeMatchCount,
  onChangeRiskLevel,
  onGenerateRecommendation,
}: RecommendationScreenProps) {
  return (
    <div className="rb-recommendation-screen rb-recommendation-screen--mockup">
      <section className="rb-reco-hero">
        <div className="rb-reco-hero__copy">
          <p className="rb-reco-kicker">Sélection intelligente</p>
          <h2>Générateur de sélection</h2>
          <p>
            Construisez une recommandation analytique à partir des matchs
            disponibles, du niveau de risque choisi et des données avant-match.
          </p>
        </div>

        <RecommendationHeroVisual />
      </section>

      <div className="rb-reco-layout" role="main">
        <div className="rb-reco-main">
          <MultiMatchRecommendationSection
            recommendationMatchCount={recommendationMatchCount}
            recommendationRiskLevel={recommendationRiskLevel}
            multiMatchRecommendation={multiMatchRecommendation}
            onChangeMatchCount={onChangeMatchCount}
            onChangeRiskLevel={onChangeRiskLevel}
            onGenerateRecommendation={onGenerateRecommendation}
            multiMatchStatus={multiMatchStatus}
          />
        </div>

        <RecommendationSidePanel
          multiMatchRecommendation={multiMatchRecommendation}
        />
      </div>

      <p className="rb-reco-footer-note">
        Outil d’aide à la décision. Les recommandations proposées ne constituent
        pas un conseil d’investissement ou un pari.
      </p>
    </div>
  );
}

export default RecommendationScreen;

// Schéma de communication du fichier :
// RecommendationScreen.tsx
// ├── reçoit les paramètres et résultats depuis App.tsx
// ├── utilise MultiMatchRecommendationSection.tsx pour le générateur et les résultats
// ├── utilise RecommendationHeroVisual.tsx pour le décor haut de page
// └──  utilise RecommendationSidePanel.tsx pour la pédagogie et le rappel responsable
