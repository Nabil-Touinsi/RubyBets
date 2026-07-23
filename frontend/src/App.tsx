// Ce fichier pilote la navigation multi-écrans MVP de RubyBets en conservant les appels API et composants existants.

import { useEffect, useRef, useState } from "react";
import "./App.css";
import "./styles/MatchDetailsScreen.css";
import {
  getCompetitions,
  getGlossary,
  getHealth,
  getMatchAdvancedStats,
  getMatchAnalysis,
  getMatchContext,
  getMatchDetails,
  getMatchLineups,
  getMatchNewsContext,
  getMatchPredictions,
  getNationalDynamicPredictionByRubyBetsMatchId,
  getMatchTeamHistory,
  getV19H2HAnalysis,
  getV19ProductPrediction,
  getMatches,
  getV19MultiMatchSelection,
  getResponsibleInfo,
} from "./services/api";
import type {
  Competition,
  GlossaryResponse,
  Match,
  MatchAdvancedStatsResponse,
  MatchAnalysisResponse,
  MatchContextResponse,
  MatchDetailsResponse,
  MatchLineupsResponse,
  MatchNewsContextResponse,
  MatchPredictionsResponse,
  NationalMlPredictionResponse,
  V19SelectionProfile,
  V19SelectionResponse,
  ResponsibleInfoResponse,
  TeamHistoryResponse,
  V19H2HResponse,
  V19ProductPredictionResponse,
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
import ArchivesScreen from "./screens/ArchivesScreen";
import StatusPanel from "./components/StatusPanel";
import ResourcesScreen from "./screens/ResourcesScreen";

const DEFAULT_COMPETITION_CODE = "PL";

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
  const [selectedCompetition, setSelectedCompetition] = useState<string>(
    DEFAULT_COMPETITION_CODE
  );

  // Références techniques empêchant les doubles chargements initiaux et les réponses obsolètes.
  const initialLoadStarted = useRef<boolean>(false);
  const matchLoadRequestId = useRef<number>(0);
  const selectedMatchLoadRequestId = useRef<number>(0);

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

  const [selectedMatchNewsContext, setSelectedMatchNewsContext] =
    useState<MatchNewsContextResponse | null>(null);

  const [selectedNationalMlPrediction, setSelectedNationalMlPrediction] =
    useState<NationalMlPredictionResponse | null>(null);

  const [selectedTeamHistory, setSelectedTeamHistory] =
    useState<TeamHistoryResponse | null>(null);

  const [selectedMatchAdvancedStats, setSelectedMatchAdvancedStats] =
    useState<MatchAdvancedStatsResponse | null>(null);


  const [selectedV19H2HAnalysis, setSelectedV19H2HAnalysis] =
    useState<V19H2HResponse | null>(null);

  const [selectedV19ProductPrediction, setSelectedV19ProductPrediction] =
    useState<V19ProductPredictionResponse | null>(null);

  // États liés à la recommandation multi-matchs.
  const [recommendationMatchCount, setRecommendationMatchCount] =
    useState<number>(3);

  const [recommendationSelectionProfile, setRecommendationSelectionProfile] =
    useState<"low" | "medium" | "high">("medium");

  const [multiMatchRecommendation, setMultiMatchRecommendation] =
    useState<V19SelectionResponse | null>(null);

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

  const [matchNewsContextStatus, setMatchNewsContextStatus] = useState<string>(
    "Aucune actualité contextuelle chargée"
  );

  const [matchAdvancedStatsStatus, setMatchAdvancedStatsStatus] = useState<string>(
    "Statistiques avancées non chargées"
  );


  const [v19H2HStatus, setV19H2HStatus] = useState<string>(
    "Aucune analyse H2H V19 chargée"
  );

  const [v19ProductStatus, setV19ProductStatus] = useState<string>(
    "Aucune décision produit V19 chargée"
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
      selectedMatchNewsContext ||
      selectedTeamHistory ||
      selectedV19H2HAnalysis ||
      selectedV19ProductPrediction
  );

  // Réinitialise les données qui dépendent de la compétition active.
  function resetCompetitionDependentState() {
    selectedMatchLoadRequestId.current += 1;
    setSelectedMatchDetails(null);
    setSelectedMatchContext(null);
    setSelectedMatchAnalysis(null);
    setSelectedMatchPredictions(null);
    setSelectedMatchLineups(null);
    setSelectedMatchNewsContext(null);
    setSelectedNationalMlPrediction(null);
    setSelectedTeamHistory(null);
    setSelectedMatchAdvancedStats(null);
    setSelectedV19H2HAnalysis(null);
    setSelectedV19ProductPrediction(null);
    setMultiMatchRecommendation(null);

    setMatchDetailsStatus("Aucun match sélectionné");
    setMatchContextStatus("Aucun contexte chargé");
    setMatchAnalysisStatus("Aucune analyse chargée");
    setMatchPredictionsStatus("Aucune prédiction chargée");
    setMatchLineupsStatus("Aucune composition chargée");
    setMatchNewsContextStatus("Aucune actualité contextuelle chargée");
    setMatchAdvancedStatsStatus("Statistiques avancées non chargées");
    setV19H2HStatus("Aucune analyse H2H V19 chargée");
    setV19ProductStatus("Aucune décision produit V19 chargée");
    setMultiMatchStatus("Aucune recommandation multi-matchs générée");
  }

  // Construit l’ordre de recherche en testant d’abord la compétition demandée.
  function buildCompetitionSearchOrder(
    requestedCompetitionCode: string,
    availableCompetitions: Competition[]
  ): string[] {
    const orderedCodes = [
      requestedCompetitionCode,
      ...availableCompetitions.map((competition) => competition.code),
    ];

    return orderedCodes.filter(
      (competitionCode, index) =>
        competitionCode.length > 0 &&
        orderedCodes.indexOf(competitionCode) === index
    );
  }

  // Charge une compétition et bascule sur la première alternative contenant des matchs.
  async function loadMatchesForCompetition(
    requestedCompetitionCode: string,
    availableCompetitions: Competition[]
  ): Promise<void> {
    const requestId = matchLoadRequestId.current + 1;
    matchLoadRequestId.current = requestId;

    setSelectedCompetition(requestedCompetitionCode);
    setMatches([]);
    setMatchesStatus("Chargement des matchs...");
    resetCompetitionDependentState();

    const competitionCodes = buildCompetitionSearchOrder(
      requestedCompetitionCode,
      availableCompetitions
    );
    let failedRequestCount = 0;

    for (const competitionCode of competitionCodes) {
      if (matchLoadRequestId.current !== requestId) {
        return;
      }

      try {
        const data = await getMatches(competitionCode);

        if (matchLoadRequestId.current !== requestId) {
          return;
        }

        const loadedMatches = data.matches || [];

        if (loadedMatches.length > 0) {
          setSelectedCompetition(competitionCode);
          setMatches(loadedMatches);
          setMatchesStatus(
            competitionCode === requestedCompetitionCode
              ? "Matchs chargés"
              : `Aucun match pour ${requestedCompetitionCode}. ${competitionCode} sélectionnée automatiquement.`
          );
          return;
        }
      } catch {
        if (matchLoadRequestId.current !== requestId) {
          return;
        }

        failedRequestCount += 1;
      }
    }

    if (matchLoadRequestId.current !== requestId) {
      return;
    }

    setMatches([]);
    setSelectedCompetition(requestedCompetitionCode);
    setMatchesStatus(
      failedRequestCount === competitionCodes.length
        ? "Impossible de charger les matchs des compétitions disponibles"
        : "Aucun match disponible dans les compétitions suivies"
    );
  }

  // Chargement initial : vérification backend + récupération des données transversales.
  useEffect(() => {
    if (initialLoadStarted.current) {
      return;
    }

    initialLoadStarted.current = true;

    getHealth()
      .then((data) => {
        setApiStatus(data.status === "ok" ? "Backend connecté" : "Réponse inattendue");
      })
      .catch(() => {
        setApiStatus("Backend inaccessible");
      });

    getCompetitions()
      .then((data) => {
        const loadedCompetitions = data.competitions || [];

        setCompetitions(loadedCompetitions);
        setCompetitionsStatus("Compétitions chargées");
        void loadMatchesForCompetition(
          DEFAULT_COMPETITION_CODE,
          loadedCompetitions
        );
      })
      .catch(() => {
        setCompetitions([]);
        setCompetitionsStatus("Impossible de charger les compétitions");
        void loadMatchesForCompetition(DEFAULT_COMPETITION_CODE, []);
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

  // Actualise uniquement les matchs de la compétition active sans recharger toute l’application.
  async function refreshSelectedCompetitionMatches(): Promise<void> {
    const requestId = matchLoadRequestId.current + 1;
    matchLoadRequestId.current = requestId;
    setMatchesStatus("Actualisation des matchs...");

    try {
      const data = await getMatches(selectedCompetition);

      if (matchLoadRequestId.current !== requestId) {
        return;
      }

      setMatches(data.matches || []);
      setMatchesStatus("Matchs actualisés");
    } catch {
      if (matchLoadRequestId.current !== requestId) {
        return;
      }

      setMatchesStatus("Impossible d’actualiser les matchs");
    }
  }

  // Change la compétition active, applique le fallback et ouvre l’écran Matchs.
  function handleSelectCompetition(competitionCode: string) {
    setCurrentScreen("matches");
    void loadMatchesForCompetition(competitionCode, competitions);
  }

  // Vérifie qu’une réponse API appartient toujours au dernier match demandé.
  function isCurrentSelectedMatchRequest(requestId: number): boolean {
    return selectedMatchLoadRequestId.current === requestId;
  }

  // Construit un détail provisoire depuis la liste afin d’afficher immédiatement l’en-tête du match.
  function buildOptimisticMatchDetails(matchId: number): MatchDetailsResponse | null {
    const selectedMatch = matches.find((match) => match.id === matchId);

    if (!selectedMatch) {
      return null;
    }

    const lastUpdated = selectedMatch.last_updated ?? null;

    return {
      source: "matches-list",
      match: selectedMatch,
      data_freshness: {
        source: "matches-list",
        provider: "RubyBets",
        from_cache: true,
        updated_at: lastUpdated,
        last_updated: lastUpdated,
        ttl_minutes: 0,
      },
    };
  }

  // Charge chaque bloc du match indépendamment pour afficher la fiche sans attendre l’appel le plus lent.
  function handleSelectMatch(matchId: number) {
    const requestId = selectedMatchLoadRequestId.current + 1;
    const competitionCode = selectedCompetition;
    const optimisticMatchDetails = buildOptimisticMatchDetails(matchId);

    selectedMatchLoadRequestId.current = requestId;
    setCurrentScreen("match-details");

    setSelectedMatchDetails(optimisticMatchDetails);
    setSelectedMatchContext(null);
    setSelectedMatchAnalysis(null);
    setSelectedMatchPredictions(null);
    setSelectedMatchLineups(null);
    setSelectedMatchNewsContext(null);
    setSelectedNationalMlPrediction(null);
    setSelectedTeamHistory(null);
    setSelectedMatchAdvancedStats(null);
    setSelectedV19H2HAnalysis(null);
    setSelectedV19ProductPrediction(null);

    setMatchDetailsStatus("Chargement du détail du match...");
    setMatchContextStatus("Chargement du contexte avant-match...");
    setMatchAnalysisStatus("Chargement de l’analyse pré-match...");
    setMatchPredictionsStatus("Chargement des prédictions...");
    setMatchLineupsStatus("Chargement des compositions probables...");
    setMatchNewsContextStatus("Chargement des actualités contextuelles...");
    setMatchAdvancedStatsStatus("Statistiques avancées prêtes à être chargées");
    setV19H2HStatus("Chargement de l’analyse H2H V19...");
    setV19ProductStatus("Chargement de la décision produit V19...");

    void getMatchDetails(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchDetails(data);
        setMatchDetailsStatus("Détail du match chargé");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        if (!optimisticMatchDetails) {
          setSelectedMatchDetails(null);
        }
        setMatchDetailsStatus("Impossible de charger le détail complet du match");
      });

    void getMatchContext(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchContext(data);
        setMatchContextStatus("Contexte avant-match chargé");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchContext(null);
        setMatchContextStatus("Impossible de charger le contexte avant-match");
      });

    void getMatchAnalysis(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchAnalysis(data);
        setMatchAnalysisStatus("Analyse pré-match chargée");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchAnalysis(null);
        setMatchAnalysisStatus("Impossible de charger l’analyse pré-match");
      });

    void getMatchPredictions(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchPredictions(data);
        setMatchPredictionsStatus("Prédictions chargées");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchPredictions(null);
        setMatchPredictionsStatus("Impossible de charger les prédictions");
      });

    void getMatchLineups(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchLineups(data);
        setMatchLineupsStatus("Compositions chargées");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchLineups(null);
        setMatchLineupsStatus("Impossible de charger les compositions");
      });

    void getMatchNewsContext(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchNewsContext(data);
        setMatchNewsContextStatus("Actualités contextuelles chargées");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchNewsContext(null);
        setMatchNewsContextStatus("Impossible de charger les actualités contextuelles");
      });

    void getNationalDynamicPredictionByRubyBetsMatchId(matchId)
      .then((data) => {
        if (isCurrentSelectedMatchRequest(requestId)) {
          setSelectedNationalMlPrediction(data);
        }
      })
      .catch(() => {
        if (isCurrentSelectedMatchRequest(requestId)) {
          setSelectedNationalMlPrediction(null);
        }
      });

    void getMatchTeamHistory(matchId)
      .then((data) => {
        if (isCurrentSelectedMatchRequest(requestId)) {
          setSelectedTeamHistory(data);
        }
      })
      .catch(() => {
        if (isCurrentSelectedMatchRequest(requestId)) {
          setSelectedTeamHistory(null);
        }
      });

    void getV19H2HAnalysis(matchId, competitionCode)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedV19H2HAnalysis(data);
        setV19H2HStatus("Analyse H2H V19 chargée");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedV19H2HAnalysis(null);
        setV19H2HStatus("Analyse H2H V19 indisponible pour ce match");
      });

    void getV19ProductPrediction(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedV19ProductPrediction(data);
        setV19ProductStatus("Décision produit V19 chargée");
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedV19ProductPrediction(null);
        setV19ProductStatus("Décision produit V19 indisponible pour ce match");
      });
  }

  // Charge les statistiques avancées uniquement lorsque l’utilisateur ouvre l’onglet Analyse détaillée.
  function handleLoadMatchAdvancedStats(matchId: number) {
    if (
      selectedMatchAdvancedStats?.match_id === matchId ||
      matchAdvancedStatsStatus === "Chargement des statistiques avancées..."
    ) {
      return;
    }

    const requestId = selectedMatchLoadRequestId.current;
    setMatchAdvancedStatsStatus("Chargement des statistiques avancées...");

    void getMatchAdvancedStats(matchId)
      .then((data) => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchAdvancedStats(data);
        setMatchAdvancedStatsStatus(
          data.status === "partial"
            ? "Statistiques avancées partielles chargées"
            : data.status === "unavailable"
              ? "Statistiques avancées indisponibles"
              : "Statistiques avancées chargées"
        );
      })
      .catch(() => {
        if (!isCurrentSelectedMatchRequest(requestId)) {
          return;
        }

        setSelectedMatchAdvancedStats(null);
        setMatchAdvancedStatsStatus("Impossible de charger les statistiques avancées");
      });
  }

  // Génère une sélection V19 à partir des identifiants des matchs actuellement chargés.
  function handleGenerateMultiMatchRecommendation() {
    const matchIds = matches.map((match) => match.id);
    const profileMapping: Record<
      "low" | "medium" | "high",
      V19SelectionProfile
    > = {
      low: "LOW",
      medium: "MEDIUM",
      high: "HIGH",
    };

    if (matchIds.length === 0) {
      setMultiMatchRecommendation(null);
      setMultiMatchStatus(
        "Aucun match disponible pour générer une sélection V19"
      );
      return;
    }

    setMultiMatchStatus("Génération de la sélection V19...");

    getV19MultiMatchSelection(
      matchIds,
      recommendationMatchCount,
      profileMapping[recommendationSelectionProfile]
    )
      .then((data) => {
        setMultiMatchRecommendation(data);
        setMultiMatchStatus("Sélection V19 générée");
      })
      .catch(() => {
        setMultiMatchRecommendation(null);
        setMultiMatchStatus("Impossible de générer la sélection V19");
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
          onRefresh={refreshSelectedCompetitionMatches}
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
          matchAdvancedStats={selectedMatchAdvancedStats}
          matchLineups={selectedMatchLineups}
          matchNewsContext={selectedMatchNewsContext}
          teamHistory={selectedTeamHistory}
          v19H2HAnalysis={selectedV19H2HAnalysis}
          v19ProductPrediction={selectedV19ProductPrediction}
          matchDetailsStatus={matchDetailsStatus}
          matchContextStatus={matchContextStatus}
          matchAnalysisStatus={matchAnalysisStatus}
          matchAdvancedStatsStatus={matchAdvancedStatsStatus}
          matchLineupsStatus={matchLineupsStatus}
          matchNewsContextStatus={matchNewsContextStatus}
          v19H2HStatus={v19H2HStatus}
          v19ProductStatus={v19ProductStatus}
          onRequestAdvancedStats={handleLoadMatchAdvancedStats}
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
          v19ProductPrediction={selectedV19ProductPrediction}
          matchDetails={selectedMatchDetails}
          matchContext={selectedMatchContext}
          v19ProductStatus={v19ProductStatus}
          onNavigate={setCurrentScreen}
        />
      );
    }

    if (currentScreen === "recommendation") {
      return (
        <RecommendationScreen
          matches={matches}
          activeCompetitionLabel={
            competitions.find(
              (competition) => competition.code === selectedCompetition
            )?.name ?? selectedCompetition
          }
          recommendationMatchCount={recommendationMatchCount}
          recommendationSelectionProfile={recommendationSelectionProfile}
          multiMatchRecommendation={multiMatchRecommendation}
          multiMatchStatus={multiMatchStatus}
          onChangeMatchCount={setRecommendationMatchCount}
          onChangeSelectionProfile={setRecommendationSelectionProfile}
          onGenerateRecommendation={handleGenerateMultiMatchRecommendation}
        />
      );
    }

    if (currentScreen === "archives") {
      return <ArchivesScreen />;
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
// ├── charge aussi /analysis, /advanced-stats à la demande, /lineups, /news-context, /team-history, le H2H V19, la décision produit V19 et le modèle national
// ├── transmet la décision produit V19 à MatchDetailsScreen.tsx et PredictionsScreen.tsx sans exposer les données internes de marché
// ├── pilote la navigation via currentScreen
// ├── utilise AppShell.tsx pour structurer l’application
// ├── peut transmettre StatusPanel.tsx à AppShell.tsx uniquement en mode debug
// ├── affiche les écrans du dossier screens/ selon l’écran actif
// ├── sélectionne automatiquement la première compétition disposant de matchs lorsque la compétition demandée est vide
// ├── ignore les réponses devenues obsolètes lors d’un changement rapide de compétition ou de match
// ├── affiche immédiatement le match depuis la liste puis hydrate chaque bloc API indépendamment
// ├── branche l’écran Sélection sur la route publique V19 à partir des matchs déjà chargés
// └── affiche l’écran Archives avec données mockées avant création du backend dédié
