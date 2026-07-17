// Ce composant affiche le générateur de sélection multi-matchs fondé sur les décisions publiques RubyBets V19.

import type {
  Match,
  V19SelectionDataQuality,
  V19SelectionItem,
  V19SelectionResponse,
} from "../models/rubybets";
import {
  cleanTextItems,
  getTeamInitials,
  getTeamShortName,
} from "../helpers/displayText";

type SelectionProfileLevel = "low" | "medium" | "high";
type RecommendationTeam = Match["home_team"];

type MultiMatchRecommendationSectionProps = {
  matches: Match[];
  activeCompetitionLabel: string;
  recommendationMatchCount: number;
  recommendationSelectionProfile: SelectionProfileLevel;
  multiMatchRecommendation: V19SelectionResponse | null;
  multiMatchStatus: string;
  onChangeMatchCount: (count: number) => void;
  onChangeSelectionProfile: (profile: SelectionProfileLevel) => void;
  onGenerateRecommendation: () => void;
};

type QualityPresentation = {
  label: string;
  detail: string;
  tone: SelectionProfileLevel;
};

// Cette fonction détecte l’état de génération à partir du statut existant.
function isGenerationPending(status: string) {
  return /génération|generation|chargement|loading/i.test(status);
}

// Cette fonction formate une date courte pour garder le tableau compact.
function formatShortDate(value: string | null | undefined) {
  if (!value) {
    return "Date à confirmer";
  }

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

// Cette fonction retourne un nom court d’équipe avec un fallback responsable.
function getTeamLabel(team: RecommendationTeam | null | undefined) {
  return team ? getTeamShortName(team) : "Équipe à confirmer";
}

// Cette fonction retourne le libellé public du profil choisi avant la première génération.
function formatSelectionProfile(profile: SelectionProfileLevel) {
  const labels: Record<SelectionProfileLevel, string> = {
    low: "Prudence renforcée",
    medium: "Équilibre",
    high: "Ouverture contrôlée",
  };

  return labels[profile];
}

// Cette fonction convertit le profil public V19 en suffixe compatible avec les badges existants.
function getProfileTone(value: string): SelectionProfileLevel {
  const normalizedValue = value.toUpperCase();

  if (normalizedValue === "LOW") {
    return "low";
  }

  if (normalizedValue === "HIGH") {
    return "high";
  }

  return "medium";
}

// Cette fonction retourne un libellé de marché clair pour les décisions publiques V19.
function formatMarketLabel(market: string) {
  const labels: Record<string, string> = {
    STRICT_1X2: "1X2",
    DOUBLE_CHANCE: "Double chance",
    OVER_1_5: "Plus de 1,5 but",
    OVER_2_5: "Plus de 2,5 buts",
    BTTS: "BTTS",
  };

  return labels[market] ?? market.replaceAll("_", " ");
}

// Cette fonction traduit une recommandation technique V19 en phrase utilisateur.
function formatSelectedPrediction(
  item: V19SelectionItem,
  match: Match | null,
) {
  const prediction = item.recommendation.value;
  const homeName = getTeamLabel(match?.home_team);
  const awayName = getTeamLabel(match?.away_team);

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

  return labels[prediction] ?? prediction.replaceAll("_", " ");
}

// Cette fonction normalise les alertes de qualité, quel que soit leur format public.
function normalizeQualityFlags(value: string[] | string | null) {
  if (Array.isArray(value)) {
    return cleanTextItems(value);
  }

  if (typeof value === "string") {
    return cleanTextItems(value.split(","));
  }

  return [];
}

// Cette fonction transforme les statuts publics V19 en lecture simple de qualité des données.
function getQualityPresentation(
  quality: V19SelectionDataQuality,
): QualityPresentation {
  const targetReady = quality.target_match_provider_status === "success";
  const marketStatus = quality.market_module_status?.toUpperCase() ?? "";
  const historyStatus = quality.history_data_status?.toLowerCase() ?? "";
  const qualityFlags = normalizeQualityFlags(quality.market_quality_flags);

  const historyAcceptable =
    historyStatus === "" ||
    historyStatus === "available" ||
    historyStatus === "partial";

  if (
    targetReady &&
    marketStatus === "READY" &&
    historyAcceptable &&
    qualityFlags.length === 0
  ) {
    return {
      label: "Disponible",
      detail: "Sources principales disponibles",
      tone: "low",
    };
  }

  if (
    targetReady &&
    (marketStatus === "READY" || marketStatus === "DEGRADED")
  ) {
    return {
      label: "Partielle",
      detail: "Données suffisantes avec limites",
      tone: "medium",
    };
  }

  return {
    label: "À surveiller",
    detail: "Disponibilité réduite des données",
    tone: "high",
  };
}

// Cette fonction choisit une explication publique courte pour la colonne Analyse clé.
function getAnalysisKey(item: V19SelectionItem) {
  const supportingFactors = cleanTextItems(
    item.explanation.supporting_factors,
  );
  const cautionFactors = cleanTextItems(item.explanation.caution_factors);

  if (supportingFactors.length > 0) {
    return supportingFactors[0];
  }

  if (cautionFactors.length > 0) {
    return cautionFactors[0];
  }

  return item.explanation.summary;
}

// Cette fonction prépare le message affiché quand aucune sélection V19 n’est disponible.
function getEmptyStateContent(
  multiMatchRecommendation: V19SelectionResponse | null,
  multiMatchStatus: string,
) {
  if (multiMatchRecommendation?.status === "EMPTY") {
    return {
      title: multiMatchRecommendation.selection_explanation.headline,
      message: multiMatchRecommendation.selection_explanation.summary,
      hint:
        "Modifiez le profil de sélectivité ou relancez la génération lorsque de nouveaux matchs seront disponibles.",
    };
  }

  return {
    title: "Aucune sélection affichée",
    message: multiMatchStatus,
    hint:
      "Lancez une génération pour analyser les décisions officielles V19 disponibles.",
  };
}

// Ce composant affiche un logo d’équipe avec fallback.
function TeamLogo({
  team,
  label,
}: {
  team: RecommendationTeam | null | undefined;
  label: string;
}) {
  return (
    <span className="rb-reco-team-logo" aria-label={`Logo ${label}`}>
      <span className="rb-reco-team-logo__fallback">
        {team ? getTeamInitials(team) : "?"}
      </span>

      {team?.crest ? (
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

// Ce composant affiche les boutons segmentés du profil de sélectivité V19.
function SelectionProfileSegments({
  value,
  disabled,
  onChange,
}: {
  value: SelectionProfileLevel;
  disabled: boolean;
  onChange: (profile: SelectionProfileLevel) => void;
}) {
  const options: Array<{
    value: SelectionProfileLevel;
    label: string;
  }> = [
    { value: "low", label: "Prudent" },
    { value: "medium", label: "Équilibré" },
    { value: "high", label: "Ouvert" },
  ];

  return (
    <div className="rb-reco-segment-group">
      <span>Profil de sélectivité</span>
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

// Ce composant affiche une ligne de sélection issue du contrat public V19.
function RecommendationRow({
  item,
  match,
  profileLabel,
  profileValue,
}: {
  item: V19SelectionItem;
  match: Match | null;
  profileLabel: string;
  profileValue: string;
}) {
  const homeLabel = getTeamLabel(match?.home_team);
  const awayLabel = getTeamLabel(match?.away_team);
  const quality = getQualityPresentation(item.data_quality);
  const profileTone = getProfileTone(profileValue);

  return (
    <article className="rb-reco-table-row">
      <div className="rb-reco-table-cell rb-reco-match-cell">
        <div className="rb-reco-match-meta">
          <strong>{match?.competition.name ?? `Match V19 #${item.match_id}`}</strong>
          <span>{formatShortDate(match?.utc_date)}</span>
        </div>

        <div className="rb-reco-fixture">
          <span className="rb-reco-fixture-team rb-reco-fixture-team--home">
            <TeamLogo team={match?.home_team} label={homeLabel} />
            <span className="rb-reco-team-name">{homeLabel}</span>
          </span>

          <span className="rb-reco-vs">VS</span>

          <span className="rb-reco-fixture-team rb-reco-fixture-team--away">
            <TeamLogo team={match?.away_team} label={awayLabel} />
            <span className="rb-reco-team-name">{awayLabel}</span>
          </span>
        </div>
      </div>

      <div className="rb-reco-table-cell rb-reco-selection-cell">
        <div className="rb-reco-selection-card">
          <span className="rb-reco-market-badge rb-reco-market-badge--solo">
            {formatMarketLabel(item.recommendation.market_type)}
          </span>
          <strong>{formatSelectedPrediction(item, match)}</strong>
          <p>{item.explanation.summary}</p>
        </div>
      </div>

      <div className="rb-reco-table-cell rb-reco-confidence-cell">
        <span
          className={`rb-reco-risk-badge rb-reco-risk-badge--${quality.tone}`}
        >
          {quality.label}
        </span>
        <small>{quality.detail}</small>
      </div>

      <div className="rb-reco-table-cell">
        <span
          className={`rb-reco-risk-badge rb-reco-risk-badge--${profileTone}`}
        >
          {profileLabel}
        </span>
      </div>

      <div className="rb-reco-table-cell">
        <p>{getAnalysisKey(item)}</p>
      </div>
    </article>
  );
}

// Ce composant affiche les exclusions publiques et le rappel responsable sans codes internes détaillés.
function SelectionNotices({
  response,
}: {
  response: V19SelectionResponse;
}) {
  const excludedMessages = cleanTextItems(
    response.excluded_matches.map((item) => item.summary),
  );
  const messages = cleanTextItems([
    ...excludedMessages,
    response.responsible_note,
  ]).slice(0, 3);

  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="rb-reco-limits">
      {messages.map((message) => (
        <p key={message}>
          <span>ⓘ</span>
          {message}
        </p>
      ))}
    </div>
  );
}

// Ce composant permet de paramétrer, générer et afficher une sélection multi-matchs V19.
function MultiMatchRecommendationSection({
  matches,
  activeCompetitionLabel,
  recommendationMatchCount,
  recommendationSelectionProfile,
  multiMatchRecommendation,
  multiMatchStatus,
  onChangeMatchCount,
  onChangeSelectionProfile,
  onGenerateRecommendation,
}: MultiMatchRecommendationSectionProps) {
  const isGenerating = isGenerationPending(multiMatchStatus);
  const candidateCount = matches.length;
  const canGenerateSelection = candidateCount >= 2;
  const hasRecommendations =
    Boolean(multiMatchRecommendation) &&
    multiMatchRecommendation!.selections.length > 0;
  const emptyStateContent = getEmptyStateContent(
    multiMatchRecommendation,
    multiMatchStatus,
  );
  const profileLabel = multiMatchRecommendation
    ? multiMatchRecommendation.profile.label
    : formatSelectionProfile(recommendationSelectionProfile);

  return (
    <section className="rb-reco-generator-panel">
      <div className="rb-reco-controls-panel">
        <MatchCountSegments
          value={recommendationMatchCount}
          disabled={isGenerating}
          onChange={onChangeMatchCount}
        />

        <SelectionProfileSegments
          value={recommendationSelectionProfile}
          disabled={isGenerating}
          onChange={onChangeSelectionProfile}
        />

        <div className="rb-reco-action-box">
          <button
            type="button"
            onClick={onGenerateRecommendation}
            disabled={isGenerating || !canGenerateSelection}
          >
            {isGenerating
              ? "Génération en cours..."
              : "Générer la sélection"}
          </button>

          <p role="status">
            <span>✧</span>
            {canGenerateSelection
              ? `${activeCompetitionLabel} · ${candidateCount} matchs candidats`
              : candidateCount === 0
                ? `${activeCompetitionLabel} · aucun match candidat. Au moins 2 matchs sont nécessaires.`
                : `${activeCompetitionLabel} · 1 match candidat. Au moins 2 matchs sont nécessaires.`}
          </p>
        </div>
      </div>

      <div className="rb-reco-results-panel">
        <div className="rb-reco-results-header">
          <div>
            <p className="rb-reco-kicker">Votre sélection multi-matchs</p>
            <h3>Sélection analytique V19</h3>
          </div>

          <div className="rb-reco-results-stats">
            <p>
              <span>Sélections</span>
              <strong>{multiMatchRecommendation?.selected_count ?? "—"}</strong>
            </p>
            <p>
              <span>
                {multiMatchRecommendation ? "Matchs évalués" : "Candidats"}
              </span>
              <strong>
                {multiMatchRecommendation?.evaluated_count ?? candidateCount}
              </strong>
            </p>
            <p>
              <span>Profil</span>
              <strong>{profileLabel}</strong>
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

        {hasRecommendations && multiMatchRecommendation ? (
          <>
            <div className="rb-reco-table">
              <div className="rb-reco-table-head">
                <span>Match</span>
                <span>Marché & sélection</span>
                <span>Qualité des données</span>
                <span>Profil</span>
                <span>Analyse clé</span>
              </div>

              {multiMatchRecommendation.selections.map((item) => (
                <RecommendationRow
                  item={item}
                  match={
                    matches.find((match) => match.id === item.match_id) ?? null
                  }
                  profileLabel={multiMatchRecommendation.profile.label}
                  profileValue={multiMatchRecommendation.profile.value}
                  key={`${item.match_id}-${item.recommendation.market_type}`}
                />
              ))}
            </div>

            <SelectionNotices response={multiMatchRecommendation} />
          </>
        ) : null}
      </div>
    </section>
  );
}

export default MultiMatchRecommendationSection;

// Schéma de communication du fichier :
// MultiMatchRecommendationSection.tsx
// ├── reçoit les matchs, la compétition active et la réponse V19 depuis RecommendationScreen.tsx
// ├── conserve les composants visuels et classes CSS du design Obsidian Teal
// ├── rapproche chaque sélection publique de son match local grâce au match_id
// ├── affiche la compétition active, le nombre de candidats et bloque la génération sous deux matchs
// ├── affiche qualité, profil, explication et exclusions sans score brut ni probabilité
// └── ne recalcule aucune décision métier et ne transforme jamais une abstention en recommandation