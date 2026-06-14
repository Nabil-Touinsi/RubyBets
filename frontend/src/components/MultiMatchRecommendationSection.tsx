// Ce composant affiche le générateur de sélection multi-matchs issu du modèle national RubyBets.

import type { CSSProperties } from "react";
import type { MultiMatchRecommendationResponse } from "../models/rubybets";
import {
  cleanTextItems,
  formatRiskLevel,
  getTeamInitials,
  getTeamShortName,
} from "../helpers/displayText";

type RiskLevel = "low" | "medium" | "high";

type MultiMatchRecommendationSectionProps = {
  recommendationMatchCount: number;
  recommendationRiskLevel: RiskLevel;
  multiMatchRecommendation: MultiMatchRecommendationResponse | null;
  multiMatchStatus: string;
  onChangeMatchCount: (count: number) => void;
  onChangeRiskLevel: (riskLevel: RiskLevel) => void;
  onGenerateRecommendation: () => void;
};

type RecommendationItem =
  MultiMatchRecommendationResponse["recommendations"][number];

type RecommendationTeam = RecommendationItem["match"]["home_team"];

// Cette fonction détecte l’état de génération à partir du statut existant.
function isGenerationPending(status: string) {
  return /génération|generation|chargement|loading/i.test(status);
}

// Cette fonction formate une date courte pour garder le tableau compact.
function formatShortDate(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Cette fonction retourne un nom court d’équipe.
function getTeamLabel(team: RecommendationTeam) {
  return getTeamShortName(team);
}

// Cette fonction convertit une probabilité modèle en pourcentage affichable.
function formatProbabilityPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "—";
  }

  return `${Math.round(value * 100)}%`;
}

// Cette fonction convertit une probabilité modèle en nombre utilisable par le ring CSS.
function getProbabilityPercentValue(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }

  return Math.round(value * 100);
}

// Cette fonction calcule une confiance globale à partir des selected_confidence réels du backend.
function getGlobalConfidence(
  multiMatchRecommendation: MultiMatchRecommendationResponse | null,
) {
  const recommendations = multiMatchRecommendation?.recommendations ?? [];
  const confidences = recommendations
    .map((item) => item.selected_confidence)
    .filter((value): value is number => typeof value === "number");

  if (confidences.length === 0) {
    return "—";
  }

  const total = confidences.reduce((sum, confidence) => sum + confidence, 0);
  return formatProbabilityPercent(total / confidences.length);
}

// Cette fonction retourne un libellé de marché clair pour les signaux du selector national.
function formatMarketLabel(market: string | null) {
  const labels: Record<string, string> = {
    DOUBLE_CHANCE: "Double chance",
    "1X2": "1X2",
    TEAM_A_WIN: "Victoire équipe A",
    TEAM_B_WIN: "Victoire équipe B",
    DRAW: "Match nul",
    OVER_1_5: "Plus de 1,5 but",
    OVER_2_5: "Plus de 2,5 buts",
    BTTS: "BTTS",
  };

  if (!market) {
    return "Marché à confirmer";
  }

  return labels[market] ?? market.replaceAll("_", " ");
}

// Cette fonction traduit une prédiction technique du selector en phrase utilisateur.
function formatSelectedPrediction(item: RecommendationItem) {
  const prediction = item.selected_prediction;
  const homeName = getTeamLabel(item.match.home_team);
  const awayName = getTeamLabel(item.match.away_team);

  const labels: Record<string, string> = {
    TEAM_A_WIN: `Victoire ${homeName}`,
    TEAM_B_WIN: `Victoire ${awayName}`,
    DRAW: "Match nul",
    DRAW_OR_TEAM_A: `Nul ou ${homeName}`,
    DRAW_OR_TEAM_B: `Nul ou ${awayName}`,
    TEAM_A_OR_TEAM_B: `${homeName} ou ${awayName}`,
    YES: "Oui",
    NO: "Non",
  };

  if (!prediction) {
    return "Sélection à confirmer";
  }

  return labels[prediction] ?? prediction.replaceAll("_", " ");
}

// Cette fonction retourne une lecture courte à partir du selector_result reçu du backend.
function formatSelectionSummary(item: RecommendationItem) {
  if (item.selected_market === "DOUBLE_CHANCE") {
    return "Signal prudent issu du sélecteur national";
  }

  if (item.consistency_checks?.status === "adjusted") {
    return "Signal corrigé par cohérence métier";
  }

  return "Signal ML national sélectionné";
}

// Cette fonction résume la règle du sélecteur sans surcharger le tableau.
function formatSelectorRule(item: RecommendationItem) {
  if (item.consistency_checks?.status === "adjusted") {
    return "Cohérence inter-marchés appliquée. Le signal reste encadré par le modèle national expérimental.";
  }

  return item.selector_rule || "Signal retenu par le sélecteur national expérimental.";
}

