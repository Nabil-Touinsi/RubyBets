// Ce composant permet de choisir un style puis d’afficher une sélection multi-matchs claire et responsable.

import type { CSSProperties } from "react";
import {
  CalendarDays,
  CheckCircle2,
  Info,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  Trophy,
} from "lucide-react";
import type {
  Match,
  V19SelectionDataQuality,
  V19SelectionItem,
  V19SelectionResponse,
} from "../models/rubybets";
import { getTeamInitials, getTeamShortName } from "../helpers/displayText";

type SelectionProfileLevel = "low" | "medium" | "high";
type RecommendationTeam = Match["home_team"];
type InformationTone = "complete" | "partial" | "limited";

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

type InformationPresentation = {
  label: string;
  tone: InformationTone;
};

// Cette fonction détecte l’état de préparation à partir du statut déjà fourni par l’application.
function isGenerationPending(status: string) {
  return /^(génération de|generation de|chargement|loading|préparation|preparation)/i.test(
    status.trim(),
  );
}

// Cette fonction détecte un message d’erreur sans l’exposer directement à l’utilisateur.
function hasGenerationError(status: string) {
  return /erreur|error|échec|echec|indisponible/i.test(status);
}

// Cette fonction formate la date d’un match dans un format court et lisible.
function formatShortDate(value: string | null | undefined) {
  if (!value) {
    return "Horaire à confirmer";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Horaire à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Cette fonction retourne un nom court d’équipe avec un fallback neutre.
function getTeamLabel(team: RecommendationTeam | null | undefined) {
  return team ? getTeamShortName(team) : "Équipe à confirmer";
}

// Cette fonction traduit le style interne en libellé utilisateur.
function formatSelectionStyle(profile: SelectionProfileLevel | string) {
  const normalizedProfile = profile.toLowerCase();
  const labels: Record<string, string> = {
    low: "Prudent",
    medium: "Équilibré",
    high: "Ouvert",
  };

  return labels[normalizedProfile] ?? "Équilibré";
}

// Cette fonction traduit la recommandation reçue en choix simple et lisible.
function formatSelectedChoice(item: V19SelectionItem) {
  const prediction = item.recommendation.value.toUpperCase();
  const labels: Record<string, string> = {
    TEAM_A_WIN: "Victoire à domicile",
    HOME_WIN: "Victoire à domicile",
    "1": "Victoire à domicile",
    TEAM_B_WIN: "Victoire à l’extérieur",
    AWAY_WIN: "Victoire à l’extérieur",
    "2": "Victoire à l’extérieur",
    DRAW: "Match nul",
    X: "Match nul",
    DRAW_OR_TEAM_A: "Domicile ou nul",
    "1X": "Domicile ou nul",
    DRAW_OR_TEAM_B: "Extérieur ou nul",
    X2: "Extérieur ou nul",
    TEAM_A_OR_TEAM_B: "Une équipe gagnante",
    "12": "Une équipe gagnante",
    OVER_1_5: "Plus de 1,5 but",
    OVER_2_5: "Plus de 2,5 buts",
    YES: "Les deux équipes marquent",
    NO: "Au moins une équipe ne marque pas",
  };

  return labels[prediction] ?? "Choix recommandé";
}

// Cette fonction transforme les états de disponibilité en libellé simple.
function getInformationPresentation(
  quality: V19SelectionDataQuality,
): InformationPresentation {
  const targetReady = quality.target_match_provider_status === "success";
  const marketStatus = quality.market_module_status?.toUpperCase() ?? "";
  const historyStatus = quality.history_data_status?.toLowerCase() ?? "";
  const flags = Array.isArray(quality.market_quality_flags)
    ? quality.market_quality_flags.filter(Boolean)
    : quality.market_quality_flags
      ? [quality.market_quality_flags]
      : [];

  const historyAvailable =
    historyStatus === "" ||
    historyStatus === "available" ||
    historyStatus === "partial";

  if (
    targetReady &&
    marketStatus === "READY" &&
    historyAvailable &&
    flags.length === 0
  ) {
    return { label: "Complet", tone: "complete" };
  }

  if (targetReady && (marketStatus === "READY" || marketStatus === "DEGRADED")) {
    return { label: "Partiel", tone: "partial" };
  }

  return { label: "Limité", tone: "limited" };
}

// Cette fonction explique le choix sans afficher de vocabulaire technique.
function getFriendlyReason(
  item: V19SelectionItem,
  information: InformationPresentation,
) {
  const market = item.recommendation.market_type.toUpperCase();
  const value = item.recommendation.value.toUpperCase();

  if (market === "DOUBLE_CHANCE" || ["1X", "X2", "12"].includes(value)) {
    return "Deux issues restent cohérentes, ce qui conduit à une lecture plus prudente.";
  }

  if (market === "OVER_1_5" || value === "OVER_1_5") {
    return "Les tendances disponibles soutiennent un match avec au moins deux buts.";
  }

  if (market === "OVER_2_5" || value === "OVER_2_5") {
    return "Les tendances disponibles vont vers un match plutôt ouvert.";
  }

  if (market === "BTTS" && value === "YES") {
    return "Les deux équipes présentent des éléments favorables pour marquer.";
  }

  if (market === "BTTS" && value === "NO") {
    return "La lecture actuelle invite à rester prudent sur la capacité des deux équipes à marquer.";
  }

  if (information.tone === "partial") {
    return "Le choix reste cohérent, avec quelques informations à considérer avec prudence.";
  }

  if (information.tone === "limited") {
    return "Le choix est proposé avec prudence car certaines informations restent limitées.";
  }

  return "Les informations disponibles vont dans le même sens et rendent ce choix plus lisible.";
}

// Cette fonction prépare un état vide compréhensible selon la situation actuelle.
function getEmptyStateContent(
  response: V19SelectionResponse | null,
  status: string,
  isGenerating: boolean,
) {
  if (isGenerating) {
    return {
      title: "Préparation de votre sélection",
      message: "RubyBets examine les matchs disponibles.",
      hint: "Quelques instants suffisent généralement.",
    };
  }

  if (response?.status === "EMPTY") {
    return {
      title: "Aucune proposition pour le moment",
      message:
        "Les matchs disponibles ne correspondent pas suffisamment au style choisi.",
      hint: "Essayez un autre style ou relancez plus tard.",
    };
  }

  if (hasGenerationError(status)) {
    return {
      title: "La sélection n’a pas pu être préparée",
      message: "Un problème temporaire a interrompu la préparation.",
      hint: "Vous pouvez relancer la sélection dans quelques instants.",
    };
  }

  return {
    title: "Votre sélection apparaîtra ici",
    message: "Choisissez vos préférences puis lancez la sélection.",
    hint: "Les rencontres trop incertaines pourront être laissées de côté.",
  };
}

// Ce composant affiche un logo d’équipe avec un fallback lisible.
function TeamLogo({
  team,
  label,
}: {
  team: RecommendationTeam | null | undefined;
  label: string;
}) {
  return (
    <span className="rb-selection-team-logo" aria-label={`Logo ${label}`}>
      <span className="rb-selection-team-logo__fallback">
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

// Ce composant affiche le choix du nombre de matchs sous forme de boutons accessibles.
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
    <fieldset className="rb-selection-control-group">
      <legend>Nombre de matchs</legend>
      <div className="rb-selection-segments" role="radiogroup" aria-label="Nombre de matchs">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={value === option}
            disabled={disabled}
            className={value === option ? "is-active" : ""}
            onClick={() => onChange(option)}
          >
            {option}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

// Ce composant affiche le style de sélection avec des libellés non techniques.
function SelectionStyleSegments({
  value,
  disabled,
  onChange,
}: {
  value: SelectionProfileLevel;
  disabled: boolean;
  onChange: (profile: SelectionProfileLevel) => void;
}) {
  const options: Array<{ value: SelectionProfileLevel; label: string }> = [
    { value: "low", label: "Prudent" },
    { value: "medium", label: "Équilibré" },
    { value: "high", label: "Ouvert" },
  ];

  return (
    <fieldset className="rb-selection-control-group">
      <legend>Style de sélection</legend>
      <div className="rb-selection-segments" role="radiogroup" aria-label="Style de sélection">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            disabled={disabled}
            className={value === option.value ? "is-active" : ""}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

// Ce composant affiche une rencontre retenue avec son choix et une explication simple.
function RecommendationRow({
  item,
  match,
  index,
}: {
  item: V19SelectionItem;
  match: Match | null;
  index: number;
}) {
  const homeLabel = getTeamLabel(match?.home_team);
  const awayLabel = getTeamLabel(match?.away_team);
  const information = getInformationPresentation(item.data_quality);
  const style = { "--rb-selection-row-index": index } as CSSProperties;

  return (
    <div className="rb-selection-result-row" style={style} role="row">
      <div className="rb-selection-result-cell rb-selection-match-cell" role="cell">
        <div className="rb-selection-match-context">
          <span>{match?.competition.name ?? "Compétition"}</span>
          <span>
            <CalendarDays size={13} aria-hidden="true" />
            {formatShortDate(match?.utc_date)}
          </span>
        </div>

        <div className="rb-selection-fixture">
          <span className="rb-selection-fixture__team">
            <TeamLogo team={match?.home_team} label={homeLabel} />
            <strong>{homeLabel}</strong>
          </span>

          <span className="rb-selection-fixture__versus">VS</span>

          <span className="rb-selection-fixture__team">
            <TeamLogo team={match?.away_team} label={awayLabel} />
            <strong>{awayLabel}</strong>
          </span>
        </div>
      </div>

      <div className="rb-selection-result-cell rb-selection-choice-cell" role="cell">
        <span className="rb-selection-choice-chip">
          <ShieldCheck size={17} aria-hidden="true" />
          {formatSelectedChoice(item)}
        </span>
      </div>

      <div className="rb-selection-result-cell rb-selection-info-cell" role="cell">
        <span className={`rb-selection-info-status is-${information.tone}`}>
          <CheckCircle2 size={15} aria-hidden="true" />
          {information.label}
        </span>
      </div>

      <div className="rb-selection-result-cell rb-selection-reason-cell" role="cell">
        <p>{getFriendlyReason(item, information)}</p>
      </div>
    </div>
  );
}

// Ce composant affiche uniquement les rappels utiles sous la sélection.
function SelectionNotices({ response }: { response: V19SelectionResponse }) {
  const hasExcludedMatches = response.excluded_matches.length > 0;

  return (
    <div className="rb-selection-notices">
      {hasExcludedMatches ? (
        <p>
          <Info size={17} aria-hidden="true" />
          Certains matchs ont été laissés de côté lorsque la lecture n’était pas assez claire.
        </p>
      ) : null}
      <p>
        <Info size={17} aria-hidden="true" />
        RubyBets propose une aide à la décision avant-match, sans garantie de résultat sportif.
      </p>
    </div>
  );
}

// Ce composant réunit les contrôles, le chargement, l’état vide et les résultats.
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
    isGenerating,
  );
  const styleLabel = multiMatchRecommendation
    ? formatSelectionStyle(multiMatchRecommendation.profile.value)
    : formatSelectionStyle(recommendationSelectionProfile);

  return (
    <section className="rb-selection-generator" aria-label="Création de la sélection">
      <div className="rb-selection-controls-card">
        <MatchCountSegments
          value={recommendationMatchCount}
          disabled={isGenerating}
          onChange={onChangeMatchCount}
        />

        <SelectionStyleSegments
          value={recommendationSelectionProfile}
          disabled={isGenerating}
          onChange={onChangeSelectionProfile}
        />

        <div className="rb-selection-action">
          <button
            type="button"
            className="rb-selection-primary-button"
            onClick={onGenerateRecommendation}
            disabled={isGenerating || !canGenerateSelection}
          >
            {isGenerating ? (
              <LoaderCircle className="rb-selection-spinner" size={19} aria-hidden="true" />
            ) : (
              <Sparkles size={19} aria-hidden="true" />
            )}
            <span>{isGenerating ? "Préparation en cours..." : "Lancer la sélection"}</span>
          </button>

          <p className="rb-selection-availability" role="status" aria-live="polite">
            <Trophy size={15} aria-hidden="true" />
            {canGenerateSelection
              ? `${activeCompetitionLabel} · ${candidateCount} matchs disponibles`
              : `${activeCompetitionLabel} · au moins 2 matchs sont nécessaires`}
          </p>
        </div>
      </div>

      <div className="rb-selection-results-card">
        <header className="rb-selection-results-header">
          <div>
            <p className="rb-selection-section-kicker">Votre sélection</p>
            <h2>Sélection proposée</h2>
          </div>

          <dl className="rb-selection-results-stats">
            <div>
              <dt>Matchs retenus</dt>
              <dd>{multiMatchRecommendation?.selected_count ?? "—"}</dd>
            </div>
            <div>
              <dt>Matchs disponibles</dt>
              <dd>{multiMatchRecommendation?.evaluated_count ?? candidateCount}</dd>
            </div>
            <div>
              <dt>Style</dt>
              <dd>{styleLabel}</dd>
            </div>
          </dl>
        </header>

        {!hasRecommendations ? (
          <div className={`rb-selection-empty${isGenerating ? " is-loading" : ""}`} aria-live="polite">
            <span className="rb-selection-empty__icon" aria-hidden="true">
              {isGenerating ? (
                <LoaderCircle className="rb-selection-spinner" size={25} />
              ) : (
                <Sparkles size={24} />
              )}
            </span>
            <div>
              <h3>{emptyStateContent.title}</h3>
              <p>{emptyStateContent.message}</p>
              <small>{emptyStateContent.hint}</small>
            </div>
          </div>
        ) : null}

        {hasRecommendations && multiMatchRecommendation ? (
          <>
            <div className="rb-selection-results-table" role="table" aria-label="Sélection proposée">
              <div className="rb-selection-results-head" role="row">
                <span role="columnheader">Match</span>
                <span role="columnheader">Choix retenu</span>
                <span role="columnheader">Infos disponibles</span>
                <span role="columnheader">Pourquoi ce choix</span>
              </div>

              <div className="rb-selection-results-body" role="rowgroup">
                {multiMatchRecommendation.selections.map((item, index) => (
                  <RecommendationRow
                    key={`${item.match_id}-${item.recommendation.market_type}`}
                    item={item}
                    match={matches.find((match) => match.id === item.match_id) ?? null}
                    index={index}
                  />
                ))}
              </div>
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
// RecommendationScreen.tsx -> MultiMatchRecommendationSection.tsx
// MultiMatchRecommendationSection.tsx <- Match[] + V19SelectionResponse
// MultiMatchRecommendationSection.tsx -> helpers/displayText.ts
// MultiMatchRecommendationSection.tsx -> aucune décision recalculée côté frontend
