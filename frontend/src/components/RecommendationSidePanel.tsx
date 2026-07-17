// Ce composant affiche la sidebar pédagogique et responsable de l’écran Sélection V19.

import type { V19SelectionResponse } from "../models/rubybets";

type RecommendationSidePanelProps = {
  multiMatchRecommendation: V19SelectionResponse | null;
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

// Cette fonction construit la note publique affichée après une génération V19.
function getSelectionNote(
  multiMatchRecommendation: V19SelectionResponse | null,
) {
  if (!multiMatchRecommendation) {
    return (
      "Lancez une génération pour afficher la synthèse publique de la " +
      "sélection proposée."
    );
  }

  return `${multiMatchRecommendation.selection_explanation.headline}. ${multiMatchRecommendation.selection_explanation.summary}`;
}

// Ce composant regroupe l’explication publique V19 et le rappel responsable.
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
            Analyse des décisions officielles V19 pour les matchs disponibles.
          </SidePanelItem>
          <SidePanelItem>
            Application du profil de sélectivité choisi sans classement par score brut.
          </SidePanelItem>
          <SidePanelItem>
            Exclusion systématique des abstentions et des décisions incompatibles.
          </SidePanelItem>
        </div>

        <p className="rb-reco-side-note">
          {getSelectionNote(multiMatchRecommendation)}
        </p>

        {multiMatchRecommendation ? (
          <p className="rb-reco-side-note">
            {multiMatchRecommendation.profile.description}
          </p>
        ) : null}
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
// ├── reçoit la réponse publique V19 depuis RecommendationScreen.tsx
// ├── affiche selection_explanation et la description du profil
// ├── explique l’exclusion des abstentions sans exposer les détails internes
// └── conserve le rappel responsable sans modifier l’API ni la logique métier
