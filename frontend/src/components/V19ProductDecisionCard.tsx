// Rôle du fichier :
// Ce composant affiche la décision produit V19 de façon responsable sans exposer les scores bruts ni les odds internes.

import type { V19ProductPredictionResponse } from "../models/rubybets";

type V19ProductDecisionCardProps = {
  prediction: V19ProductPredictionResponse | null;
  statusMessage: string;
};

const MARKET_LABELS: Record<string, string> = {
  STRICT_1X2: "Résultat du match",
  DOUBLE_CHANCE: "Double chance",
  OVER_1_5: "Plus de 1,5 but",
  GOALS_OVER_15: "Plus de 1,5 but",
  BTTS: "Les deux équipes marquent",
};

const VALUE_LABELS: Record<string, string> = {
  HOME_WIN: "Victoire domicile",
  DRAW: "Match nul",
  AWAY_WIN: "Victoire extérieure",
  "1X": "Domicile ou nul",
  X2: "Extérieur ou nul",
  "12": "Domicile ou extérieur",
  OVER_1_5: "Plus de 1,5 but",
  BTTS_YES: "Oui",
  BTTS_NO: "Non",
};

// Cette fonction transforme un code technique en libellé lisible sans modifier la décision backend.
function formatDecisionLabel(value: string, labels: Record<string, string>) {
  return labels[value] ?? value.replaceAll("_", " ").toLocaleLowerCase("fr-FR");
}

// Ce composant restitue les états chargement, recommandation, abstention et indisponibilité du pipeline V19.
function V19ProductDecisionCard({
  prediction,
  statusMessage,
}: V19ProductDecisionCardProps) {
  const isLoading = statusMessage.startsWith("Chargement");

  if (isLoading) {
    return (
      <section
        className="rb-v19-decision-card rb-v19-decision-card--loading"
        aria-live="polite"
      >
        <div className="rb-v19-decision-card__header">
          <p>Décision RubyBets V19</p>
          <span>Analyse en cours</span>
        </div>
        <h3>Comparaison des signaux disponibles</h3>
        <p>Le moteur prépare une décision avant-match sans bloquer le reste de la fiche.</p>
      </section>
    );
  }

  if (!prediction) {
    return (
      <section
        className="rb-v19-decision-card rb-v19-decision-card--unavailable"
        aria-live="polite"
      >
        <div className="rb-v19-decision-card__header">
          <p>Décision RubyBets V19</p>
          <span>Indisponible</span>
        </div>
        <h3>Décision temporairement indisponible</h3>
        <p>Le reste des informations du match demeure consultable.</p>
      </section>
    );
  }

  if (prediction.status === "RECOMMEND" && prediction.recommendation) {
    const marketLabel = formatDecisionLabel(
      prediction.recommendation.market_type,
      MARKET_LABELS,
    );
    const valueLabel = formatDecisionLabel(
      prediction.recommendation.value,
      VALUE_LABELS,
    );

    return (
      <section
        className="rb-v19-decision-card rb-v19-decision-card--recommend"
        aria-live="polite"
      >
        <div className="rb-v19-decision-card__header">
          <p>Décision RubyBets V19</p>
          <span>Signal retenu</span>
        </div>

        <div className="rb-v19-decision-card__decision">
          <div>
            <small>Marché retenu</small>
            <h3>{marketLabel}</h3>
          </div>
          <strong>{valueLabel}</strong>
        </div>

        <p>
          RubyBets retient ce signal après comparaison des experts disponibles.
          Aucun score brut, aucune cote et aucun bookmaker ne sont affichés.
        </p>
        <small className="rb-v19-decision-card__note">
          {prediction.responsible_note}
        </small>
      </section>
    );
  }

  if (prediction.status === "ABSTAIN") {
    return (
      <section
        className="rb-v19-decision-card rb-v19-decision-card--abstain"
        aria-live="polite"
      >
        <div className="rb-v19-decision-card__header">
          <p>Décision RubyBets V19</p>
          <span>Abstention</span>
        </div>
        <h3>Aucune recommandation retenue</h3>
        <p>
          Les données ou les signaux disponibles ne permettent pas une recommandation suffisamment responsable.
        </p>
        <small className="rb-v19-decision-card__note">
          {prediction.responsible_note}
        </small>
      </section>
    );
  }

  return (
    <section
      className="rb-v19-decision-card rb-v19-decision-card--unavailable"
      aria-live="polite"
    >
      <div className="rb-v19-decision-card__header">
        <p>Décision RubyBets V19</p>
        <span>État non reconnu</span>
      </div>
      <h3>Décision temporairement indisponible</h3>
      <p>Le moteur a répondu avec un état qui ne peut pas encore être présenté dans l’interface.</p>
    </section>
  );
}

export default V19ProductDecisionCard;

// Schéma de communication du fichier :
// V19ProductDecisionCard.tsx
// ├── reçoit V19ProductPredictionResponse depuis MatchDetailsScreen.tsx
// ├── utilise uniquement le résumé public fourni par la route produit V19
// └── n’affiche jamais score brut, odds, bookmaker ou payload FlashScore
