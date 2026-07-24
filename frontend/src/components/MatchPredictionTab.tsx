// Ce fichier affiche le sous-onglet Prédictions de la fiche match à partir de la décision publique V19, sans recalculer ni inventer de donnée.

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  CircleDot,
  Database,
  Info,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import type {
  V19ProductPredictionResponse,
  V19ProductRecommendation,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";

export type V19ProductLoadState =
  | "idle"
  | "loading"
  | "success"
  | "unavailable"
  | "error";

type MatchPredictionTabProps = {
  prediction: V19ProductPredictionResponse | null;
  loadState: V19ProductLoadState;
  statusMessage: string;
  onRetry: () => void;
};

type MatchPredictionSidebarProps = {
  prediction: V19ProductPredictionResponse | null;
  loadState: V19ProductLoadState;
  onNavigate: (screen: AppScreen) => void;
};

type SignalCard = {
  key: string;
  label: string;
  value: string;
  reason: string;
  icon: LucideIcon;
  retained: boolean;
  confidenceLevel: string | null;
  riskLevel: string | null;
};

type ExplanationColumnProps = {
  icon: ReactNode;
  title: string;
  items: string[];
  emptyMessage: string;
  tone: "positive" | "caution" | "negative" | "info";
};

type QualityRow = {
  label: string;
  status: string;
  strength: 1 | 2 | 3 | 4;
  tone: "good" | "warning";
};

// Cette fonction traduit le marché retenu avec des mots simples.
function formatMarketLabel(marketType: string): string {
  const labels: Record<string, string> = {
    STRICT_1X2: "Résultat du match",
    DOUBLE_CHANCE: "Double chance",
    OVER_1_5: "Nombre de buts",
    BTTS: "Les deux équipes marquent",
  };

  return labels[marketType] || "Signal analysé";
}

// Cette fonction traduit la valeur retenue sans produire une nouvelle prédiction.
function formatRecommendationValue(
  recommendation: V19ProductRecommendation,
): string {
  const values: Record<string, string> = {
    HOME_WIN: "Victoire à domicile",
    DRAW: "Match nul",
    AWAY_WIN: "Victoire à l’extérieur",
    "1X": "Domicile ou nul",
    X2: "Nul ou extérieur",
    "12": "Une équipe gagnera",
    OVER_1_5: "Plus de 1,5 but",
    YES: "Oui",
    NO: "Non",
  };

  return values[recommendation.value] || recommendation.value.replaceAll("_", " ");
}

// Cette fonction met uniquement la première lettre en minuscule pour fluidifier un titre après deux-points.
function lowercaseFirst(value: string): string {
  return value.length > 0 ? value.charAt(0).toLocaleLowerCase("fr-FR") + value.slice(1) : value;
}

// Cette fonction transforme un niveau réel en libellé français.
function formatLevel(level: string | null, feminine = false): string {
  if (!level) {
    return feminine ? "Non précisée" : "Non précisé";
  }

  const normalizedLevel = level.trim().toUpperCase();
  const labels: Record<string, string> = {
    LOW: "Faible",
    MEDIUM: feminine ? "Moyenne" : "Moyen",
    HIGH: feminine ? "Élevée" : "Élevé",
  };

  return labels[normalizedLevel] || level;
}

// Cette fonction associe un niveau transmis à trois repères visuels sans afficher de pourcentage.
function getLevelStep(level: string | null): number {
  const normalizedLevel = level?.trim().toUpperCase();

  if (normalizedLevel === "LOW") {
    return 1;
  }

  if (normalizedLevel === "MEDIUM") {
    return 2;
  }

  if (normalizedLevel === "HIGH") {
    return 3;
  }

  return 0;
}

// Cette fonction associe chaque marché à l’une des trois familles publiques de la maquette.
function getSignalFamilyFromMarket(
  marketType: string,
): "result" | "goals" | "btts" | null {
  const normalizedMarket = marketType.trim().toUpperCase();

  if (normalizedMarket === "STRICT_1X2" || normalizedMarket === "DOUBLE_CHANCE") {
    return "result";
  }

  if (normalizedMarket === "OVER_1_5") {
    return "goals";
  }

  if (normalizedMarket === "BTTS") {
    return "btts";
  }

  return null;
}

// Cette fonction reconnaît la famille d’un scénario public sans déduire une nouvelle prédiction.
function getSignalFamilyFromText(
  value: string,
): "result" | "goals" | "btts" | null {
  const normalizedValue = value.toLocaleLowerCase("fr-FR");

  if (
    normalizedValue.includes("résultat du match") ||
    normalizedValue.includes("double chance") ||
    normalizedValue.includes("1x2")
  ) {
    return "result";
  }

  if (
    normalizedValue.includes("plus de 1,5") ||
    normalizedValue.includes("nombre de buts") ||
    normalizedValue.includes("buts")
  ) {
    return "goals";
  }

  if (
    normalizedValue.includes("les deux équipes marquent") ||
    normalizedValue.includes("btts")
  ) {
    return "btts";
  }

  return null;
}

// Cette fonction fournit les libellés et icônes fixes de la maquette validée.
function getSignalFamilyDisplay(family: "result" | "goals" | "btts") {
  if (family === "result") {
    return { label: "1X2", icon: Target };
  }

  if (family === "goals") {
    return { label: "Nombre de buts", icon: TrendingUp };
  }

  return { label: "Les deux équipes marquent", icon: CircleDot };
}

// Cette fonction remplace les formulations internes par des mots publics plus simples sans modifier le sens général.
function simplifyPublicText(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  return value
    .replace(/données de marché internes/gi, "informations disponibles")
    .replace(/sources de marché internes/gi, "informations disponibles")
    .replace(/probabilité calibrée/gi, "niveau de confiance suffisamment fiable")
    .replace(/variables nécessaires/gi, "informations nécessaires")
    .replace(/limite interne non détaillée/gi, "élément de prudence non précisé")
    .replace(/diagnostics techniques/gi, "informations détaillées")
    .replace(/score expert/gi, "indicateur de décision")
    .replace(/politique versionnée/gi, "ordre de priorité défini")
    .replace(/un autre signal, prioritaire dans l’ordre de priorité défini, a été retenu/gi, "une autre lecture a été retenue en priorité")
    .replace(/les conditions minimales de ce signal ne sont pas satisfaites/gi, "les éléments disponibles ne suffisent pas pour retenir cette lecture")
    .replace(/deux issues concentrent suffisamment le signal pour une double chance/gi, "les éléments disponibles soutiennent une double chance")
    .replace(/moteur/gi, "analyse RubyBets")
    .replace(/candidat/gi, "signal")
    .replace(/module/gi, "source d’information")
    .trim();
}

// Cette fonction sépare une alternative publique en libellé et explication.
function splitPublicAlternative(value: string): { label: string; reason: string } {
  const separatorIndex = value.indexOf(":");

  if (separatorIndex < 0) {
    return {
      label: "Signal examiné",
      reason: simplifyPublicText(value),
    };
  }

  return {
    label: simplifyPublicText(value.slice(0, separatorIndex).trim()) || "Signal examiné",
    reason:
      simplifyPublicText(value.slice(separatorIndex + 1).trim()) ||
      "Ce signal n’a pas été retenu.",
  };
}

// Cette fonction prépare exactement les trois familles de signaux de la maquette à partir des seules données reçues.
function buildSignalCards(prediction: V19ProductPredictionResponse): SignalCard[] {
  const families: Array<"result" | "goals" | "btts"> = [
    "result",
    "goals",
    "btts",
  ];

  const cards = new Map<"result" | "goals" | "btts", SignalCard>();

  families.forEach((family) => {
    const display = getSignalFamilyDisplay(family);
    cards.set(family, {
      key: family,
      label: display.label,
      value: "Non communiqué",
      reason: "Aucune lecture publique n’a été transmise pour ce signal.",
      icon: display.icon,
      retained: false,
      confidenceLevel: null,
      riskLevel: null,
    });
  });

  if (prediction.recommendation) {
    const family = getSignalFamilyFromMarket(prediction.recommendation.market_type);

    if (family) {
      const display = getSignalFamilyDisplay(family);
      cards.set(family, {
        key: family,
        label: display.label,
        value: formatRecommendationValue(prediction.recommendation),
        reason: simplifyPublicText(
          prediction.explanation.supporting_factors[0] ||
            prediction.explanation.summary,
        ),
        icon: display.icon,
        retained: true,
        confidenceLevel: prediction.recommendation.confidence_level,
        riskLevel: prediction.recommendation.risk_level,
      });
    }
  }

  prediction.explanation.rejected_alternatives.forEach((alternative) => {
    const parsedAlternative = splitPublicAlternative(alternative);
    const family = getSignalFamilyFromText(parsedAlternative.label);

    if (!family || cards.get(family)?.retained) {
      return;
    }

    const display = getSignalFamilyDisplay(family);
    cards.set(family, {
      key: family,
      label: display.label,
      value: "Non retenu",
      reason: parsedAlternative.reason,
      icon: display.icon,
      retained: false,
      confidenceLevel: null,
      riskLevel: null,
    });
  });

  return families.map((family) => cards.get(family)!);
}

// Cette fonction produit une lecture publique et catégorielle de la qualité des informations.
function getQualityRows(prediction: V19ProductPredictionResponse): QualityRow[] {
  const matchAvailable =
    prediction.data_quality.target_match_provider_status?.toUpperCase() === "SUCCESS";
  const informationStatus = prediction.data_quality.market_module_status?.toUpperCase();
  const historyStatus = prediction.data_quality.history_data_status?.toUpperCase();
  const explanationAvailable = Boolean(
    prediction.explanation.headline || prediction.explanation.summary,
  );

  return [
    {
      label: "Match cible",
      status: matchAvailable ? "Disponible" : "À vérifier",
      strength: matchAvailable ? 4 : 1,
      tone: matchAvailable ? "good" : "warning",
    },
    {
      label: "Informations utiles",
      status:
        informationStatus === "READY"
          ? "Suffisantes"
          : informationStatus === "UNAVAILABLE"
            ? "Incomplètes"
            : "Partielles",
      strength: informationStatus === "READY" ? 4 : informationStatus === "UNAVAILABLE" ? 1 : 2,
      tone: informationStatus === "READY" ? "good" : "warning",
    },
    {
      label: "Historique récent",
      status:
        historyStatus === "AVAILABLE"
          ? "Disponible"
          : historyStatus === "PARTIAL"
            ? "Partiel"
            : "Indisponible",
      strength: historyStatus === "AVAILABLE" ? 4 : historyStatus === "PARTIAL" ? 2 : 1,
      tone: historyStatus === "AVAILABLE" ? "good" : "warning",
    },
    {
      label: "Explication publique",
      status: explanationAvailable ? "Disponible" : "Incomplète",
      strength: explanationAvailable ? 4 : 1,
      tone: explanationAvailable ? "good" : "warning",
    },
  ];
}

// Cette fonction affiche une échelle fondée uniquement sur le niveau textuel transmis.
function LevelIndicator({
  label,
  level,
  tone,
}: {
  label: string;
  level: string | null;
  tone: "confidence" | "risk";
}) {
  const activeStep = getLevelStep(level);

  return (
    <div className={`rb-detail-prediction-level rb-detail-prediction-level--${tone}`}>
      <span>{label}</span>
      <div>
        <strong>{formatLevel(level, tone === "confidence")}</strong>
        <span
          className="rb-detail-prediction-level__steps"
          aria-label={`${label} : ${formatLevel(level, tone === "confidence")}`}
        >
          {[1, 2, 3].map((step) => (
            <i
              key={step}
              className={step <= activeStep ? "is-active" : ""}
              aria-hidden="true"
            />
          ))}
        </span>
      </div>
    </div>
  );
}

// Cette fonction affiche une carte de signal à partir des seules informations publiques reçues.
function SignalCardView({ card }: { card: SignalCard }) {
  const Icon = card.icon;

  return (
    <article
      className={`rb-detail-prediction-signal-card${
        card.retained ? " rb-detail-prediction-signal-card--retained" : ""
      }`}
    >
      <header>
        <span className="rb-detail-prediction-icon-chip">
          <Icon size={20} aria-hidden="true" />
        </span>
        <div>
          <span>{card.label}</span>
          <h3>{card.value}</h3>
        </div>
      </header>

      <p className="rb-detail-prediction-signal-card__reason">{card.reason}</p>

      <footer className="rb-detail-prediction-signal-card__footer">
        {card.retained ? (
          <>
            <LevelIndicator
              label="Confiance"
              level={card.confidenceLevel}
              tone="confidence"
            />
            <LevelIndicator
              label="Prudence"
              level={card.riskLevel}
              tone="risk"
            />
          </>
        ) : (
          <span className="rb-detail-prediction-signal-card__status">
            Scénario examiné
          </span>
        )}
      </footer>
    </article>
  );
}

// Cette fonction affiche une colonne d’explication avec un état vide explicite.
function ExplanationColumn({
  icon,
  title,
  items,
  emptyMessage,
  tone,
}: ExplanationColumnProps) {
  return (
    <section
      className={`rb-detail-prediction-explanation-column rb-detail-prediction-explanation-column--${tone}`}
    >
      <header>
        <span>{icon}</span>
        <h3>{title}</h3>
      </header>

      {items.length > 0 ? (
        <ul>
          {items.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="rb-detail-prediction-empty-copy">{emptyMessage}</p>
      )}
    </section>
  );
}

// Cette fonction affiche l’état de chargement, d’indisponibilité ou d’erreur de l’onglet.
function PredictionStateCard({
  state,
  message,
  onRetry,
}: {
  state: V19ProductLoadState;
  message: string;
  onRetry: () => void;
}) {
  const isLoading = state === "loading" || state === "idle";
  const isError = state === "error";
  const title = isLoading
    ? "Préparation de la décision en cours"
    : isError
      ? "La décision n’a pas pu être chargée"
      : "Aucune décision disponible pour ce match";

  return (
    <section
      className={`rb-detail-prediction-state rb-detail-prediction-state--${state}`}
      aria-live="polite"
    >
      <span className="rb-detail-prediction-state__icon">
        {isLoading ? (
          <Sparkles size={28} aria-hidden="true" />
        ) : isError ? (
          <AlertTriangle size={28} aria-hidden="true" />
        ) : (
          <ShieldCheck size={28} aria-hidden="true" />
        )}
      </span>
      <div>
        <p className="rb-detail-prediction-eyebrow">DÉCISION RUBYBETS</p>
        <h2>{title}</h2>
        <p>{message}</p>
        {!isLoading ? (
          <button type="button" onClick={onRetry}>
            <RefreshCw size={17} aria-hidden="true" />
            Réessayer
          </button>
        ) : null}
      </div>
    </section>
  );
}

// Ce composant affiche le contenu principal du sous-onglet Prédictions.
export function MatchPredictionTabContent({
  prediction,
  loadState,
  statusMessage,
  onRetry,
}: MatchPredictionTabProps) {
  if (!prediction) {
    return (
      <PredictionStateCard
        state={loadState}
        message={statusMessage}
        onRetry={onRetry}
      />
    );
  }

  const isRecommendation = prediction.status === "RECOMMEND";
  const primaryRecommendation = prediction.recommendation;
  const signalCards = buildSignalCards(prediction);
  const decisionTitle = primaryRecommendation
    ? `${formatMarketLabel(primaryRecommendation.market_type)} : ${lowercaseFirst(formatRecommendationValue(primaryRecommendation))}.`
    : simplifyPublicText(prediction.explanation.headline) ||
      "Aucune recommandation retenue";
  const decisionSummary = simplifyPublicText(
    isRecommendation
      ? prediction.explanation.supporting_factors[0] ||
          prediction.explanation.summary
      : prediction.explanation.abstention_explanation ||
          prediction.explanation.summary,
  );
  const supportingItems = prediction.explanation.supporting_factors
    .map(simplifyPublicText)
    .filter(Boolean);
  const cautionItems = prediction.explanation.caution_factors
    .map(simplifyPublicText)
    .filter(Boolean);
  const rejectedItems = prediction.explanation.rejected_alternatives
    .map(simplifyPublicText)
    .filter(Boolean);
  const reminderItems = [
    simplifyPublicText(prediction.explanation.confidence_explanation),
    simplifyPublicText(prediction.explanation.data_quality_summary),
  ].filter(Boolean);

  return (
    <div className="rb-detail-prediction-main-shell">
      <section className="rb-detail-prediction-overview">
        <div
          className={`rb-detail-prediction-decision rb-detail-prediction-decision--${
            isRecommendation ? "recommend" : "abstain"
          }`}
          aria-live="polite"
        >
          <div className="rb-detail-prediction-decision__content">
            <p className="rb-detail-prediction-eyebrow">
              <Target size={15} aria-hidden="true" />
              DÉCISION RUBYBETS
            </p>

            <h2>{decisionTitle}</h2>
            <p className="rb-detail-prediction-decision__summary">
              {decisionSummary}
            </p>

            <div className="rb-detail-prediction-decision__bottomline">
              <div className="rb-detail-prediction-decision__badges">
                <span>
                  <ShieldCheck size={15} aria-hidden="true" />
                  Confiance : {formatLevel(primaryRecommendation?.confidence_level ?? null, true)}
                </span>
                <span className="rb-detail-prediction-decision__badge--risk">
                  <AlertTriangle size={15} aria-hidden="true" />
                  Prudence : {formatLevel(primaryRecommendation?.risk_level ?? null)}
                </span>
              </div>

              <span className="rb-detail-prediction-decision__status">
                <Sparkles size={14} aria-hidden="true" />
                {isRecommendation ? "Recommandé" : "Abstention"}
              </span>
            </div>
          </div>

          <div className="rb-detail-prediction-decision__visual" aria-hidden="true">
            <span><ShieldCheck size={46} /></span>
          </div>
        </div>

        <div className="rb-detail-prediction-signals">
          <header className="rb-detail-prediction-section-title">
            <TrendingUp size={17} aria-hidden="true" />
            <h2>
              {isRecommendation
                ? "Signaux principaux"
                : "Pourquoi RubyBets s’abstient"}
            </h2>
          </header>

          <div className="rb-detail-prediction-signal-grid">
            {signalCards.map((card) => (
              <SignalCardView key={card.key} card={card} />
            ))}
          </div>
        </div>
      </section>

      <section className="rb-detail-prediction-explanations">
        <header className="rb-detail-prediction-section-title">
          <Info size={17} aria-hidden="true" />
          <h2>Pourquoi cette lecture ?</h2>
        </header>

        <div className="rb-detail-prediction-explanation-grid">
          <ExplanationColumn
            icon={<CheckCircle2 size={18} aria-hidden="true" />}
            title={isRecommendation ? "Points favorables" : "Éléments disponibles"}
            items={supportingItems}
            emptyMessage={
              isRecommendation
                ? "Aucun autre point favorable n’a été transmis."
                : "Aucun élément suffisamment favorable n’a été identifié."
            }
            tone="positive"
          />

          <ExplanationColumn
            icon={<AlertTriangle size={18} aria-hidden="true" />}
            title="Points de prudence"
            items={cautionItems}
            emptyMessage="Aucun point de prudence supplémentaire n’a été transmis."
            tone="caution"
          />

          <ExplanationColumn
            icon={<Target size={18} aria-hidden="true" />}
            title="Autres scénarios étudiés"
            items={rejectedItems}
            emptyMessage="Aucun autre scénario n’a été transmis."
            tone="negative"
          />

          <ExplanationColumn
            icon={<Info size={18} aria-hidden="true" />}
            title="À garder en tête"
            items={reminderItems}
            emptyMessage="Aucune précision complémentaire n’a été transmise."
            tone="info"
          />
        </div>
      </section>
    </div>
  );
}

// Ce composant affiche la colonne droite du sous-onglet Prédictions.
export function MatchPredictionSidebar({
  prediction,
  loadState,
  onNavigate,
}: MatchPredictionSidebarProps) {
  if (!prediction) {
    return (
      <section className="rb-detail-prediction-side-card rb-detail-prediction-side-card--responsible">
        <header>
          <span className="rb-detail-prediction-icon-chip">
            <ShieldCheck size={19} aria-hidden="true" />
          </span>
          <h2>Cadre responsable</h2>
        </header>
        <p>
          RubyBets prépare une aide à la lecture avant-match. Aucune décision ne garantit un résultat sportif.
        </p>
        <small>{loadState === "loading" ? "Préparation en cours…" : "Informations en attente."}</small>
      </section>
    );
  }

  const qualityRows = getQualityRows(prediction);
  const responsibleItems = [
    {
      icon: Sparkles,
      title: "Le sport avant tout",
      text: "Le plaisir du jeu reste essentiel.",
    },
    {
      icon: ShieldCheck,
      title: "Usage responsable",
      text: "Gardez vos limites et votre libre jugement.",
    },
    {
      icon: CheckCircle2,
      title: "Décision éclairée",
      text: "Les données aident à réfléchir sans garantir un résultat.",
    },
  ];

  return (
    <>
      <section className="rb-detail-prediction-side-card rb-detail-prediction-side-card--quality">
        <header>
          <span className="rb-detail-prediction-icon-chip">
            <Database size={19} aria-hidden="true" />
          </span>
          <h2>Qualité des informations</h2>
        </header>

        <ul className="rb-detail-prediction-quality-meter-list">
          {qualityRows.map((row) => (
            <li key={row.label}>
              <span>{row.label}</span>
              <span
                className={`rb-detail-prediction-quality-meter is-${row.tone}`}
                aria-label={`${row.label} : ${row.status}`}
                title={row.status}
              >
                {[1, 2, 3, 4].map((step) => (
                  <i
                    key={step}
                    className={step <= row.strength ? "is-active" : ""}
                    aria-hidden="true"
                  />
                ))}
              </span>
            </li>
          ))}
        </ul>

        <p>{simplifyPublicText(prediction.explanation.data_quality_summary)}</p>
      </section>

      <section className="rb-detail-prediction-side-card rb-detail-prediction-side-card--responsible">
        <header>
          <span className="rb-detail-prediction-icon-chip">
            <ShieldCheck size={19} aria-hidden="true" />
          </span>
          <h2>Cadre responsable</h2>
        </header>

        <ul className="rb-detail-prediction-responsible-list">
          {responsibleItems.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.title}>
                <Icon size={18} aria-hidden="true" />
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.text}</span>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="rb-detail-prediction-side-card rb-detail-prediction-side-card--learn">
        <header>
          <span className="rb-detail-prediction-icon-chip">
            <BookOpen size={19} aria-hidden="true" />
          </span>
          <h2>Pour aller plus loin</h2>
        </header>
        <p>Mieux comprendre notre analyse et les termes utilisés dans RubyBets.</p>
        <button type="button" onClick={() => onNavigate("resources")}>
          Voir les ressources
          <BookOpen size={15} aria-hidden="true" />
        </button>
      </section>
    </>
  );
}

// Schéma de communication du fichier :
// App.tsx -> charge la décision publique à la demande
// MatchDetailsScreen.tsx -> affiche le contenu et la colonne droite dans le sous-onglet Prédictions
// MatchPredictionTab.tsx -> transforme uniquement les libellés publics sans recalcul métier
// MatchDetailsScreen.css -> fournit les styles isolés rb-detail-prediction-*
