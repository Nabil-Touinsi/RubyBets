// Ce composant transforme l’analyse pré-match en cartes compactes et lisibles.

import type { AnalysisKeyFactor, MatchAnalysisResponse } from "../models/rubybets";
import { cleanTextItems, formatContextTrend, formatDateTime } from "../helpers/displayText";

type MatchAnalysisSectionProps = {
  matchAnalysis: MatchAnalysisResponse;
};

// Cette fonction limite une liste textuelle pour garder une interface compacte.
function getLimitedItems(items: string[], limit: number) {
  return cleanTextItems(items).slice(0, limit);
}

// Cette fonction retourne un badge responsable selon la valeur d’un facteur.
function getFactorBadge(factor: AnalysisKeyFactor) {
  if (factor.value >= 2) {
    return "Signal fort";
  }

  if (factor.value === 1) {
    return "Signal positif";
  }

  if (factor.value === 0) {
    return "Lecture neutre";
  }

  return "Lecture prudente";
}

// Ce composant affiche une carte de facteur clé avec lecture associée.
function FactorCard({ factor }: { factor: AnalysisKeyFactor }) {
  return (
    <article className="rb-analysis-factor-card">
      <div>
        <strong>{factor.label}</strong>
        <span>{getFactorBadge(factor)}</span>
      </div>
      <p>{factor.reading}</p>
    </article>
  );
}

// Ce composant affiche un fait observé sous forme de ligne compacte.
function ObservedFactItem({ fact }: { fact: string }) {
  return (
    <li>
      <span>✓</span>
      <p>{fact}</p>
    </li>
  );
}

// Ce composant présente l’analyse explicable, les faits observés, les facteurs clés et les limites.
function MatchAnalysisSection({ matchAnalysis }: MatchAnalysisSectionProps) {
  const observedFacts = getLimitedItems(matchAnalysis.analysis.observed_facts, 5);
  const factors = matchAnalysis.analysis.key_factors.slice(0, 5);
  const interpretation = getLimitedItems(matchAnalysis.analysis.interpretation, 3);
  const limits = getLimitedItems(matchAnalysis.analysis.limits, 3);

  return (
    <section className="rb-analysis-main-section">
      <article className="rb-analysis-card rb-analysis-summary-card">
        <div className="rb-analysis-card__header">
          <div>
            <p className="rb-analysis-kicker">Résumé analytique</p>
            <h3>{matchAnalysis.analysis.title}</h3>
          </div>
          <span className="rb-analysis-soft-badge">
            {formatContextTrend(matchAnalysis.analysis.context_trend)}
          </span>
        </div>

        <p>
          Cette lecture regroupe les faits observés, les facteurs clés et les limites connues pour préparer l’analyse avant-match.
        </p>

        <div className="rb-analysis-data-strip">
          <span>
            Détail match <strong>{matchAnalysis.data_used.match_details ? "chargé" : "partiel"}</strong>
          </span>
          <span>
            Classement <strong>{matchAnalysis.data_used.competition_standings ? "chargé" : "partiel"}</strong>
          </span>
          <span>
            Source <strong>{matchAnalysis.source}</strong>
          </span>
        </div>
      </article>

      <div className="rb-analysis-content-grid">
        <article className="rb-analysis-card rb-analysis-facts-card">
          <div className="rb-analysis-card__header">
            <div>
              <p className="rb-analysis-kicker">Faits observés</p>
              <h3>Ce que disent les données</h3>
            </div>
          </div>

          {observedFacts.length > 0 ? (
            <ul className="rb-analysis-observed-list">
              {observedFacts.map((fact) => (
                <ObservedFactItem key={fact} fact={fact} />
              ))}
            </ul>
          ) : (
            <p>Aucun fait observé exploitable n’est disponible pour cette rencontre.</p>
          )}
        </article>

        <article className="rb-analysis-card rb-analysis-interpretation-card">
          <div className="rb-analysis-card__header">
            <div>
              <p className="rb-analysis-kicker">Interprétation</p>
              <h3>Lecture analytique</h3>
            </div>
          </div>

          <div className="rb-analysis-interpretation-list">
            {interpretation.length > 0 ? (
              interpretation.map((item) => <p key={item}>{item}</p>)
            ) : (
              <p>Interprétation indisponible pour le moment.</p>
            )}
          </div>
        </article>
      </div>

      <article className="rb-analysis-card rb-analysis-factors-section">
        <div className="rb-analysis-card__header">
          <div>
            <p className="rb-analysis-kicker">Facteurs clés</p>
            <h3>Éléments qui structurent la lecture</h3>
          </div>
        </div>

        <div className="rb-analysis-factor-grid">
          {factors.length > 0 ? (
            factors.map((factor) => <FactorCard key={factor.label} factor={factor} />)
          ) : (
            <p>Aucun facteur clé n’est disponible pour cette analyse.</p>
          )}
        </div>
      </article>

      <article className="rb-analysis-card rb-analysis-limits-card">
        <div className="rb-analysis-card__header">
          <div>
            <p className="rb-analysis-kicker">Limites de l’analyse</p>
            <h3>À prendre en compte</h3>
          </div>
          <span className="rb-analysis-soft-badge">Prudence</span>
        </div>

        <div className="rb-analysis-limits-grid">
          {limits.length > 0 ? (
            limits.map((limit) => <p key={limit}>{limit}</p>)
          ) : (
            <p>Les limites ne sont pas précisées par la réponse actuelle.</p>
          )}
        </div>

        <div className="rb-analysis-data-strip rb-analysis-data-strip--freshness">
          <span>
            Fournisseur <strong>{matchAnalysis.data_freshness.provider}</strong>
          </span>
          <span>
            Match <strong>{formatDateTime(matchAnalysis.data_freshness.match_last_updated)}</strong>
          </span>
        </div>
      </article>
    </section>
  );
}

export default MatchAnalysisSection;

// Schéma de communication du fichier :
// MatchAnalysisSection.tsx
// ├── reçoit matchAnalysis depuis AnalysisScreen.tsx
// ├── utilise displayText.ts pour nettoyer et formater les libellés
// ├── affiche résumé, faits observés, facteurs clés, interprétation et limites
// └── n’ajoute aucune donnée non fournie par le backend