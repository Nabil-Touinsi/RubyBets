// Ce composant affiche la sidebar pédagogique et responsable de l’écran Recommandation.

import type { MultiMatchRecommendationResponse } from "../models/rubybets";

type RecommendationSidePanelProps = {
  multiMatchRecommendation: MultiMatchRecommendationResponse | null;
};

// Ce composant affiche une ligne courte dans la carte pédagogique.
function SidePanelItem({ children }: { children: string }) {
  return (
    <p className="rb-reco-side-item">
      <span>✓</span>
      {children}
    </p>
  );
}

// Ce composant regroupe les explications de sélection et le rappel responsable.
function RecommendationSidePanel({
  multiMatchRecommendation,
}: RecommendationSidePanelProps) {
  return (
    <aside className="rb-reco-sidebar">
      <section className="rb-reco-side-card">
        <div className="rb-reco-side-card__header">
          <div>
            <p className="rb-reco-kicker">Pourquoi cette sélection ?</p>
            <h3>Lecture explicable</h3>
          </div>
          <span>ⓘ</span>
        </div>

        <div className="rb-reco-side-list">
          <SidePanelItem>
            Analyse des matchs disponibles à partir des données avant-match.
          </SidePanelItem>
          <SidePanelItem>
            Prise en compte de la confiance, du risque et du contexte disponible.
          </SidePanelItem>
          <SidePanelItem>
            Sélection cohérente, sans garantie de résultat sportif.
          </SidePanelItem>
        </div>

        {multiMatchRecommendation ? (
          <p className="rb-reco-side-note">
            {multiMatchRecommendation.selection_logic.description}
          </p>
        ) : (
          <p className="rb-reco-side-note">
            Lancez une génération pour afficher une lecture synthétique de la
            sélection proposée.
          </p>
        )}
      </section>

      <section className="rb-reco-side-card rb-reco-side-card--responsible">
        <div className="rb-reco-side-card__header">
          <div>
            <p className="rb-reco-kicker">Rappel responsable</p>
            <h3>Aide à la décision</h3>
          </div>
          <span>◇</span>
        </div>

        <p>
          RubyBets structure une lecture analytique avant-match. L’application ne
          permet pas de parier, ne gère aucune mise et ne promet aucun gain.
        </p>

        <strong>Le contrôle reste à l’utilisateur.</strong>
      </section>
    </aside>
  );
}

export default RecommendationSidePanel;

// Schéma de communication du fichier :
// RecommendationSidePanel.tsx
// ├── reçoit multiMatchRecommendation depuis RecommendationScreen.tsx
// ├── affiche la logique de sélection si elle existe
// ├── affiche le rappel responsable de l’écran
// └── ne modifie ni backend, ni API, ni logique métier