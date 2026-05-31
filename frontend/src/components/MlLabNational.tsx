// Ce fichier affiche le Lab ML national experimental.
// Il permet de tester une prediction nationale V18.3.3 par clean_match_id sans remplacer les predictions officielles RubyBets.

import { useState } from "react";
import type { FormEvent } from "react";
import { getV1833PredictionByMatchId } from "../services/api";
import type {
  V1833MatchMetadata,
  V1833MatchPredictionResponse,
  V1833SelectorResult,
} from "../models/rubybets";

// Cette fonction formate une valeur numerique en pourcentage lisible.
function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "Non disponible";
  }

  return `${(value * 100).toFixed(1)} %`;
}

// Cette fonction transforme le marche technique en libelle lisible.
function formatSelectedMarket(value: string) {
  const labels: Record<string, string> = {
    STRICT_1X2: "1X2 strict",
    DOUBLE_CHANCE: "Double chance",
    OVER_1_5: "Plus de 1,5 but",
    OVER_2_5: "Plus de 2,5 buts",
    BTTS: "Les deux equipes marquent",
    ABSTAIN: "Abstention",
  };

  return labels[value] ?? value;
}

// Cette fonction transforme la prediction technique en libelle comprehensible.
function formatSelectedPrediction(
  result: V1833SelectorResult,
  match: V1833MatchMetadata
) {
  const prediction = result.selected_prediction;

  if (!prediction || result.status === "ABSTAIN") {
    return "Abstention recommandee";
  }

  const labels: Record<string, string> = {
    TEAM_A_WIN: `Victoire ${match.team_a_name}`,
    TEAM_B_WIN: `Victoire ${match.team_b_name}`,
    DRAW: "Match nul",
    TEAM_A_OR_DRAW: `${match.team_a_name} ou match nul`,
    TEAM_B_OR_DRAW: `${match.team_b_name} ou match nul`,
    TEAM_A_OR_TEAM_B: `${match.team_a_name} ou ${match.team_b_name}`,
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
    high: "Eleve",
  };

  return labels[value] ?? value;
}

// Ce composant affiche les metadonnees du match issu du CSV V18.3 global.
function LabMatchCard({ match }: { match: V1833MatchMetadata }) {
  return (
    <article className="rb-prediction-side-card">
      <p className="rb-prediction-kicker">Match reel du CSV 348</p>
      <h3>
        {match.team_a_name} vs {match.team_b_name}
      </h3>

      <div className="rb-prediction-global-tags">
        <span>
          Competition <strong>{match.competition_name}</strong>
        </span>
        <span>
          Code <strong>{match.competition_code}</strong>
        </span>
        <span>
          Saison <strong>{match.season}</strong>
        </span>
        <span>
          ID <strong>{match.clean_match_id}</strong>
        </span>
      </div>
    </article>
  );
}

// Ce composant affiche le resultat du selecteur V18.3.3.
function LabSelectorResultCard({
  response,
}: {
  response: V1833MatchPredictionResponse;
}) {
  const { match, selector_result: result } = response;

  return (
    <section className="rb-prediction-main-section">
      <div className="rb-prediction-section-header">
        <div>
          <p className="rb-prediction-kicker">Resultat experimental</p>
          <h3>Selection V18.3.3 strict reliability</h3>
          <p>
            Ce resultat provient du laboratoire ML national. Il ne remplace pas
            les predictions officielles RubyBets.
          </p>
        </div>

        <span className="rb-prediction-soft-badge">
          {result.status === "RECOMMEND" ? "Recommandation" : "Abstention"}
        </span>
      </div>

      <div className="rb-prediction-card-grid">
        <article className="rb-prediction-main-card">
          <div className="rb-prediction-main-card__header">
            <div>
              <h3>Marche selectionne</h3>
              <span>Choix du selecteur</span>
            </div>
            <span>◎</span>
          </div>

          <div className="rb-prediction-main-card__highlight">
            <span>Marche</span>
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
              <h3>Prediction</h3>
              <span>Lecture utilisateur</span>
            </div>
            <span>▣</span>
          </div>

          <div className="rb-prediction-main-card__highlight">
            <span>Sortie</span>
            <strong>{formatSelectedPrediction(result, match)}</strong>
          </div>

          <p>
            Confiance selectionnee :{" "}
            <strong>{formatPercent(result.selected_confidence)}</strong>
          </p>

          <div className="rb-prediction-card-tags">
            <span>Profil {result.selector_profile}</span>
            <span>Scope experimental</span>
          </div>
        </article>

        <article className="rb-prediction-main-card">
          <div className="rb-prediction-main-card__header">
            <div>
              <h3>Reference V18.3.3</h3>
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
            Lignes selectionnees :{" "}
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
          <h3>Lab experimental uniquement</h3>
          <p>{response.responsible_note}</p>
          <p>{result.responsible_note}</p>
        </div>
      </section>
    </section>
  );
}

