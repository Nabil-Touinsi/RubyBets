// Ce composant explique simplement la sélection et rappelle le cadre responsable de RubyBets.

import { Check, CircleHelp, ShieldCheck } from "lucide-react";
import type { V19SelectionResponse } from "../models/rubybets";

type RecommendationSidePanelProps = {
  multiMatchRecommendation: V19SelectionResponse | null;
};

// Ce composant affiche une raison courte et compréhensible.
function ExplanationItem({ children }: { children: string }) {
  return (
    <li className="rb-selection-side-list__item">
      <span aria-hidden="true">
        <Check size={16} strokeWidth={2.4} />
      </span>
      <p>{children}</p>
    </li>
  );
}

// Cette fonction construit un résumé simple à partir des compteurs publics reçus.
function getSelectionSummary(
  multiMatchRecommendation: V19SelectionResponse | null,
) {
  if (!multiMatchRecommendation) {
    return "Lancez la sélection pour afficher une proposition adaptée au style choisi.";
  }

  const selectedCount = multiMatchRecommendation.selected_count;
  const evaluatedCount = multiMatchRecommendation.evaluated_count;

  if (selectedCount === 0) {
    return "Aucun match n’a été retenu pour le moment. Les rencontres jugées trop incertaines ont été laissées de côté.";
  }

  return `${selectedCount} match${selectedCount > 1 ? "s ont" : " a"} été retenu${
    selectedCount > 1 ? "s" : ""
  } parmi ${evaluatedCount} rencontres examinées. Les choix les moins lisibles ont été laissés de côté.`;
}

// Ce composant regroupe la lecture simple et le rappel responsable.
function RecommendationSidePanel({
  multiMatchRecommendation,
}: RecommendationSidePanelProps) {
  return (
    <aside className="rb-selection-sidebar" aria-label="Informations sur la sélection">
      <section className="rb-selection-side-card rb-selection-side-card--explain">
        <div className="rb-selection-side-card__heading">
          <span className="rb-selection-side-card__icon" aria-hidden="true">
            <CircleHelp size={18} />
          </span>
          <div>
            <p className="rb-selection-side-kicker">Pourquoi cette sélection ?</p>
            <h2>Lecture simple</h2>
          </div>
        </div>

        <ul className="rb-selection-side-list">
          <ExplanationItem>
            Les choix les plus cohérents sont mis en avant.
          </ExplanationItem>
          <ExplanationItem>
            Le style choisi guide le niveau de prudence.
          </ExplanationItem>
          <ExplanationItem>
            Les rencontres trop incertaines ne sont pas retenues.
          </ExplanationItem>
        </ul>

        <p className="rb-selection-side-summary" aria-live="polite">
          {getSelectionSummary(multiMatchRecommendation)}
        </p>
      </section>

      <section className="rb-selection-side-card rb-selection-side-card--responsible">
        <div className="rb-selection-side-card__heading">
          <span className="rb-selection-side-card__icon" aria-hidden="true">
            <ShieldCheck size={18} />
          </span>
          <div>
            <p className="rb-selection-side-kicker">Rappel responsable</p>
            <h2>Aide à la décision</h2>
          </div>
        </div>

        <p className="rb-selection-responsible-copy">
          RubyBets accompagne votre lecture avant-match. L’application ne permet
          pas de parier et ne promet aucun résultat.
        </p>

        <div className="rb-selection-responsible-callout">
          <ShieldCheck size={20} aria-hidden="true" />
          <strong>Le choix final vous appartient</strong>
        </div>
      </section>
    </aside>
  );
}

export default RecommendationSidePanel;

// Schéma de communication du fichier :
// RecommendationScreen.tsx -> RecommendationSidePanel.tsx
// RecommendationSidePanel.tsx <- V19SelectionResponse
// RecommendationSidePanel.tsx -> aucune route API directe
