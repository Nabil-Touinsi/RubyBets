// Ce composant affiche le générateur de recommandation multi-matchs avec contrôles segmentés et tableau compact.

import type { MultiMatchRecommendationResponse } from "../models/rubybets";
import {
  cleanTextItems,
  formatConfidenceLevel,
  formatRiskLevel,
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
  return team.short_name || team.tla || team.name;
}

// Cette fonction retourne un fallback textuel pour les logos absents.
function getTeamInitials(team: RecommendationTeam) {
  if (team.tla) {
    return team.tla;
  }

  return getTeamLabel(team)
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");
}

// Cette fonction convertit un niveau de confiance en score visuel.
function getConfidencePercent(confidence: string) {
  const values: Record<string, number> = {
    high: 72,
    medium: 64,
    low: 56,
  };

  return values[confidence] ?? 60;
}

// Cette fonction calcule une confiance globale indicative pour la sélection.
function getGlobalConfidence(
  multiMatchRecommendation: MultiMatchRecommendationResponse | null,
) {
  const recommendations = multiMatchRecommendation?.recommendations ?? [];

  if (recommendations.length === 0) {
    return "—";
  }

  const total = recommendations.reduce((sum, item) => {
    return sum + getConfidencePercent(item.selected_prediction.confidence);
  }, 0);

  return `${Math.round(total / recommendations.length)}%`;
}

// Cette fonction retourne un libellé marché plus lisible.
function formatMarketLabel(market: string) {
  const labels: Record<string, string> = {
    one_x_two: "Résultat du match",
    goals: "Nombre de buts",
    btts: "Les deux équipes marquent",
  };

  return labels[market] ?? market;
}

// Ce composant affiche un logo d’équipe avec fallback.
function TeamLogo({ team }: { team: RecommendationTeam }) {
  return (
    <span className="rb-reco-team-logo" aria-label={`Logo ${team.name}`}>
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

// Ce composant affiche une ligne de recommandation dans le tableau compact.
function RecommendationRow({ item }: { item: RecommendationItem }) {
  const confidencePercent = getConfidencePercent(
    item.selected_prediction.confidence,
  );

  return (
    <article className="rb-reco-table-row">
      <div className="rb-reco-table-cell rb-reco-match-cell">
        <div className="rb-reco-match-meta">
          <strong>{item.match.competition.name}</strong>
          <span>{formatShortDate(item.match.utc_date)}</span>
        </div>

        <div className="rb-reco-fixture">
          <TeamLogo team={item.match.home_team} />
          <span className="rb-reco-team-name">
            {getTeamLabel(item.match.home_team)}
          </span>
          <span className="rb-reco-vs">VS</span>
          <TeamLogo team={item.match.away_team} />
          <span className="rb-reco-team-name">
            {getTeamLabel(item.match.away_team)}
          </span>
        </div>
      </div>

      <div className="rb-reco-table-cell">
        <span className="rb-reco-market-badge">
          {formatMarketLabel(item.selected_prediction.market)}
        </span>
        <strong>{item.selected_prediction.label}</strong>
      </div>

      <div className="rb-reco-table-cell rb-reco-confidence-cell">
        <span
          className="rb-reco-confidence-ring"
          style={{ "--rb-reco-confidence": `${confidencePercent}%` } as React.CSSProperties}
        >
          {confidencePercent}%
        </span>
        <small>{formatConfidenceLevel(item.selected_prediction.confidence)}</small>
      </div>

      <div className="rb-reco-table-cell">
        <span
          className={`rb-reco-risk-badge rb-reco-risk-badge--${item.selected_prediction.risk}`}
        >
          {formatRiskLevel(item.selected_prediction.risk)}
        </span>
      </div>

      <div className="rb-reco-table-cell">
        <p>{item.selected_prediction.justification}</p>
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

// Ce composant permet de paramétrer, générer et afficher une recommandation multi-matchs explicable.
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
              : "Générer la recommandation"}
          </button>

          <p role="status">
            <span>✧</span>
            Analyse basée sur des données avant-match
          </p>
        </div>
      </div>

      <div className="rb-reco-results-panel">
        <div className="rb-reco-results-header">
          <div>
            <p className="rb-reco-kicker">Votre recommandation multi-matchs</p>
            <h3>Sélection analytique</h3>
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
            <h3>Aucune sélection affichée</h3>
            <p>{multiMatchStatus}</p>
            <p>
              Lancez une génération pour afficher une recommandation structurée à
              partir des matchs disponibles.
            </p>
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
                <RecommendationRow item={item} key={item.match.id} />
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
// ├── affiche les sélections reçues du backend sous forme de tableau compact
// └── ne modifie ni API, ni backend, ni modèle de données