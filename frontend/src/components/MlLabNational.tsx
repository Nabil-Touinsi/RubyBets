// Ce fichier affiche le bloc ML national expérimental V18.3.4 dans l’écran Prédictions.
// Il calcule automatiquement le match sélectionné quand il est compatible, sans remplacer les prédictions officielles RubyBets.

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  getV1833DynamicPredictionByRubyBetsMatchId,
  getV1833PredictionByMatchId,
} from "../services/api";
import type {
  Match,
  V1833MatchMetadata,
  V1833MatchPredictionResponse,
  V1833SelectorResult,
} from "../models/rubybets";
import { getTeamDisplayName, hasKnownTeams } from "../helpers/displayText";

type MlLabNationalProps = {
  selectedMatch: Match | null;
};

// Cette fonction formate une valeur numérique en pourcentage lisible.
function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "Non disponible";
  }

  return `${(value * 100).toFixed(1)} %`;
}

// Cette fonction transforme le marché technique en libellé lisible.
function formatSelectedMarket(value: string) {
  const labels: Record<string, string> = {
    STRICT_1X2: "1X2 strict",
    DOUBLE_CHANCE: "Double chance",
    OVER_1_5: "Plus de 1,5 but",
    OVER_2_5: "Plus de 2,5 buts",
    BTTS: "Les deux équipes marquent",
    ABSTAIN: "Abstention",
  };

  return labels[value] ?? value;
}

// Cette fonction transforme la prédiction technique en libellé compréhensible.
function formatSelectedPrediction(
  result: V1833SelectorResult,
  match: V1833MatchMetadata
) {
  const prediction = result.selected_prediction;
  const teamAName = match.team_a_name ?? "Équipe A";
  const teamBName = match.team_b_name ?? "Équipe B";

  if (!prediction || result.status === "ABSTAIN") {
    return "Abstention recommandée";
  }

  const labels: Record<string, string> = {
    TEAM_A_WIN: `Victoire ${teamAName}`,
    TEAM_B_WIN: `Victoire ${teamBName}`,
    DRAW: "Match nul",
    TEAM_A_OR_DRAW: `${teamAName} ou match nul`,
    TEAM_B_OR_DRAW: `${teamBName} ou match nul`,
    TEAM_A_OR_TEAM_B: `${teamAName} ou ${teamBName}`,
    YES: "Oui",
    NO: "Non",
    OVER: "Over",
    UNDER: "Under",
  };

  return labels[prediction] ?? prediction;
}

// Cette fonction renvoie un texte court selon le niveau de risque.
function formatRiskLevel(value: string) {
  const labels: Record<string, string> = {
    low: "Faible",
    medium: "Moyen",
    high: "Élevé",
    none: "Aucun",
  };

  return labels[value] ?? value;
}

// Cette fonction indique si la réponse contient vraiment un résultat sélectionnable.
function isComputedResponse(response: V1833MatchPredictionResponse | null) {
  return Boolean(response && response.status === "computed" && response.selector_result);
}

// Ce composant affiche les métadonnées du match analysé par V18.3.4.
function LabMatchCard({
  match,
  title,
}: {
  match: V1833MatchMetadata;
  title: string;
}) {
  return (
    <article className="rb-prediction-side-card">
      <p className="rb-prediction-kicker">{title}</p>
      <h3>
        {match.team_a_name ?? "Équipe A"} vs {match.team_b_name ?? "Équipe B"}
      </h3>

      <div className="rb-prediction-global-tags">
        <span>
          Compétition <strong>{match.competition_name ?? "Non disponible"}</strong>
        </span>
        <span>
          Code <strong>{match.competition_code ?? "N/A"}</strong>
        </span>
        <span>
          Saison <strong>{match.season ?? "N/A"}</strong>
        </span>
        <span>
          ID <strong>{match.rubybets_match_id ?? match.clean_match_id}</strong>
        </span>
      </div>
    </article>
  );
}

