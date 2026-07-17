// Ce fichier affiche l’écran Sélection multi-matchs V19 avec son hero, son générateur et sa sidebar responsable.

import type {
  Match,
  V19SelectionResponse,
} from "../models/rubybets";
import MultiMatchRecommendationSection from "../components/MultiMatchRecommendationSection";
import RecommendationHeroVisual from "../components/RecommendationHeroVisual";
import RecommendationSidePanel from "../components/RecommendationSidePanel";

type SelectionProfileLevel = "low" | "medium" | "high";

type RecommendationScreenProps = {
  matches: Match[];
  activeCompetitionLabel: string;
  recommendationMatchCount: number;
  recommendationSelectionProfile: SelectionProfileLevel;
  multiMatchRecommendation: V19SelectionResponse | null;
  multiMatchStatus: string;
  onChangeMatchCount: (matchCount: number) => void;
  onChangeSelectionProfile: (profile: SelectionProfileLevel) => void;
  onGenerateRecommendation: () => void;
};

// Ce composant structure l’écran Sélection V19 sans modifier son design Obsidian Teal.
function RecommendationScreen({
  matches,
  activeCompetitionLabel,
  recommendationMatchCount,
  recommendationSelectionProfile,
  multiMatchRecommendation,
  multiMatchStatus,
  onChangeMatchCount,
  onChangeSelectionProfile,
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
            disponibles, du profil de sélectivité choisi et des décisions V19.
          </p>
        </div>

        <RecommendationHeroVisual />
      </section>

      <div className="rb-reco-layout" role="main">
        <div className="rb-reco-main">
          <MultiMatchRecommendationSection
            matches={matches}
            activeCompetitionLabel={activeCompetitionLabel}
            recommendationMatchCount={recommendationMatchCount}
            recommendationSelectionProfile={recommendationSelectionProfile}
            multiMatchRecommendation={multiMatchRecommendation}
            onChangeMatchCount={onChangeMatchCount}
            onChangeSelectionProfile={onChangeSelectionProfile}
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
// ├── reçoit les matchs, la compétition active, les paramètres et les résultats V19 depuis App.tsx
// ├── utilise MultiMatchRecommendationSection.tsx pour le générateur et les résultats
// ├── utilise RecommendationHeroVisual.tsx pour conserver le décor haut de page
// └── utilise RecommendationSidePanel.tsx pour l’explication publique et le rappel responsable