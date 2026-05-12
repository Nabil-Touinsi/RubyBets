// Ce fichier affiche l’écran Prédictions de RubyBets avec une structure dédiée proche de la maquette MVP.

import type { MatchPredictionsResponse } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import MatchPredictionsSection from "../components/MatchPredictionsSection";

type PredictionsScreenProps = {
  matchPredictions: MatchPredictionsResponse | null;
  matchPredictionsStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

// Ce composant structure les prédictions avec une zone principale, une synthèse et des rappels responsables.
function PredictionsScreen({
  matchPredictions,
  matchPredictionsStatus,
  onNavigate,
}: PredictionsScreenProps) {
  return (
    <div className="rb-predictions-screen">
      <section className="rb-page-hero">
        <div>
          <p className="rb-eyebrow">Prédictions</p>
          <h2>Lire les tendances avant-match avec prudence</h2>
          <p>
            RubyBets présente les marchés principaux du MVP : 1X2, volume de
            buts et BTTS, avec un niveau de confiance, un niveau de risque et une
            justification explicable.
          </p>
        </div>

        <aside className="rb-page-hero__aside">
          <p className="rb-eyebrow">Scoring V1</p>
          <h3>Règles métier</h3>
          <p>
            La V1 n’est pas un modèle Machine Learning entraîné : elle repose sur
            un scoring explicable basé sur données réelles.
          </p>
        </aside>
      </section>

      <section className="rb-predictions-layout">
        <div className="rb-predictions-main">
          {matchPredictions ? (
            <MatchPredictionsSection matchPredictions={matchPredictions} />
          ) : (
            <article className="rb-empty-state">
              <p className="rb-eyebrow">Prédictions</p>
              <h3>Prédictions indisponibles</h3>
              <p>{matchPredictionsStatus}</p>
            </article>
          )}
        </div>

        <aside className="rb-predictions-aside">
          <article>
            <p className="rb-eyebrow">Marchés MVP</p>
            <h3>3 lectures principales</h3>
            <ul>
              <li>1X2 : domicile, nul ou extérieur</li>
              <li>Volume de buts : tendance offensive</li>
              <li>BTTS : les deux équipes marquent</li>
            </ul>
          </article>

          <article>
            <p className="rb-eyebrow">Interprétation</p>
            <h3>Confiance ≠ certitude</h3>
            <p>
              Le niveau de confiance indique la solidité relative du signal. Il
              ne garantit jamais le résultat sportif.
            </p>
          </article>

          <article>
            <p className="rb-eyebrow">Étape suivante</p>
            <h3>Recommandation multi-matchs</h3>
            <p>
              Utilisez ensuite ces tendances pour générer une sélection
              analytique selon un niveau de risque choisi.
            </p>
            <button type="button" onClick={() => onNavigate("recommendation")}>
              Générer une recommandation
            </button>
          </article>
        </aside>
      </section>
    </div>
  );
}

export default PredictionsScreen;

// Schéma de communication du fichier :
// PredictionsScreen.tsx
// ├── reçoit les prédictions depuis App.tsx
// ├── utilise MatchPredictionsSection.tsx pour afficher les marchés MVP
// ├── ajoute une colonne de lecture responsable
// └── déclenche la navigation vers RecommendationScreen via onNavigate