// Ce composant affiche un message clair quand V18.3.4 ne peut pas analyser le match sélectionné.
function LabUnavailableCard({
  response,
  selectedMatch,
}: {
  response: V1833MatchPredictionResponse | null;
  selectedMatch: Match | null;
}) {
  const reason = response?.unavailable_reason ??
    "L’analyse dynamique V18.3.4 n’est pas disponible pour ce match.";

  return (
    <article className="rb-prediction-card rb-prediction-empty-state">
      <p className="rb-prediction-kicker">Analyse ML nationale expérimentale</p>
      <h3>V18.3.4 indisponible pour ce match</h3>
      <p>{reason}</p>

      {selectedMatch ? (
        <div className="rb-prediction-card-tags">
          <span>{getTeamDisplayName(selectedMatch.home_team)}</span>
          <span>{getTeamDisplayName(selectedMatch.away_team)}</span>
          <span>{selectedMatch.competition.code}</span>
        </div>
      ) : null}
    </article>
  );
}

// Ce composant affiche le résultat du sélecteur V18.3.4 dc018.
function LabSelectorResultCard({
  response,
  title,
}: {
  response: V1833MatchPredictionResponse;
  title: string;
}) {
  const { match, selector_result: result } = response;

  if (!result) {
    return <LabUnavailableCard response={response} selectedMatch={null} />;
  }

  return (
    <section className="rb-prediction-main-section">
      <div className="rb-prediction-section-header">
        <div>
          <p className="rb-prediction-kicker">{title}</p>
          <h3>Sélection V18.3.4 dc018</h3>
          <p>
            Ce résultat provient du laboratoire ML national. Il reste séparé des
            prédictions officielles RubyBets.
          </p>
        </div>

        <span className="rb-prediction-soft-badge">
          {result.status === "RECOMMEND" ? "Signal expérimental" : "Abstention"}
        </span>
      </div>

      <div className="rb-prediction-card-grid">
        <article className="rb-prediction-main-card">
          <div className="rb-prediction-main-card__header">
            <div>
              <h3>Marché sélectionné</h3>
              <span>Choix du sélecteur</span>
            </div>
            <span>◎</span>
          </div>

          <div className="rb-prediction-main-card__highlight">
            <span>Marché</span>
            <strong>{formatSelectedMarket(result.selected_market)}</strong>
          </div>

          <p>{result.selector_rule}</p>

          <div className="rb-prediction-card-tags">
            <span>Risque {formatRiskLevel(result.risk_level)}</span>
            <span>Version {result.selector_version}</span>
          </div>
        </article>

        <article className="rb-prediction-main-card">
          <div className="rb-prediction-main-card__header">
            <div>
              <h3>Lecture expérimentale</h3>
              <span>Sortie utilisateur</span>
            </div>
            <span>▣</span>
          </div>

          <div className="rb-prediction-main-card__highlight">
            <span>Sortie</span>
            <strong>{formatSelectedPrediction(result, match)}</strong>
          </div>

          <p>
            Confiance sélectionnée :{" "}
            <strong>{formatPercent(result.selected_confidence)}</strong>
          </p>

          <div className="rb-prediction-card-tags">
            <span>Profil {result.selector_profile}</span>
            <span>Scope non officiel</span>
          </div>
        </article>

        <article className="rb-prediction-main-card">
          <div className="rb-prediction-main-card__header">
            <div>
              <h3>Référence V18.3.4</h3>
              <span>Performance globale test</span>
            </div>
            <span>△</span>
          </div>

          <div className="rb-prediction-main-card__highlight">
            <span>Reliability</span>
            <strong>{formatPercent(result.reference_reliability)}</strong>
          </div>

          <p>
            Coverage : <strong>{formatPercent(result.reference_coverage)}</strong>
            <br />
            Lignes sélectionnées :{" "}
            <strong>{result.reference_selected_rows}</strong>
          </p>

          <div className="rb-prediction-card-tags">
            <span>
              Double chance {formatPercent(result.reference_double_chance_share)}
            </span>
          </div>
        </article>
      </div>

      <section className="rb-prediction-global-reading">
        <div className="rb-prediction-global-reading__icon">!</div>

        <div>
          <p className="rb-prediction-kicker">Cadre responsable</p>
          <h3>Expérimentation uniquement</h3>
          <p>{response.responsible_note}</p>
          <p>{result.responsible_note}</p>
        </div>
      </section>
    </section>
  );
}

