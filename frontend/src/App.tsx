// Ce fichier pilote la navigation multi-écrans MVP de RubyBets en conservant les appels API et composants existants.

import { useEffect, useState } from "react";
import "./App.css";
import {
  getCompetitions,
  getGlossary,
  getHealth,
  getMatchAnalysis,
  getMatchContext,
  getMatchDetails,
  getMatchLineups,
  getMatchPredictions,
  getNationalDynamicPredictionByRubyBetsMatchId,
  getMatchTeamHistory,
  getMatches,
  getNationalMlMultiMatchSelection,
  getResponsibleInfo,
} from "./services/api";
import type {
  Competition,
  GlossaryResponse,
  Match,
  MatchAnalysisResponse,
  MatchContextResponse,
  MatchDetailsResponse,
  MatchLineupsResponse,
  MatchPredictionsResponse,
  NationalMlPredictionResponse,
  MultiMatchRecommendationResponse,
  ResponsibleInfoResponse,
  TeamHistoryResponse,
} from "./models/rubybets";
import AppShell from "./layout/AppShell";
import type { AppScreen } from "./types/navigation";
import { NAVIGATION_ITEMS } from "./types/navigation";
import DashboardScreen from "./screens/DashboardScreen";
import MatchesScreen from "./screens/MatchesScreen";
import MatchDetailsScreen from "./screens/MatchDetailsScreen";
import AnalysisScreen from "./screens/AnalysisScreen";
import PredictionsScreen from "./screens/PredictionsScreen";
import RecommendationScreen from "./screens/RecommendationScreen";
import StatusPanel from "./components/StatusPanel";
import ResourcesScreen from "./screens/ResourcesScreen";

