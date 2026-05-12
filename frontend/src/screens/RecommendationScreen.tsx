// Ce fichier affiche l’écran Recommandation multi-matchs de RubyBets avec une structure dédiée proche de la maquette MVP.

import type { MultiMatchRecommendationResponse } from "../models/rubybets";
import MultiMatchRecommendationSection from "../components/MultiMatchRecommendationSection";

type RecommendationScreenProps = {
  recommendationMatchCount: number;
  recommendationRiskLevel: "low" | "medium" | "high";
  multiMatchRecommendation: MultiMatchRecommendationResponse | null;
  multiMatchStatus: string;
  onChangeMatchCount: (matchCount: number) => void;
  onChangeRiskLevel: (riskLevel: "low" | "medium" | "high") => void;
  onGenerateRecommendation: () => void;
};

// Ce composant structure l’écran de recommandation avec paramétrage, résultat et rappel responsable.
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
    <div className="rb-recommendation-screen">
      <section className="rb-page-hero">
        <div>
          <p className="rb-eyebrow">Recommandation multi-matchs</p>
          <h2>Construire une sélection analytique</h2>
          <p>
            Choisissez un nombre de matchs et un niveau de risque pour générer
            une recommandation fondée sur les données disponibles et le scoring
            explicable RubyBets.
          </p>
        </div>

        <aside className="rb-page-hero__aside">
          <p className="rb-eyebrow">Important</p>
          <h3>Pas de pari réel</h3>
          <p>
            La recommandation aide à structurer une lecture avant-match. Elle ne
            correspond pas à une prise de pari et ne garantit aucun résultat.
          </p>
        </aside>
      </section>

      <section className="rb-recommendation-layout">
        <div className="rb-recommendation-main">
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

        <aside className="rb-recommendation-aside">
          <article>
            <p className="rb-eyebrow">Paramètres</p>
            <h3>Nombre + risque</h3>
            <p>
              Le moteur sélectionne les matchs selon le nombre demandé et le
              profil de risque choisi : faible, moyen ou élevé.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Méthode V1</p>
            <h3>Scoring explicable</h3>
            <p>
              La sélection repose sur une logique rules_based_multimatch_selection_v1
              alimentée par les prédictions du scoring V1.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Formulation</p>
            <h3>Recommandation analytique</h3>
            <p>
              On évite de présenter cette zone comme un ticket bookmaker. Le bon
              terme à défendre est : recommandation multi-matchs.
            </p>
          </article>
        </aside>
      </section>
    </div>
  );
}

export default RecommendationScreen;

// Schéma de communication du fichier :
// RecommendationScreen.tsx
// ├── reçoit les paramètres et résultats depuis App.tsx
// ├── utilise MultiMatchRecommendationSection.tsx pour le bloc métier existant
// ├── ajoute une colonne de lecture responsable
// └── renvoie les changements de paramètres et la génération vers App.tsx