// Ce composant affiche les cartes de contexte du bloc expérimental dynamique.
function DynamicContextCards({
  response,
}: {
  response: V1833MatchPredictionResponse | null;
}) {
  return (
    <div className="rb-prediction-card-grid">
      {response?.match ? (
        <LabMatchCard match={response.match} title="Match sélectionné analysé" />
      ) : (
        <article className="rb-prediction-side-card">
          <p className="rb-prediction-kicker">Match sélectionné</p>
          <h3>En attente</h3>
          <p>
            Sélectionne un match national compatible pour lancer l’analyse
            dynamique V18.3.4.
          </p>
        </article>
      )}

      <article className="rb-prediction-side-card">
        <p className="rb-prediction-kicker">Mode</p>
        <h3>Dynamique expérimental</h3>
        <p>
          Le backend construit les features du match sélectionné, charge les
          modèles sauvegardés V18.3 et applique le sélecteur V18.3.4 dc018.
        </p>
      </article>

      <article className="rb-prediction-side-card">
        <p className="rb-prediction-kicker">Limite</p>
        <h3>Non officiel</h3>
        <p>
          Ce bloc ne remplace pas les prédictions RubyBets officielles et ne
          garantit aucun résultat sportif.
        </p>
      </article>
    </div>
  );
}

// Ce composant permet de tester un clean_match_id historique sans le confondre avec le match sélectionné.
function HistoricalCleanMatchTest() {
  const [cleanMatchId, setCleanMatchId] = useState<string>("7789");
  const [statusMessage, setStatusMessage] = useState<string>(
    "Test technique séparé : aucun résultat historique n’est chargé."
  );
  const [response, setResponse] =
    useState<V1833MatchPredictionResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Cette fonction lance l’appel API historique vers le CSV 348.
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedMatchId = cleanMatchId.trim();

    if (!trimmedMatchId) {
      setResponse(null);
      setStatusMessage("Le clean_match_id est obligatoire pour le test historique.");
      return;
    }

    setIsLoading(true);
    setStatusMessage("Chargement du test historique V18.3.3...");

    getV1833PredictionByMatchId(trimmedMatchId)
      .then((data) => {
        setResponse(data);
        setStatusMessage(
          "Test historique chargé. Il ne correspond pas forcément au match sélectionné."
        );
      })
      .catch((error: unknown) => {
        setResponse(null);
        setStatusMessage(
          error instanceof Error
            ? error.message
            : "Impossible de charger le test historique V18.3.3."
        );
      })
      .finally(() => {
        setIsLoading(false);
      });
  }

  return (
    <section className="rb-prediction-main-section">
      <div className="rb-prediction-section-header">
        <div>
          <p className="rb-prediction-kicker">Test technique historique</p>
          <h3>clean_match_id CSV 348</h3>
          <p>
            Cette zone sert uniquement à vérifier une ligne historique du CSV 348 avec V18.3.3.
            Elle est séparée du match actuellement sélectionné, qui utilise V18.3.4 dc018.
          </p>
        </div>

        <span className="rb-prediction-soft-badge">Lab manuel</span>
      </div>

      <form onSubmit={handleSubmit}>
        <label htmlFor="v18-3-3-clean-match-id">Identifiant historique</label>

        <input
          id="v18-3-3-clean-match-id"
          type="text"
          value={cleanMatchId}
          onChange={(event) => setCleanMatchId(event.target.value)}
          placeholder="Exemple : 7789"
        />

        <button type="submit" disabled={isLoading}>
          {isLoading ? "Chargement..." : "Tester un match historique"}
        </button>
      </form>

      <div className="rb-prediction-message">
        <p>{statusMessage}</p>
      </div>

      {response && isComputedResponse(response) ? (
        <LabSelectorResultCard response={response} title="Résultat historique" />
      ) : null}
    </section>
  );
}