// Cette fonction prépare le message affiché quand aucune sélection n’est retournée par le backend.
function getEmptyStateContent(
  multiMatchRecommendation: MultiMatchRecommendationResponse | null,
  recommendationRiskLevel: RiskLevel,
  multiMatchStatus: string,
) {
  const requestedRiskLevel =
    multiMatchRecommendation?.request.risk_level ?? recommendationRiskLevel;

  const isBackendEmptyResponse =
    multiMatchRecommendation?.status === "empty" ||
    multiMatchRecommendation?.selected_count === 0;

  if (isBackendEmptyResponse && requestedRiskLevel === "high") {
    return {
      title: "Aucune sélection à risque élevé disponible",
      message:
        "Le modèle national n’a identifié aucun signal suffisamment cohérent pour ce niveau de risque sur les matchs actuellement disponibles.",
      hint: "Vous pouvez essayer un niveau de risque moyen ou faible.",
    };
  }

  if (isBackendEmptyResponse) {
    return {
      title: `Aucune sélection ${formatRiskLevel(requestedRiskLevel).toLowerCase()} disponible`,
      message:
        "Aucun signal compatible avec ce niveau de risque n’est disponible sur les matchs actuellement calculés.",
      hint: "Vous pouvez modifier le niveau de risque ou relancer la génération plus tard.",
    };
  }

  return {
    title: "Aucune sélection affichée",
    message: multiMatchStatus,
    hint:
      "Lancez une génération pour afficher une sélection structurée à partir des signaux déjà produits par le modèle national.",
  };
}

