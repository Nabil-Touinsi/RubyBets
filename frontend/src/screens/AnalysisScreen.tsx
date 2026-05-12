// Ce fichier affiche l’écran Analyse pré-match de RubyBets avec une structure dédiée proche de la maquette MVP.

import type { MatchAnalysisResponse } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import MatchAnalysisSection from "../components/MatchAnalysisSection";

type AnalysisScreenProps = {
  matchAnalysis: MatchAnalysisResponse | null;
  matchAnalysisStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

// Ce composant structure l’analyse pré-match avec une zone principale et une colonne d’aide à la lecture.
function AnalysisScreen({
  matchAnalysis,
  matchAnalysisStatus,
  onNavigate,
}: AnalysisScreenProps) {
  return (
    <div className="rb-analysis-screen">
      <section className="rb-page-hero">
        <div>
          <p className="rb-eyebrow">Analyse pré-match</p>
          <h2>Comprendre les facteurs qui influencent la rencontre</h2>
          <p>
            Cette page présente une lecture structurée du match avant les
            prédictions : faits observés, dynamique, contexte et interprétation
            analytique.
          </p>
        </div>

        <aside className="rb-page-hero__aside">
          <p className="rb-eyebrow">Lecture</p>
          <h3>Faits + interprétation</h3>
          <p>
            L’objectif est de distinguer les données observées de la lecture
            proposée par RubyBets.
          </p>
        </aside>
      </section>

      <section className="rb-analysis-layout">
        <div className="rb-analysis-main">
          {matchAnalysis ? (
            <MatchAnalysisSection matchAnalysis={matchAnalysis} />
          ) : (
            <article className="rb-empty-state">
              <p className="rb-eyebrow">Analyse</p>
              <h3>Analyse pré-match</h3>
              <p>{matchAnalysisStatus}</p>
            </article>
          )}
        </div>

        <aside className="rb-analysis-aside">
          <article>
            <p className="rb-eyebrow">Méthode</p>
            <h3>Analyse explicable</h3>
            <p>
              La V1 repose sur une lecture par règles métier et données réelles,
              sans modèle Machine Learning entraîné.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Étape suivante</p>
            <h3>Prédictions</h3>
            <p>
              Après l’analyse, consultez les tendances 1X2, volume de buts et
              BTTS avec confiance, risque et justification.
            </p>
            <button type="button" onClick={() => onNavigate("predictions")}>
              Voir les prédictions
            </button>
          </article>

          <article>
            <p className="rb-eyebrow">Responsable</p>
            <h3>Aucune certitude</h3>
            <p>
              L’analyse aide à structurer une décision avant-match, mais elle ne
              garantit jamais le résultat final d’une rencontre.
            </p>
          </article>
        </aside>
      </section>
    </div>
  );
}

export default AnalysisScreen;

// Schéma de communication du fichier :
// AnalysisScreen.tsx
// ├── reçoit l’analyse pré-match depuis App.tsx
// ├── utilise MatchAnalysisSection.tsx pour afficher le contenu existant
// ├── ajoute une colonne d’aide à la lecture responsable
// └── déclenche la navigation vers PredictionsScreen via onNavigate