// Ce composant affiche l’analyse V18.3.4 dynamique pour le match sélectionné.
function MlLabNational({ selectedMatch }: MlLabNationalProps) {
  const [dynamicStatus, setDynamicStatus] = useState<string>(
    "En attente d’un match national compatible."
  );
  const [dynamicResponse, setDynamicResponse] =
    useState<V1833MatchPredictionResponse | null>(null);
  const [isDynamicLoading, setIsDynamicLoading] = useState<boolean>(false);

  // Cette fonction lance automatiquement l’inférence dynamique quand le match sélectionné change.
  useEffect(() => {
    if (!selectedMatch) {
      setDynamicResponse(null);
      setDynamicStatus("Sélectionne un match pour lancer V18.3.4 dynamique.");
      return;
    }

    if (!hasKnownTeams(selectedMatch)) {
      setDynamicResponse(null);
      setDynamicStatus(
        "Les équipes ne sont pas encore connues : V18.3.4 dynamique est indisponible."
      );
      return;
    }

    setIsDynamicLoading(true);
    setDynamicStatus("Calcul dynamique V18.3.4 en cours pour le match sélectionné...");

    getV1833DynamicPredictionByRubyBetsMatchId(selectedMatch.id)
      .then((data) => {
        setDynamicResponse(data);
        setDynamicStatus(
          data.status === "computed"
            ? "Analyse V18.3.4 calculée pour le match sélectionné."
            : "V18.3.4 dynamique indisponible pour ce match."
        );
      })
      .catch((error: unknown) => {
        setDynamicResponse(null);
        setDynamicStatus(
          error instanceof Error
            ? error.message
            : "Impossible de calculer V18.3.4 pour ce match."
        );
      })
      .finally(() => {
        setIsDynamicLoading(false);
      });
  }, [selectedMatch]);

  return (
    <section className="rb-prediction-main-section">
      <div className="rb-prediction-section-header">
        <div>
          <p className="rb-prediction-kicker">Bloc expérimental séparé</p>
          <h3>Analyse ML nationale expérimentale</h3>
          <p>
            Ce bloc calcule V18.3.4 sur le match national sélectionné quand les
            données nécessaires sont disponibles. Il ne remplace pas les
            prédictions officielles RubyBets.
          </p>
        </div>

        <span className="rb-prediction-soft-badge">
          {isDynamicLoading ? "Calcul en cours" : "V18.3.4 non officiel"}
        </span>
      </div>

      <div className="rb-prediction-message">
        <p>{dynamicStatus}</p>
      </div>

      {dynamicResponse && isComputedResponse(dynamicResponse) ? (
        <LabSelectorResultCard
          response={dynamicResponse}
          title="Résultat dynamique du match sélectionné"
        />
      ) : (
        <LabUnavailableCard response={dynamicResponse} selectedMatch={selectedMatch} />
      )}

      <DynamicContextCards response={dynamicResponse} />
      <HistoricalCleanMatchTest />
    </section>
  );
}

export default MlLabNational;

// Schéma de communication :
// MlLabNational.tsx
// ├── reçoit selectedMatch depuis PredictionsScreen.tsx
// ├── appelle getV1833DynamicPredictionByRubyBetsMatchId dans services/api.ts
// ├── garde getV1833PredictionByMatchId uniquement comme test historique séparé
// ├── utilise les types V18.3.3/V18.3.4 définis dans models/rubybets.ts
// └── reste expérimental, séparé du moteur officiel RubyBets
