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
  formatMatchStatus,
  formatPredictionStatus,
  formatPriority,
  formatRiskLevel,
} from "./helpers/displayText";
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

      {/* Statuts de chargement visibles pendant les tests du MVP. */}
      <p className="api-status">{apiStatus}</p>
      <p className="api-status">{competitionsStatus}</p>
      <p className="api-status">{matchesStatus}</p>
      <p className="api-status">{matchDetailsStatus}</p>
      <p className="api-status">{matchContextStatus}</p>
      <p className="api-status">{matchAnalysisStatus}</p>
      <p className="api-status">{matchPredictionsStatus}</p>
      <p className="api-status">{multiMatchStatus}</p>
      <p className="api-status">{glossaryStatus}</p>
      <p className="api-status">{responsibleInfoStatus}</p>

      <section>
        <h2>Compétitions MVP</h2>

        {competitions.length === 0 ? (
          <p>Aucune compétition disponible pour le moment.</p>
        ) : (
          <div>
            {competitions.map((competition) => (
              <button
                key={competition.id}
                type="button"
                onClick={() => setSelectedCompetition(competition.code)}
              >
                {competition.name} ({competition.code})
              </button>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Matchs à venir — {selectedCompetition}</h2>

        {matches.length === 0 ? (
          <p>Aucun match disponible pour cette compétition.</p>
        ) : (
          <ul>
            {matches.map((match) => (
              <li key={match.id}>
                <button type="button" onClick={() => handleSelectMatch(match.id)}>
                  <strong>{match.home_team.name}</strong> vs{" "}
                  <strong>{match.away_team.name}</strong>
                </button>
                <br />
                <span>
                  {match.competition.name} — Journée {match.matchday} —{" "}
                  {new Date(match.utc_date).toLocaleString("fr-FR")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>Recommandation multi-matchs</h2>

        <p>
          Cette sélection est générée à partir des matchs disponibles, des
          prédictions calculées et du niveau de risque choisi.
        </p>

        <label htmlFor="match-count">Nombre de matchs : </label>
        <select
          id="match-count"
          value={recommendationMatchCount}
          onChange={(event) => setRecommendationMatchCount(Number(event.target.value))}
        >
          <option value={1}>1</option>
          <option value={2}>2</option>
          <option value={3}>3</option>
          <option value={4}>4</option>
          <option value={5}>5</option>
        </select>

        <br />

        <label htmlFor="risk-level">Niveau de risque : </label>
        <select
          id="risk-level"
          value={recommendationRiskLevel}
          onChange={(event) =>
            setRecommendationRiskLevel(
              event.target.value as "low" | "medium" | "high"
            )
          }
        >
          <option value="low">Faible</option>
          <option value="medium">Moyen</option>
          <option value="high">Élevé</option>
        </select>

        <br />

        <button type="button" onClick={handleGenerateMultiMatchRecommendation}>
          Générer la recommandation
        </button>

        {multiMatchRecommendation && (
          <div>
            <h3>Sélection recommandée</h3>

            <p>
              Compétition : {multiMatchRecommendation.request.competition_code} —
              Niveau de risque : {formatRiskLevel(multiMatchRecommendation.request.risk_level)} —
              Matchs sélectionnés : {multiMatchRecommendation.selected_count}
            </p>

            {multiMatchRecommendation.recommendations.map((item) => (
              <article key={item.match.id}>
                <h4>
                  {item.match.home_team.name} vs {item.match.away_team.name}
                </h4>

                <p>
                  {item.match.competition.name} — Journée {item.match.matchday} —{" "}
                  {new Date(item.match.utc_date).toLocaleString("fr-FR")}
                </p>

                <p>
                  Recommandation :{" "}
                  <strong>{item.selected_prediction.label}</strong>
                </p>

                <p>Marché analysé : {item.selected_prediction.market}</p>
                <p>
                  Confiance :{" "}
                  {formatConfidenceLevel(item.selected_prediction.confidence)}
                </p>
                <p>Risque : {formatRiskLevel(item.selected_prediction.risk)}</p>
                <p>Score de sélection : {item.selection_score}</p>
                <p>Justification : {item.selected_prediction.justification}</p>
              </article>
            ))}

            <h4>Logique de sélection</h4>
            <p>{multiMatchRecommendation.selection_logic.description}</p>

            <h4>Limites</h4>
            <ul>
              {cleanTextItems(multiMatchRecommendation.limits).map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>

            <p>
              Méthode : {multiMatchRecommendation.method} — Source :{" "}
              {multiMatchRecommendation.source}
            </p>
          </div>
        )}
      </section>

      <section>
        <h2>Glossaire</h2>

        <p>
          Définitions pédagogiques des principaux termes utilisés dans RubyBets.
        </p>

        {glossary && glossary.items.length > 0 ? (
          <div>
            <p>Nombre de termes : {glossary.count}</p>

            {glossary.items.map((item) => (
              <article key={item.slug}>
                <h3>{item.term}</h3>
                <p>Catégorie : {item.category}</p>
                <p>{item.definition}</p>
              </article>
            ))}
          </div>
        ) : (
          <p>Aucun terme disponible pour le moment.</p>
        )}
      </section>

      <section>
        <h2>Informations responsables</h2>

        <p>
          Cette section rappelle les limites de RubyBets et son positionnement
          comme outil d’aide à la décision.
        </p>

        {responsibleInfo ? (
          <div>
            <p>Nombre de messages : {responsibleInfo.count}</p>

            <p>
              Positionnement :{" "}
              <strong>{responsibleInfo.summary.product_positioning}</strong>
            </p>

            <p>
              Pari réel activé :{" "}
              {responsibleInfo.summary.real_betting_enabled ? "Oui" : "Non"}
            </p>

            <p>
              Analyse live activée :{" "}
              {responsibleInfo.summary.live_analysis_enabled ? "Oui" : "Non"}
            </p>

            <p>
              Données réelles utilisées :{" "}
              {responsibleInfo.summary.uses_real_data ? "Oui" : "Non"}
            </p>

            <p>
              Garantie de résultat :{" "}
              {responsibleInfo.summary.guarantees_result ? "Oui" : "Non"}
            </p>

            {responsibleInfo.items.map((item) => (
              <article key={`${item.type}-${item.title}`}>
                <h3>{item.title}</h3>
                <p>Priorité : {formatPriority(item.priority)}</p>
                <p>{item.content}</p>
              </article>
            ))}
          </div>
        ) : (
          <p>Aucune information responsable disponible pour le moment.</p>
        )}
      </section>

      {selectedMatchDetails && (
        <section>
          <h2>Fiche détail match</h2>

          <h3>
            {selectedMatchDetails.match.home_team.name} vs{" "}
            {selectedMatchDetails.match.away_team.name}
          </h3>

          <p>
            Compétition : {selectedMatchDetails.match.competition.name} (
            {selectedMatchDetails.match.competition.code})
          </p>

          <p>
            Date :{" "}
            {new Date(selectedMatchDetails.match.utc_date).toLocaleString("fr-FR")}
          </p>

          <p>Statut : {formatMatchStatus(selectedMatchDetails.match.status)}</p>
          <p>Journée : {selectedMatchDetails.match.matchday}</p>
          <p>Source : {selectedMatchDetails.source}</p>
          <p>
            Dernière mise à jour :{" "}
            {selectedMatchDetails.data_freshness.last_updated}
          </p>
        </section>
      )}

      {selectedMatchContext && (
        <section>
          <h2>Contexte avant-match</h2>

          <h3>{selectedMatchContext.context.summary.title}</h3>

          <ul>
            {cleanTextItems(selectedMatchContext.context.summary.main_facts).map(
              (fact) => (
                <li key={fact}>{fact}</li>
              )
            )}
          </ul>

          <h4>Classement des équipes</h4>

          <div>
            {selectedMatchContext.context.home_team_standing && (
              <article>
                <h5>{selectedMatchContext.context.home_team_standing.team.name}</h5>
                <p>
                  Position :{" "}
                  {selectedMatchContext.context.home_team_standing.position}
                </p>
                <p>
                  Points : {selectedMatchContext.context.home_team_standing.points}
                </p>
                <p>
                  Matchs joués :{" "}
                  {selectedMatchContext.context.home_team_standing.played_games}
                </p>
                <p>
                  Buts pour / contre :{" "}
                  {selectedMatchContext.context.home_team_standing.goals_for} /{" "}
                  {selectedMatchContext.context.home_team_standing.goals_against}
                </p>
                <p>
                  Différence de buts :{" "}
                  {selectedMatchContext.context.home_team_standing.goal_difference}
                </p>
              </article>
            )}

            {selectedMatchContext.context.away_team_standing && (
              <article>
                <h5>{selectedMatchContext.context.away_team_standing.team.name}</h5>
                <p>
                  Position :{" "}
                  {selectedMatchContext.context.away_team_standing.position}
                </p>
                <p>
                  Points : {selectedMatchContext.context.away_team_standing.points}
                </p>
                <p>
                  Matchs joués :{" "}
                  {selectedMatchContext.context.away_team_standing.played_games}
                </p>
                <p>
                  Buts pour / contre :{" "}
                  {selectedMatchContext.context.away_team_standing.goals_for} /{" "}
                  {selectedMatchContext.context.away_team_standing.goals_against}
                </p>
                <p>
                  Différence de buts :{" "}
                  {selectedMatchContext.context.away_team_standing.goal_difference}
                </p>
              </article>
            )}
          </div>
        </section>
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