// Ce composant orchestre le chargement des données, la navigation et le rendu des écrans RubyBets.
function App() {
  // État de navigation interne utilisé pour afficher un écran MVP à la fois.
  const [currentScreen, setCurrentScreen] = useState<AppScreen>("dashboard");

  // Active le panneau technique uniquement si la variable VITE_SHOW_STATUS_PANEL vaut "true".
  const showStatusPanel = import.meta.env.VITE_SHOW_STATUS_PANEL === "true";

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

  const [selectedMatchLineups, setSelectedMatchLineups] =
    useState<MatchLineupsResponse | null>(null);

  const [selectedNationalMlPrediction, setSelectedNationalMlPrediction] =
    useState<NationalMlPredictionResponse | null>(null);

  const [selectedTeamHistory, setSelectedTeamHistory] =
    useState<TeamHistoryResponse | null>(null);

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

  // États textuels conservés pour le mode debug du panneau technique.
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

  const [matchLineupsStatus, setMatchLineupsStatus] = useState<string>(
    "Aucune composition chargée"
  );


  const [multiMatchStatus, setMultiMatchStatus] = useState<string>(
    "Aucune recommandation multi-matchs générée"
  );

  const hasSelectedMatch = Boolean(
    selectedMatchDetails ||
      selectedMatchContext ||
      selectedMatchAnalysis ||
      selectedMatchPredictions ||
      selectedNationalMlPrediction ||
      selectedMatchLineups ||
      selectedTeamHistory
  );

  // Chargement initial : vérification backend + récupération des données transversales.
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

    setSelectedMatchDetails(null);
    setSelectedMatchContext(null);
    setSelectedMatchAnalysis(null);
    setSelectedMatchPredictions(null);
    setSelectedMatchLineups(null);
    setSelectedNationalMlPrediction(null);
    setSelectedTeamHistory(null);
    setMultiMatchRecommendation(null);

    setMatchDetailsStatus("Aucun match sélectionné");
    setMatchContextStatus("Aucun contexte chargé");
    setMatchAnalysisStatus("Aucune analyse chargée");
    setMatchPredictionsStatus("Aucune prédiction chargée");
    setMatchLineupsStatus("Aucune composition chargée");
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

  // Change la compétition active et ouvre l’écran Matchs.
  function handleSelectCompetition(competitionCode: string) {
    setSelectedCompetition(competitionCode);
    setCurrentScreen("matches");
  }

  // Charge les données d’un match sélectionné sans bloquer tout l’affichage si un appel API échoue.
  function handleSelectMatch(matchId: number) {
    setCurrentScreen("match-details");

    setSelectedMatchDetails(null);
    setSelectedMatchContext(null);
    setSelectedMatchAnalysis(null);
    setSelectedMatchPredictions(null);
    setSelectedMatchLineups(null);
    setSelectedNationalMlPrediction(null);
    setSelectedTeamHistory(null);

    setMatchDetailsStatus("Chargement du détail du match...");
    setMatchContextStatus("Chargement du contexte avant-match...");
    setMatchAnalysisStatus("Chargement de l’analyse pré-match...");
    setMatchPredictionsStatus("Chargement des prédictions...");
    setMatchLineupsStatus("Chargement des compositions probables...");

    Promise.allSettled([
      getMatchDetails(matchId),
      getMatchContext(matchId),
      getMatchAnalysis(matchId),
      getMatchPredictions(matchId),
      getMatchLineups(matchId),
      getNationalDynamicPredictionByRubyBetsMatchId(matchId),
      getMatchTeamHistory(matchId),
    ]).then(
      ([
        detailsResult,
        contextResult,
        analysisResult,
        predictionsResult,
        lineupsResult,
        nationalMlPredictionResult,
        teamHistoryResult,
      ]) => {
        if (detailsResult.status === "fulfilled") {
          setSelectedMatchDetails(detailsResult.value);
          setMatchDetailsStatus("Détail du match chargé");
        } else {
          setSelectedMatchDetails(null);
          setMatchDetailsStatus("Impossible de charger le détail du match");
        }

        if (contextResult.status === "fulfilled") {
          setSelectedMatchContext(contextResult.value);
          setMatchContextStatus("Contexte avant-match chargé");
        } else {
          setSelectedMatchContext(null);
          setMatchContextStatus("Impossible de charger le contexte avant-match");
        }

        if (analysisResult.status === "fulfilled") {
          setSelectedMatchAnalysis(analysisResult.value);
          setMatchAnalysisStatus("Analyse pré-match chargée");
        } else {
          setSelectedMatchAnalysis(null);
          setMatchAnalysisStatus("Impossible de charger l’analyse pré-match");
        }

        if (predictionsResult.status === "fulfilled") {
          setSelectedMatchPredictions(predictionsResult.value);
          setMatchPredictionsStatus("Prédictions chargées");
        } else {
          setSelectedMatchPredictions(null);
          setMatchPredictionsStatus("Impossible de charger les prédictions");
        }

        if (lineupsResult.status === "fulfilled") {
          setSelectedMatchLineups(lineupsResult.value);
          setMatchLineupsStatus("Compositions chargées");
        } else {
          setSelectedMatchLineups(null);
          setMatchLineupsStatus("Impossible de charger les compositions");
        }

        if (nationalMlPredictionResult.status === "fulfilled") {
          setSelectedNationalMlPrediction(nationalMlPredictionResult.value);
        } else {
          setSelectedNationalMlPrediction(null);
        }

        if (teamHistoryResult.status === "fulfilled") {
          setSelectedTeamHistory(teamHistoryResult.value);
        } else {
          setSelectedTeamHistory(null);
        }
      }
    );
  }

  // Génère une sélection multi-matchs depuis le modèle national déjà utilisé par l’écran Prédictions.
  function handleGenerateMultiMatchRecommendation() {
    const nationalSelectionCompetitionCode = "WC";

    setMultiMatchStatus("Génération de la sélection ML nationale...");

    getNationalMlMultiMatchSelection(
      nationalSelectionCompetitionCode,
      recommendationMatchCount,
      recommendationRiskLevel
    )
      .then((data) => {
        setMultiMatchRecommendation(data);
        setMultiMatchStatus("Sélection ML nationale générée");
      })
      .catch(() => {
        setMultiMatchRecommendation(null);
        setMultiMatchStatus("Impossible de générer la sélection ML nationale");
      });
  }

  // Affiche un écran d’attente lorsqu’une page dépend d’un match sélectionné.
  function renderMatchRequiredState(title: string) {
    return (
      <section>
        <h2>{title}</h2>
        <p>Sélectionne d’abord un match depuis l’écran Matchs.</p>
        <button type="button" onClick={() => setCurrentScreen("matches")}>
          Aller aux matchs
        </button>
      </section>
    );
  }

  // Affiche le contenu correspondant à l’écran actif.
  function renderCurrentScreen() {
    if (currentScreen === "dashboard") {
      return (
        <DashboardScreen
          apiStatus={apiStatus}
          competitions={competitions}
          matches={matches}
          selectedCompetition={selectedCompetition}
          onSelectCompetition={handleSelectCompetition}
          onSelectMatch={handleSelectMatch}
          onNavigate={setCurrentScreen}
        />
      );
    }

    if (currentScreen === "matches") {
      return (
        <MatchesScreen
          competitions={competitions}
          matches={matches}
          selectedCompetition={selectedCompetition}
          matchesStatus={matchesStatus}
          onSelectCompetition={handleSelectCompetition}
          onSelectMatch={handleSelectMatch}
          onNavigate={setCurrentScreen}
        />
      );
    }

    if (currentScreen === "match-details") {
      if (!hasSelectedMatch) {
        return renderMatchRequiredState("Détail match");
      }

      return (
        <MatchDetailsScreen
          matchDetails={selectedMatchDetails}
          matchContext={selectedMatchContext}
          matchAnalysis={selectedMatchAnalysis}
          matchLineups={selectedMatchLineups}
          teamHistory={selectedTeamHistory}
          matchDetailsStatus={matchDetailsStatus}
          matchContextStatus={matchContextStatus}
          matchAnalysisStatus={matchAnalysisStatus}
          matchLineupsStatus={matchLineupsStatus}
          onNavigate={setCurrentScreen}
        />
      );
    }

    if (currentScreen === "analysis") {
      if (!hasSelectedMatch) {
        return renderMatchRequiredState("Analyse pré-match");
      }

      return (
        <AnalysisScreen
          matchAnalysis={selectedMatchAnalysis}
          matchDetails={selectedMatchDetails}
          matchContext={selectedMatchContext}
          matchAnalysisStatus={matchAnalysisStatus}
          onNavigate={setCurrentScreen}
        />
      );
    }

    if (currentScreen === "predictions") {
      if (!hasSelectedMatch) {
        return renderMatchRequiredState("Prédictions");
      }

      return (
        <PredictionsScreen
          nationalMlPrediction={selectedNationalMlPrediction}
          matchDetails={selectedMatchDetails}
          matchContext={selectedMatchContext}
          matchPredictionsStatus={matchPredictionsStatus}
          onNavigate={setCurrentScreen}
        />
      );
    }

    if (currentScreen === "recommendation") {
      return (
        <RecommendationScreen
          recommendationMatchCount={recommendationMatchCount}
          recommendationRiskLevel={recommendationRiskLevel}
          multiMatchRecommendation={multiMatchRecommendation}
          multiMatchStatus={multiMatchStatus}
          onChangeMatchCount={setRecommendationMatchCount}
          onChangeRiskLevel={setRecommendationRiskLevel}
          onGenerateRecommendation={handleGenerateMultiMatchRecommendation}
        />
      );
    }

    if (currentScreen === "resources") {
      return (
        <ResourcesScreen
          glossary={glossary}
          glossaryStatus={glossaryStatus}
          responsibleInfo={responsibleInfo}
          responsibleInfoStatus={responsibleInfoStatus}
        />
      );
    }

    return null;
  }

  return (
    <AppShell
      currentScreen={currentScreen}
      navigationItems={NAVIGATION_ITEMS}
      hasSelectedMatch={hasSelectedMatch}
      onNavigate={setCurrentScreen}
      statusNode={
        showStatusPanel ? (
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
        ) : null
      }
    >
      {renderCurrentScreen()}
    </AppShell>
  );
}

export default App;

// Schéma de communication du fichier :
// App.tsx
// ├── appelle services/api.ts pour récupérer les données backend
// ├── charge aussi /analysis, /lineups, /team-history et le modèle national lors de la sélection d’un match
// ├── transmet l’analyse détaillée et les compositions à MatchDetailsScreen.tsx pour les onglets dédiés
// ├── pilote la navigation via currentScreen
// ├── utilise AppShell.tsx pour structurer l’application
// ├── peut transmettre StatusPanel.tsx à AppShell.tsx uniquement en mode debug
// ├── affiche les écrans du dossier screens/ selon l’écran actif
// └── branche aussi l’écran Sélection sur la route expérimentale nationale issue du même modèle que Prédictions