// Ce composant permet de saisir un clean_match_id et d'appeler la route experimentale V18.3.3.
function MlLabNational() {
  const [cleanMatchId, setCleanMatchId] = useState<string>("7789");
  const [statusMessage, setStatusMessage] = useState<string>(
    "Saisis un clean_match_id puis lance le test experimental."
  );
  const [response, setResponse] =
    useState<V1833MatchPredictionResponse | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Cette fonction lance l'appel API experimental vers le backend.
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedMatchId = cleanMatchId.trim();

    if (!trimmedMatchId) {
      setResponse(null);
      setStatusMessage("Le clean_match_id est obligatoire.");
      return;
    }

    setIsLoading(true);
    setStatusMessage("Chargement du resultat V18.3.3...");

    getV1833PredictionByMatchId(trimmedMatchId)
      .then((data) => {
        setResponse(data);
        setStatusMessage("Resultat V18.3.3 charge avec succes.");
      })
      .catch((error: unknown) => {
        setResponse(null);
        setStatusMessage(
          error instanceof Error
            ? error.message
            : "Impossible de charger le resultat experimental V18.3.3."
        );
      })
      .finally(() => {
        setIsLoading(false);
      });
  }

  return (
    <div className="rb-predictions-screen rb-predictions-screen--mockup">
      <header className="rb-prediction-topbar">
        <h2>Lab ML national</h2>
      </header>

      <section className="rb-prediction-hero rb-prediction-hero--empty">
        <p className="rb-prediction-kicker">Experimental</p>
        <h2>Test du selecteur national V18.3.3</h2>
        <p>
          Cet espace permet de tester le selecteur strict reliability sur un
          match reel du fichier CSV 348. Il ne remplace pas les predictions
          officielles RubyBets.
        </p>
      </section>

      <main className="rb-prediction-dashboard-grid">
        <div className="rb-prediction-dashboard-grid__main">
          <section className="rb-prediction-main-section">
            <div className="rb-prediction-section-header">
              <div>
                <p className="rb-prediction-kicker">Recherche par match</p>
                <h3>clean_match_id</h3>
                <p>
                  Exemple valide deja teste : <strong>7789</strong>.
                </p>
              </div>

              <span className="rb-prediction-soft-badge">Lab backend</span>
            </div>

            <form onSubmit={handleSubmit}>
              <label htmlFor="v18-3-3-clean-match-id">
                Identifiant du match
              </label>

              <input
                id="v18-3-3-clean-match-id"
                type="text"
                value={cleanMatchId}
                onChange={(event) => setCleanMatchId(event.target.value)}
                placeholder="Exemple : 7789"
              />

              <button type="submit" disabled={isLoading}>
                {isLoading ? "Chargement..." : "Tester V18.3.3"}
              </button>
            </form>

            <div className="rb-prediction-message">
              <p>{statusMessage}</p>
            </div>
          </section>

          {response ? <LabSelectorResultCard response={response} /> : null}
        </div>

        <aside className="rb-prediction-dashboard-grid__side">
          {response ? (
            <LabMatchCard match={response.match} />
          ) : (
            <article className="rb-prediction-side-card">
              <p className="rb-prediction-kicker">Aucune selection chargee</p>
              <h3>En attente de test</h3>
              <p>
                Lance un appel avec un clean_match_id present dans le CSV 348
                pour afficher le resultat du selecteur.
              </p>
            </article>
          )}

          <article className="rb-prediction-side-card">
            <p className="rb-prediction-kicker">Important</p>
            <h3>Non officiel</h3>
            <p>
              V18.3.3 reste un laboratoire ML experimental. Le parcours officiel
              RubyBets continue d'utiliser les routes de predictions existantes.
            </p>
          </article>
        </aside>
      </main>

      <p className="rb-prediction-footer-note">
        Outil d'aide analytique avant-match. Aucune prise de pari reelle,
        aucune promesse de resultat sportif.
      </p>
    </div>
  );
}

export default MlLabNational;

// Schema de communication :
// MlLabNational.tsx
// ├── appelle getV18.3.3PredictionByMatchId dans services/api.ts
// ├── utilise les types V18.3.3 definis dans models/rubybets.ts
// ├── affiche une zone Lab ML nationale experimentale separee des predictions officielles
// └── est rendu par App.tsx via l'ecran lab-ml-v18.3.3