// Ce composant affiche un logo d’équipe avec fallback.
function TeamLogo({ team }: { team: RecommendationTeam }) {
  const teamLabel = getTeamLabel(team);

  return (
    <span className="rb-reco-team-logo" aria-label={`Logo ${teamLabel}`}>
      <span className="rb-reco-team-logo__fallback">{getTeamInitials(team)}</span>

      {team.crest ? (
        <img
          src={team.crest}
          alt=""
          loading="lazy"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
    </span>
  );
}

// Ce composant affiche les boutons segmentés du nombre de matchs.
function MatchCountSegments({
  value,
  disabled,
  onChange,
}: {
  value: number;
  disabled: boolean;
  onChange: (count: number) => void;
}) {
  const options = [2, 3, 4, 5];

  return (
    <div className="rb-reco-segment-group">
      <span>Nombre de matchs</span>
      <div>
        {options.map((option) => (
          <button
            key={option}
            type="button"
            disabled={disabled}
            className={value === option ? "rb-reco-segment--active" : ""}
            onClick={() => onChange(option)}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

// Ce composant affiche les boutons segmentés du niveau de risque.
function RiskLevelSegments({
  value,
  disabled,
  onChange,
}: {
  value: RiskLevel;
  disabled: boolean;
  onChange: (riskLevel: RiskLevel) => void;
}) {
  const options: Array<{ value: RiskLevel; label: string }> = [
    { value: "low", label: "Faible" },
    { value: "medium", label: "Moyen" },
    { value: "high", label: "Élevé" },
  ];

  return (
    <div className="rb-reco-segment-group">
      <span>Niveau de risque</span>
      <div>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={disabled}
            className={value === option.value ? "rb-reco-segment--active" : ""}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// Ce composant affiche une ligne de sélection issue du modèle national expérimental.
function RecommendationRow({ item }: { item: RecommendationItem }) {
  const confidencePercent = getProbabilityPercentValue(item.selected_confidence);
  const reliabilityLabel = formatProbabilityPercent(item.reference_reliability);
  const riskLevel = item.risk_level || "medium";

  return (
    <article className="rb-reco-table-row">
      <div className="rb-reco-table-cell rb-reco-match-cell">
        <div className="rb-reco-match-meta">
          <strong>{item.match.competition.name}</strong>
          <span>{formatShortDate(item.match.utc_date)}</span>
        </div>

        <div className="rb-reco-fixture">
          <span className="rb-reco-fixture-team rb-reco-fixture-team--home">
            <TeamLogo team={item.match.home_team} />
            <span className="rb-reco-team-name">
              {getTeamLabel(item.match.home_team)}
            </span>
          </span>

          <span className="rb-reco-vs">VS</span>

          <span className="rb-reco-fixture-team rb-reco-fixture-team--away">
            <TeamLogo team={item.match.away_team} />
            <span className="rb-reco-team-name">
              {getTeamLabel(item.match.away_team)}
            </span>
          </span>
        </div>
      </div>

      <div className="rb-reco-table-cell rb-reco-selection-cell">
        <div className="rb-reco-selection-card">
          <span className="rb-reco-market-badge rb-reco-market-badge--solo">
            {formatMarketLabel(item.selected_market)}
          </span>
          <strong>{formatSelectedPrediction(item)}</strong>
          <p>{formatSelectionSummary(item)}</p>
        </div>
      </div>

      <div className="rb-reco-table-cell rb-reco-confidence-cell">
        <span
          className="rb-reco-confidence-ring"
          style={
            { "--rb-reco-confidence": `${confidencePercent}%` } as CSSProperties
          }
        >
          {formatProbabilityPercent(item.selected_confidence)}
        </span>
        <small>Fiabilité réf. {reliabilityLabel}</small>
      </div>

      <div className="rb-reco-table-cell">
        <span className={`rb-reco-risk-badge rb-reco-risk-badge--${riskLevel}`}>
          {formatRiskLevel(riskLevel)}
        </span>
      </div>

      <div className="rb-reco-table-cell">
        <p>{formatSelectorRule(item)}</p>
      </div>
    </article>
  );
}

// Ce composant affiche les limites de la recommandation sous forme compacte.
function RecommendationLimits({
  limits,
}: {
  limits: MultiMatchRecommendationResponse["limits"];
}) {
  const cleanedLimits = cleanTextItems(limits).slice(0, 2);

  if (cleanedLimits.length === 0) {
    return null;
  }

  return (
    <div className="rb-reco-limits">
      {cleanedLimits.map((limit) => (
        <p key={limit}>
          <span>ⓘ</span>
          {limit}
        </p>
      ))}
    </div>
  );
}

// Ce composant permet de paramétrer, générer et afficher une sélection multi-matchs expérimentale.
function MultiMatchRecommendationSection({
  recommendationMatchCount,
  recommendationRiskLevel,
  multiMatchRecommendation,
  multiMatchStatus,
  onChangeMatchCount,
  onChangeRiskLevel,
  onGenerateRecommendation,
}: MultiMatchRecommendationSectionProps) {
  const isGenerating = isGenerationPending(multiMatchStatus);
  const hasRecommendations =
    Boolean(multiMatchRecommendation) &&
    multiMatchRecommendation!.recommendations.length > 0;

    const emptyStateContent = getEmptyStateContent(
    multiMatchRecommendation,
    recommendationRiskLevel,
    multiMatchStatus,
  );
  return (
    <section className="rb-reco-generator-panel">
      <div className="rb-reco-controls-panel">
        <MatchCountSegments
          value={recommendationMatchCount}
          disabled={isGenerating}
          onChange={onChangeMatchCount}
        />

        <RiskLevelSegments
          value={recommendationRiskLevel}
          disabled={isGenerating}
          onChange={onChangeRiskLevel}
        />

        <div className="rb-reco-action-box">
          <button
            type="button"
            onClick={onGenerateRecommendation}
            disabled={isGenerating}
          >
            {isGenerating
              ? "Génération en cours..."
              : "Générer la sélection"}
          </button>

          <p role="status">
            <span>✧</span>
            Signaux issus du modèle national expérimental
          </p>
        </div>
      </div>

      <div className="rb-reco-results-panel">
        <div className="rb-reco-results-header">
          <div>
            <p className="rb-reco-kicker">Votre sélection multi-matchs</p>
            <h3>Sélection analytique nationale</h3>
          </div>

          <div className="rb-reco-results-stats">
            <p>
              <span>Sélections</span>
              <strong>{multiMatchRecommendation?.selected_count ?? "—"}</strong>
            </p>
            <p>
              <span>Confiance globale</span>
              <strong>{getGlobalConfidence(multiMatchRecommendation)}</strong>
            </p>
            <p>
              <span>Risque global</span>
              <strong>
                {multiMatchRecommendation
                  ? formatRiskLevel(multiMatchRecommendation.request.risk_level)
                  : formatRiskLevel(recommendationRiskLevel)}
              </strong>
            </p>
          </div>
        </div>

                {!hasRecommendations ? (
          <div className="rb-reco-empty-state">
            <h3>{emptyStateContent.title}</h3>
            <p>{emptyStateContent.message}</p>
            <p>{emptyStateContent.hint}</p>
          </div>
        ) : null}

        {hasRecommendations ? (
          <>
            <div className="rb-reco-table">
              <div className="rb-reco-table-head">
                <span>Match</span>
                <span>Marché & sélection</span>
                <span>Confiance</span>
                <span>Risque</span>
                <span>Analyse clé</span>
              </div>

              {multiMatchRecommendation!.recommendations.map((item) => (
                <RecommendationRow
                  item={item}
                  key={`${item.match.id}-${item.selected_market}`}
                />
              ))}
            </div>

            <RecommendationLimits limits={multiMatchRecommendation!.limits} />
          </>
        ) : null}
      </div>
    </section>
  );
}

export default MultiMatchRecommendationSection;

// Schéma de communication du fichier :
// MultiMatchRecommendationSection.tsx
// ├── reçoit les paramètres et résultats depuis RecommendationScreen.tsx
// ├── conserve les callbacks onChangeMatchCount, onChangeRiskLevel et onGenerateRecommendation
// ├── affiche les sélections issues du endpoint national expérimental sous forme de tableau premium
// ├── sépare clairement Match, Marché & sélection, Confiance, Risque et Analyse clé
// └── ne modifie ni backend, ni modèle ML ; il restitue uniquement la réponse typée reçue par App.tsx
