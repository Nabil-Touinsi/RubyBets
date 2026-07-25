// Ce fichier compose l’écran Sélection guidée avec son hero, son générateur et ses explications responsables.

import type { Match, V19SelectionResponse } from "../models/rubybets";
import MultiMatchRecommendationSection from "../components/MultiMatchRecommendationSection";
import RecommendationHeroVisual from "../components/RecommendationHeroVisual";
import RecommendationSidePanel from "../components/RecommendationSidePanel";
import "../styles/RecommendationScreen.css";

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

// Ce composant organise l’écran complet sans modifier la logique métier de sélection.
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
    <div className="rb-selection-screen">
      <section className="rb-selection-hero" aria-labelledby="selection-title">
        <div className="rb-selection-hero__copy">
          <p className="rb-selection-eyebrow">Sélection guidée</p>
          <h1 id="selection-title">Créez votre sélection</h1>
          <p className="rb-selection-hero__intro">
            Choisissez le nombre de matchs et le style souhaité. RubyBets vous
            aide à composer une sélection claire, prudente et facile à lire.
          </p>
        </div>

        <RecommendationHeroVisual />
      </section>

      <div className="rb-selection-layout">
        <main className="rb-selection-main">
          <MultiMatchRecommendationSection
            matches={matches}
            activeCompetitionLabel={activeCompetitionLabel}
            recommendationMatchCount={recommendationMatchCount}
            recommendationSelectionProfile={recommendationSelectionProfile}
            multiMatchRecommendation={multiMatchRecommendation}
            multiMatchStatus={multiMatchStatus}
            onChangeMatchCount={onChangeMatchCount}
            onChangeSelectionProfile={onChangeSelectionProfile}
            onGenerateRecommendation={onGenerateRecommendation}
          />
        </main>

        <RecommendationSidePanel
          multiMatchRecommendation={multiMatchRecommendation}
        />
      </div>
    </div>
  );
}

export default RecommendationScreen;

// Schéma de communication du fichier :
// App.tsx -> RecommendationScreen.tsx
// RecommendationScreen.tsx -> MultiMatchRecommendationSection.tsx
// RecommendationScreen.tsx -> RecommendationHeroVisual.tsx
// RecommendationScreen.tsx -> RecommendationSidePanel.tsx
// RecommendationScreen.tsx -> RecommendationScreen.css
