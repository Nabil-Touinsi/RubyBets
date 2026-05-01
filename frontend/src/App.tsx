// Ce fichier affiche la page principale temporaire de RubyBets avec compétitions, matchs, analyse, prédictions, recommandation multi-matchs, glossaire et informations responsables.

import { useEffect, useState } from "react";
import "./App.css";
import {
  getCompetitions,
  getGlossary,
  getHealth,
  getMatchAnalysis,
  getMatchContext,
  getMatchDetails,
  getMatchPredictions,
  getMatches,
  getMultiMatchRecommendation,
  getResponsibleInfo,
} from "./services/api";
import type {
  Competition,
  GlossaryResponse,
  Match,
  MatchAnalysisResponse,
  MatchContextResponse,
  MatchDetailsResponse,
  MatchPredictionsResponse,
  MultiMatchRecommendationResponse,
  ResponsibleInfoResponse,
} from "./models/rubybets";
import {
  cleanTextItems,
  formatConfidenceLevel,
  formatContextTrend,
  formatPredictionStatus,
  formatRiskLevel,
} from "./helpers/displayText";
import StatusPanel from "./components/StatusPanel";
import CompetitionsSection from "./components/CompetitionsSection";
import MatchesSection from "./components/MatchesSection";
import MultiMatchRecommendationSection from "./components/MultiMatchRecommendationSection";
import GlossarySection from "./components/GlossarySection";
import ResponsibleInfoSection from "./components/ResponsibleInfoSection";
import MatchDetailsSection from "./components/MatchDetailsSection";
import MatchContextSection from "./components/MatchContextSection";
function App() {
  // États globaux de connexion et de données principales.
  const [apiStatus, setApiStatus] = useState<string>("Vérification en cours...");
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [selectedCompetition, setSelectedCompetition] = useState<string>("PL");

  // États liés au match sélectionné.
  const [selectedMatchDetails, setSelectedMatchDetails] =
    useState<MatchDetailsResponse | null>(null);

  const [selectedMatchContext, setSelectedMatchContext] =
    useState<MatchContextResponse | null>(null);

  const [selectedMatchAnalysis, setSelectedMatchAnalysis] =
    useState<MatchAnalysisResponse | null>(null);

  const [selectedMatchPredictions, setSelectedMatchPredictions] =
    useState<MatchPredictionsResponse | null>(null);

  // États liés à la recommandation multi-matchs.
  const [recommendationMatchCount, setRecommendationMatchCount] =
    useState<number>(3);

  const [recommendationRiskLevel, setRecommendationRiskLevel] =
    useState<"low" | "medium" | "high">("medium");

  const [multiMatchRecommendation, setMultiMatchRecommendation] =
    useState<MultiMatchRecommendationResponse | null>(null);

  // États liés au glossaire pédagogique.
  const [glossary, setGlossary] = useState<GlossaryResponse | null>(null);

  const [glossaryStatus, setGlossaryStatus] = useState<string>(
    "Chargement du glossaire..."
  );

  // États liés aux informations responsables.
  const [responsibleInfo, setResponsibleInfo] =
    useState<ResponsibleInfoResponse | null>(null);

  const [responsibleInfoStatus, setResponsibleInfoStatus] = useState<string>(
    "Chargement des informations responsables..."
  );

  // États textuels affichés à l’écran pour suivre les chargements.
  const [competitionsStatus, setCompetitionsStatus] = useState<string>(
    "Chargement des compétitions..."
  );

  const [matchesStatus, setMatchesStatus] = useState<string>(
    "Chargement des matchs..."
  );

  const [matchDetailsStatus, setMatchDetailsStatus] = useState<string>(
    "Aucun match sélectionné"
  );

  const [matchContextStatus, setMatchContextStatus] = useState<string>(
    "Aucun contexte chargé"
  );

  const [matchAnalysisStatus, setMatchAnalysisStatus] = useState<string>(
    "Aucune analyse chargée"
  );

  const [matchPredictionsStatus, setMatchPredictionsStatus] = useState<string>(
    "Aucune prédiction chargée"
  );

  const [multiMatchStatus, setMultiMatchStatus] = useState<string>(
    "Aucune recommandation multi-matchs générée"
  );

  // Chargement initial : vérification backend + récupération des compétitions.
  useEffect(() => {
    getHealth()
      .then((data) => {
        setApiStatus(data.status === "ok" ? "Backend connecté" : "Réponse inattendue");
      })
      .catch(() => {
        setApiStatus("Backend inaccessible");
      });

    getCompetitions()
      .then((data) => {
        setCompetitions(data.competitions || []);
        setCompetitionsStatus("Compétitions chargées");
      })
      .catch(() => {
        setCompetitionsStatus("Impossible de charger les compétitions");
      });

    getGlossary()
      .then((data) => {
        setGlossary(data);
        setGlossaryStatus("Glossaire chargé");
      })
      .catch(() => {
        setGlossary(null);
        setGlossaryStatus("Impossible de charger le glossaire");
      });

    getResponsibleInfo()
      .then((data) => {
        setResponsibleInfo(data);
        setResponsibleInfoStatus("Informations responsables chargées");
      })
      .catch(() => {
        setResponsibleInfo(null);
        setResponsibleInfoStatus("Impossible de charger les informations responsables");
      });
  }, []);

  // Chargement des matchs quand l’utilisateur change de compétition.
  useEffect(() => {
    setMatchesStatus("Chargement des matchs...");

    // On réinitialise les données du match précédent et la recommandation en cours.
    setSelectedMatchDetails(null);
    setSelectedMatchContext(null);
    setSelectedMatchAnalysis(null);
    setSelectedMatchPredictions(null);
    setMultiMatchRecommendation(null);

    setMatchDetailsStatus("Aucun match sélectionné");
    setMatchContextStatus("Aucun contexte chargé");
    setMatchAnalysisStatus("Aucune analyse chargée");
    setMatchPredictionsStatus("Aucune prédiction chargée");
    setMultiMatchStatus("Aucune recommandation multi-matchs générée");

    getMatches(selectedCompetition)
      .then((data) => {
        setMatches(data.matches || []);
        setMatchesStatus("Matchs chargés");
      })
      .catch(() => {
        setMatches([]);
        setMatchesStatus("Impossible de charger les matchs");
      });
  }, [selectedCompetition]);

  // Chargement complet d’un match : détail, contexte, analyse et prédictions.
  function handleSelectMatch(matchId: number) {
    setMatchDetailsStatus("Chargement du détail du match...");
    setMatchContextStatus("Chargement du contexte avant-match...");
    setMatchAnalysisStatus("Chargement de l’analyse pré-match...");
    setMatchPredictionsStatus("Chargement des prédictions...");

    Promise.all([
      getMatchDetails(matchId),
      getMatchContext(matchId),
      getMatchAnalysis(matchId),
      getMatchPredictions(matchId),
    ])
      .then(([detailsData, contextData, analysisData, predictionsData]) => {
        setSelectedMatchDetails(detailsData);
        setSelectedMatchContext(contextData);
        setSelectedMatchAnalysis(analysisData);
        setSelectedMatchPredictions(predictionsData);

        setMatchDetailsStatus("Détail du match chargé");
        setMatchContextStatus("Contexte avant-match chargé");
        setMatchAnalysisStatus("Analyse pré-match chargée");
        setMatchPredictionsStatus("Prédictions chargées");
      })
      .catch(() => {
        setSelectedMatchDetails(null);
        setSelectedMatchContext(null);
        setSelectedMatchAnalysis(null);
        setSelectedMatchPredictions(null);

        setMatchDetailsStatus("Impossible de charger le détail du match");
        setMatchContextStatus("Impossible de charger le contexte avant-match");
        setMatchAnalysisStatus("Impossible de charger l’analyse pré-match");
        setMatchPredictionsStatus("Impossible de charger les prédictions");
      });
  }

  // Génère une recommandation multi-matchs à partir des prédictions disponibles côté backend.
  function handleGenerateMultiMatchRecommendation() {
    setMultiMatchStatus("Génération de la recommandation multi-matchs...");

    getMultiMatchRecommendation(
      selectedCompetition,
      recommendationMatchCount,
      recommendationRiskLevel
    )
      .then((data) => {
        setMultiMatchRecommendation(data);
        setMultiMatchStatus("Recommandation multi-matchs générée");
      })
      .catch(() => {
        setMultiMatchRecommendation(null);
        setMultiMatchStatus("Impossible de générer la recommandation multi-matchs");
      });
  }

  return (
    <main>
      <h1>RubyBets</h1>

      <p>Application d’aide à la décision football avant-match.</p>
      <p>Frontend React connecté aux routes backend métier.</p>

      <StatusPanel
      apiStatus={apiStatus}
      competitionsStatus={competitionsStatus}
      matchesStatus={matchesStatus}
      matchDetailsStatus={matchDetailsStatus}
      matchContextStatus={matchContextStatus}
      matchAnalysisStatus={matchAnalysisStatus}
      matchPredictionsStatus={matchPredictionsStatus}
      multiMatchStatus={multiMatchStatus}
      glossaryStatus={glossaryStatus}
      responsibleInfoStatus={responsibleInfoStatus}
      />

        <CompetitionsSection
      competitions={competitions}
      onSelectCompetition={setSelectedCompetition}
      />

          <MatchesSection
        selectedCompetition={selectedCompetition}
        matches={matches}
        onSelectMatch={handleSelectMatch}
      />

          <MultiMatchRecommendationSection
        recommendationMatchCount={recommendationMatchCount}
        recommendationRiskLevel={recommendationRiskLevel}
        multiMatchRecommendation={multiMatchRecommendation}
        onChangeMatchCount={setRecommendationMatchCount}
        onChangeRiskLevel={setRecommendationRiskLevel}
        onGenerateRecommendation={handleGenerateMultiMatchRecommendation}
      />

      <GlossarySection glossary={glossary} />

      <ResponsibleInfoSection responsibleInfo={responsibleInfo} />

      {selectedMatchDetails && (
  <MatchDetailsSection matchDetails={selectedMatchDetails} />
)}

      {selectedMatchContext && (
  <MatchContextSection matchContext={selectedMatchContext} />
)}

      {selectedMatchAnalysis && (
        <section>
          <h2>Analyse pré-match</h2>

          <h3>{selectedMatchAnalysis.analysis.title}</h3>

          <p>
            Tendance de contexte :{" "}
            <strong>{formatContextTrend(selectedMatchAnalysis.analysis.context_trend)}</strong>
          </p>

          <h4>Faits observés</h4>
          <ul>
            {cleanTextItems(selectedMatchAnalysis.analysis.observed_facts).map(
              (fact) => (
                <li key={fact}>{fact}</li>
              )
            )}
          </ul>

          <h4>Facteurs clés</h4>
          <ul>
            {selectedMatchAnalysis.analysis.key_factors.map((factor) => (
              <li key={`${factor.label}-${factor.value}`}>
                <strong>{factor.label}</strong> : {factor.value} —{" "}
                {factor.reading}
              </li>
            ))}
          </ul>

          <h4>Interprétation</h4>
          <ul>
            {cleanTextItems(selectedMatchAnalysis.analysis.interpretation).map(
              (item) => (
                <li key={item}>{item}</li>
              )
            )}
          </ul>

          <h4>Limites de l’analyse</h4>
          <ul>
            {cleanTextItems(selectedMatchAnalysis.analysis.limits).map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>

          <p>
            Source : {selectedMatchAnalysis.source} — Données :{" "}
            {selectedMatchAnalysis.data_freshness.provider}
          </p>
        </section>
      )}

      {selectedMatchPredictions && (
        <section>
          <h2>Prédictions avant-match</h2>

          <p>
            Statut :{" "}
            <strong>{formatPredictionStatus(selectedMatchPredictions.predictions.status)}</strong>
          </p>

          {selectedMatchPredictions.predictions.message && (
            <p>{selectedMatchPredictions.predictions.message}</p>
          )}

          {selectedMatchPredictions.predictions.predictions && (
            <>
              <article>
                <h3>Prédiction 1X2</h3>
                <p>
                  <strong>
                    {selectedMatchPredictions.predictions.predictions.one_x_two.label}
                  </strong>
                </p>
                <p>
                  Confiance :{" "}
                  {formatConfidenceLevel(
                    selectedMatchPredictions.predictions.predictions.one_x_two
                      .confidence
                  )}
                </p>
                <p>
                  Risque :{" "}
                  {formatRiskLevel(
                    selectedMatchPredictions.predictions.predictions.one_x_two.risk
                  )}
                </p>
                <p>
                  Justification :{" "}
                  {
                    selectedMatchPredictions.predictions.predictions.one_x_two
                      .justification
                  }
                </p>
              </article>

              <article>
                <h3>Volume de buts</h3>
                <p>
                  <strong>
                    {selectedMatchPredictions.predictions.predictions.goals.label}
                  </strong>
                </p>
                <p>
                  Confiance :{" "}
                  {formatConfidenceLevel(
                    selectedMatchPredictions.predictions.predictions.goals.confidence
                  )}
                </p>
                <p>
                  Risque :{" "}
                  {formatRiskLevel(
                    selectedMatchPredictions.predictions.predictions.goals.risk
                  )}
                </p>
                <p>
                  Justification :{" "}
                  {
                    selectedMatchPredictions.predictions.predictions.goals
                      .justification
                  }
                </p>
              </article>

              <article>
                <h3>BTTS</h3>
                <p>
                  <strong>
                    {selectedMatchPredictions.predictions.predictions.btts.label}
                  </strong>
                </p>
                <p>
                  Confiance :{" "}
                  {formatConfidenceLevel(
                    selectedMatchPredictions.predictions.predictions.btts.confidence
                  )}
                </p>
                <p>
                  Risque :{" "}
                  {formatRiskLevel(
                    selectedMatchPredictions.predictions.predictions.btts.risk
                  )}
                </p>
                <p>
                  Justification :{" "}
                  {
                    selectedMatchPredictions.predictions.predictions.btts
                      .justification
                  }
                </p>
              </article>
            </>
          )}

          {selectedMatchPredictions.predictions.limits && (
            <>
              <h4>Limites des prédictions</h4>
              <ul>
                {cleanTextItems(selectedMatchPredictions.predictions.limits).map(
                  (limit) => (
                    <li key={limit}>{limit}</li>
                  )
                )}
              </ul>
            </>
          )}

          <p>
            Méthode :{" "}
            {selectedMatchPredictions.predictions.method || "Non disponible"} —
            Source : {selectedMatchPredictions.source}
          </p>
        </section>
      )}
    </main>
  );
}

export default App;
