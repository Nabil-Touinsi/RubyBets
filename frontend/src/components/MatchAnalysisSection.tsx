// Ce composant affiche l’analyse pré-match du match sélectionné dans RubyBets.
import type { MatchAnalysisResponse } from "../models/rubybets";
import { cleanTextItems, formatContextTrend } from "../helpers/displayText";
import DataFreshnessBlock from "./DataFreshnessBlock";

type MatchAnalysisSectionProps = {
  matchAnalysis: MatchAnalysisResponse;
};

// Ce composant présente l’analyse explicable du match, ses limites et la fraîcheur des données utilisées.
function MatchAnalysisSection({ matchAnalysis }: MatchAnalysisSectionProps) {
  return (
    <section>
      <h2>Analyse pré-match</h2>

      <h3>{matchAnalysis.analysis.title}</h3>

      <p>
        Tendance de contexte :{" "}
        {formatContextTrend(matchAnalysis.analysis.context_trend)}
      </p>

      <h4>Faits observés</h4>
      <ul>
        {cleanTextItems(matchAnalysis.analysis.observed_facts).map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>

      <h4>Facteurs clés</h4>
      <ul>
        {matchAnalysis.analysis.key_factors.map((factor) => (
          <li key={factor.label}>
            {factor.label} : {factor.value} — {factor.reading}
          </li>
        ))}
      </ul>

      <h4>Interprétation</h4>
      <ul>
        {cleanTextItems(matchAnalysis.analysis.interpretation).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <h4>Limites de l’analyse</h4>
      <ul>
        {cleanTextItems(matchAnalysis.analysis.limits).map((limit) => (
          <li key={limit}>{limit}</li>
        ))}
      </ul>

      <p>
        Source : {matchAnalysis.source} — Données :{" "}
        {matchAnalysis.data_freshness.provider}
      </p>

      <DataFreshnessBlock
        title="Fraîcheur des données utilisées pour l’analyse"
        dataFreshness={matchAnalysis.data_freshness}
      />
    </section>
  );
}

export default MatchAnalysisSection;

// Schéma de communication du fichier :
// MatchAnalysisSection.tsx
// ├── reçoit l’analyse pré-match depuis App.tsx
// ├── utilise displayText.ts pour formater la tendance et nettoyer les listes
// ├── utilise DataFreshnessBlock.tsx pour afficher la fraîcheur des données
// └── affiche les faits observés, facteurs clés, interprétation et limites fournis par le backend
