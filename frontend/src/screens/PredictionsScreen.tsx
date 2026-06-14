// Ce fichier affiche l’écran Prédictions de RubyBets à partir du modèle national expérimental.
// Il présente les signaux 1X2, Over 1.5, BTTS et le signal complémentaire sans utiliser de cote.

import type { CSSProperties, ReactNode } from "react";
import {
  ArrowLeft,
  BarChart3,
  CalendarDays,
  Eye,
  Gauge,
  Info,
  ShieldCheck,
  Sparkles,
  Trophy,
  Zap,
} from "lucide-react";
import type {
  MatchContextResponse,
  MatchDetailsResponse,
  NationalMlMarketKey,
  NationalMlMarketPrediction,
  NationalMlPredictionResponse,
  NationalMlSelectorResult,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";

type PredictionsScreenProps = {
  nationalMlPrediction: NationalMlPredictionResponse | null;
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  matchPredictionsStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

type UnknownRecord = Record<string, unknown>;

type DisplayMarket = {
  key: NationalMlMarketKey | "selector";
  title: string;
  subtitle: string;
  predictionLabel: string;
  probabilityLabel: string;
  modelLabel: string;
  reading: string;
  muted: boolean;
};

// Cette fonction vérifie qu’une valeur peut être lue comme un objet simple.
function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Cette fonction lit une valeur texte dans plusieurs chemins possibles pour rester compatible avec les contrats API.
function readText(source: unknown, paths: string[][], fallback: string): string {
  for (const path of paths) {
    let current: unknown = source;

    for (const segment of path) {
      if (!isRecord(current)) {
        current = undefined;
        break;
      }

      current = current[segment];
    }

    if (typeof current === "string" && current.trim().length > 0) {
      return current;
    }

    if (typeof current === "number") {
      return String(current);
    }
  }

  return fallback;
}

// Cette fonction formate une date de match dans un libellé court.
function formatMatchDate(source: unknown): string {
  const rawDate = readText(
    source,
    [["utc_date"], ["utcDate"], ["date"], ["match_date"], ["matchDate"], ["match", "utc_date"]],
    ""
  );

  if (!rawDate) {
    return "Date à confirmer";
  }

  const parsedDate = new Date(rawDate);

  if (Number.isNaN(parsedDate.getTime())) {
    return rawDate;
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(parsedDate);
}

// Cette fonction formate l’heure de coup d’envoi.
function formatMatchTime(source: unknown): string {
  const rawDate = readText(
    source,
    [["utc_date"], ["utcDate"], ["date"], ["match_date"], ["matchDate"], ["match", "utc_date"]],
    ""
  );

  if (!rawDate) {
    return "Heure à confirmer";
  }

  const parsedDate = new Date(rawDate);

  if (Number.isNaN(parsedDate.getTime())) {
    return readText(source, [["time"], ["kickoff_time"], ["kickoffTime"]], "Heure à confirmer");
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsedDate);
}

// Cette fonction convertit une probabilité numérique en pourcentage lisible.
function formatProbability(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "non disponible";
  }

  const percentage = value > 0 && value <= 1 ? value * 100 : value;
  return `${Math.round(percentage)} %`;
}

// Cette fonction convertit une probabilité en valeur numérique 0-100 exploitable par la jauge.
function probabilityToGaugeValue(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return 0;
  }

  const percentage = value > 0 && value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, Math.round(percentage)));
}

// Cette fonction convertit un niveau de risque technique en libellé utilisateur.
function formatRisk(value: string | null | undefined): string {
  const normalizedValue = (value || "").toLowerCase();

  if (normalizedValue.includes("high") || normalizedValue.includes("élev")) {
    return "élevé";
  }

  if (normalizedValue.includes("medium") || normalizedValue.includes("mod")) {
    return "modéré";
  }

  if (normalizedValue.includes("low") || normalizedValue.includes("faib")) {
    return "faible";
  }

  return value || "non fourni";
}

// Cette fonction transforme une clé de marché technique en libellé visible.
function formatMarketName(marketKey: string): string {
  const normalizedMarket = marketKey.toLowerCase();

  if (normalizedMarket === "1x2") {
    return "1X2";
  }

  if (normalizedMarket === "over_1_5") {
    return "Nombre de buts · Over 1.5";
  }

  if (normalizedMarket === "over_2_5") {
    return "Nombre de buts · Over 2.5";
  }

  if (normalizedMarket === "btts") {
    return "BTTS";
  }

  return marketKey.replaceAll("_", " ").toUpperCase();
}

// Cette fonction récupère le nom de l’équipe à domicile.
function getHomeTeamName(matchDetails: MatchDetailsResponse | null): string {
  return readText(
    matchDetails,
    [
      ["home_team", "name"],
      ["homeTeam", "name"],
      ["home_team_name"],
      ["homeTeamName"],
      ["match", "home_team", "name"],
    ],
    "Équipe domicile"
  );
}

// Cette fonction récupère le nom de l’équipe extérieure.
function getAwayTeamName(matchDetails: MatchDetailsResponse | null): string {
  return readText(
    matchDetails,
    [
      ["away_team", "name"],
      ["awayTeam", "name"],
      ["away_team_name"],
      ["awayTeamName"],
      ["match", "away_team", "name"],
    ],
    "Équipe extérieure"
  );
}

// Cette fonction récupère le logo ou blason d’une équipe depuis les différentes formes possibles du contrat API.
function getTeamLogo(matchDetails: MatchDetailsResponse | null, side: "home" | "away"): string {
  const prefix = side === "home" ? "home" : "away";

  return readText(
    matchDetails,
    [
      [`${prefix}_team`, "crest"],
      [`${prefix}_team`, "logo"],
      [`${prefix}Team`, "crest"],
      [`${prefix}Team`, "logo"],
      [`${prefix}_team_crest`],
      [`${prefix}TeamCrest`],
      ["match", `${prefix}_team`, "crest"],
      ["match", `${prefix}_team`, "logo"],
      ["match", `${prefix}Team`, "crest"],
      ["match", `${prefix}Team`, "logo"],
    ],
    ""
  );
}

// Cette fonction récupère le nom de la compétition.
function getCompetitionName(matchDetails: MatchDetailsResponse | null): string {
  return readText(
    matchDetails,
    [
      ["competition", "name"],
      ["competition_name"],
      ["competitionName"],
      ["match", "competition", "name"],
    ],
    "Compétition"
  );
}

// Cette fonction récupère la journée ou phase affichable du match.
function getMatchRound(matchDetails: MatchDetailsResponse | null): string {
  const round = readText(
    matchDetails,
    [
      ["matchday"],
      ["round"],
      ["stage"],
      ["group_name"],
      ["groupName"],
      ["match", "matchday"],
      ["match", "stage"],
    ],
    "Phase à confirmer"
  );

  if (/^\d+$/.test(round)) {
    return `Journée ${round}`;
  }

  return round;
}

// Cette fonction affiche un logo d’équipe ou un fallback textuel propre.
function TeamVisual({ logo, name }: { logo: string; name: string }) {
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join("");

  if (logo) {
    return <img src={logo} alt="" className="rb-pred-v3-match-card__crest" loading="lazy" />;
  }

  return (
    <span className="rb-pred-v3-match-card__fallback" aria-hidden="true">
      {initials || "RB"}
    </span>
  );
}

// Cette fonction traduit la sortie 1X2 du modèle national en libellé utilisateur.
function formatOneXTwoPrediction(
  prediction: string | null | undefined,
  homeTeamName: string,
  awayTeamName: string
): string {
  const normalizedPrediction = (prediction || "").toUpperCase();

  if (normalizedPrediction === "TEAM_A_WIN" || normalizedPrediction.includes("HOME")) {
    return `${homeTeamName} gagnant`;
  }

  if (normalizedPrediction === "TEAM_B_WIN" || normalizedPrediction.includes("AWAY")) {
    return `${awayTeamName} gagnant`;
  }

  if (normalizedPrediction.includes("DRAW")) {
    return "Match nul";
  }

  return "Tendance 1X2 non disponible";
}

// Cette fonction traduit la sortie Over 1.5 en libellé utilisateur.
function formatOverOneFivePrediction(prediction: string | null | undefined): string {
  const normalizedPrediction = (prediction || "").toUpperCase();

  if (normalizedPrediction === "YES") {
    return "Plus de 1,5 but";
  }

  if (normalizedPrediction === "NO") {
    return "Moins de 1,5 but";
  }

  return "Volume de buts non disponible";
}

// Cette fonction traduit la sortie BTTS en libellé utilisateur.
function formatBttsPrediction(prediction: string | null | undefined): string {
  const normalizedPrediction = (prediction || "").toUpperCase();

  if (normalizedPrediction === "YES") {
    return "Oui · les deux équipes marquent";
  }

  if (normalizedPrediction === "NO") {
    return "Non · BTTS non prioritaire";
  }

  return "BTTS non disponible";
}

// Cette fonction traduit le signal sélectionné par le modèle en libellé utilisateur.
function formatSelectorPrediction(
  selector: NationalMlSelectorResult,
  homeTeamName: string,
  awayTeamName: string
): string {
  const market = selector.selected_market.toUpperCase();
  const prediction = (selector.selected_prediction || "").toUpperCase();

  if (market === "1X2") {
    return formatOneXTwoPrediction(prediction, homeTeamName, awayTeamName);
  }

  if (market === "OVER_1_5") {
    return prediction === "YES" ? "Plus de 1,5 but" : "Moins de 1,5 but";
  }

  if (market === "OVER_2_5") {
    return prediction === "YES" ? "Plus de 2,5 buts" : "Moins de 2,5 buts";
  }

  if (market === "BTTS") {
    return formatBttsPrediction(prediction);
  }

  return selector.selected_prediction || "Signal non disponible";
}

// Cette fonction construit la carte 1X2 à partir du modèle national.
function buildOneXTwoDisplayMarket(
  market: NationalMlMarketPrediction | undefined,
  homeTeamName: string,
  awayTeamName: string
): DisplayMarket {
  if (!market) {
    return {
      key: "1x2",
      title: "1X2",
      subtitle: "Résultat du match",
      predictionLabel: "Donnée modèle indisponible",
      probabilityLabel: "non disponible",
      modelLabel: "Modèle non appelé",
      reading: "Le modèle national n’a pas retourné de signal 1X2 exploitable pour ce match.",
      muted: true,
    };
  }

  return {
    key: "1x2",
    title: "1X2",
    subtitle: "Résultat du match",
    predictionLabel: formatOneXTwoPrediction(market.prediction, homeTeamName, awayTeamName),
    probabilityLabel: formatProbability(market.max_probability),
    modelLabel: market.model_name,
    reading: "Lecture produite par le modèle national expérimental à partir des features disponibles.",
    muted: false,
  };
}

// Cette fonction construit la carte Nombre de buts à partir de over_1_5.
function buildGoalsDisplayMarket(market: NationalMlMarketPrediction | undefined): DisplayMarket {
  if (!market) {
    return {
      key: "over_1_5",
      title: "Nombre de buts",
      subtitle: "Marché Over 1.5",
      predictionLabel: "Donnée modèle indisponible",
      probabilityLabel: "non disponible",
      modelLabel: "Modèle non appelé",
      reading: "Le modèle national n’a pas retourné de signal Over 1.5 exploitable pour ce match.",
      muted: true,
    };
  }

  return {
    key: "over_1_5",
    title: "Nombre de buts",
    subtitle: "Marché Over 1.5",
    predictionLabel: formatOverOneFivePrediction(market.prediction),
    probabilityLabel: formatProbability(market.max_probability),
    modelLabel: market.model_name,
    reading: "RubyBets affiche ici le marché Over 1.5 demandé pour la lecture du volume de buts.",
    muted: false,
  };
}

// Cette fonction construit la carte BTTS à partir du modèle national.
function buildBttsDisplayMarket(market: NationalMlMarketPrediction | undefined): DisplayMarket {
  if (!market) {
    return {
      key: "btts",
      title: "BTTS",
      subtitle: "Les deux équipes marquent",
      predictionLabel: "Donnée modèle indisponible",
      probabilityLabel: "non disponible",
      modelLabel: "Modèle non appelé",
      reading: "Le modèle national n’a pas retourné de signal BTTS exploitable pour ce match.",
      muted: true,
    };
  }

  return {
    key: "btts",
    title: "BTTS",
    subtitle: "Les deux équipes marquent",
    predictionLabel: formatBttsPrediction(market.prediction),
    probabilityLabel: formatProbability(market.max_probability),
    modelLabel: market.model_name,
    reading: "Signal BTTS calculé par le modèle national expérimental, sans utiliser de cote.",
    muted: false,
  };
}

// Cette fonction choisit le meilleur signal disponible si le sélecteur ne retourne rien.
function findBestMarketFallback(
  marketPredictions: NationalMlPredictionResponse["market_predictions"]
): { key: string; market: NationalMlMarketPrediction } | null {
  if (!marketPredictions) {
    return null;
  }

  const entries = Object.entries(marketPredictions).filter(
    (entry): entry is [string, NationalMlMarketPrediction] => Boolean(entry[1])
  );

  return entries.reduce<{ key: string; market: NationalMlMarketPrediction } | null>(
    (best, [key, market]) => {
      if (!best || market.max_probability > best.market.max_probability) {
        return { key, market };
      }

      return best;
    },
    null
  );
}

// Cette fonction affiche une carte de prédiction compacte.
function PredictionCard({
  icon,
  title,
  subtitle,
  bodyTitle,
  bodyText,
  probability,
  modelName,
  muted = false,
}: {
  icon: ReactNode;
  title: string;
  subtitle: string;
  bodyTitle: string;
  bodyText: string;
  probability: string;
  modelName: string;
  muted?: boolean;
}) {
  const cardClassName = muted
    ? "rb-pred-v3-prediction-card rb-pred-v3-prediction-card--muted"
    : "rb-pred-v3-prediction-card";

  return (
    <article className={cardClassName}>
      <header className="rb-pred-v3-prediction-card__head">
        <span className="rb-pred-v3-icon-chip">{icon}</span>
        <span>
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </span>
      </header>

      <div className="rb-pred-v3-prediction-card__body">
        <strong>{bodyTitle}</strong>
        <p>{bodyText}</p>
      </div>

      <div className="rb-pred-v3-prediction-card__meta">
        <span>
          <BarChart3 size={15} aria-hidden="true" />
          Probabilité : {probability}
        </span>
        <span>
          <Gauge size={15} aria-hidden="true" />
          Modèle : {modelName}
        </span>
      </div>
    </article>
  );
}

// Cette fonction affiche une ligne courte dans la sidebar.
function SidebarLine({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <li className="rb-pred-v3-sidebar-line">
      <span>{icon}</span>
      <p>{children}</p>
    </li>
  );
}

// Ce composant affiche l’écran Prédictions à partir du modèle national expérimental chargé par App.tsx.
function PredictionsScreen({
  nationalMlPrediction,
  matchDetails,
  matchContext,
  matchPredictionsStatus,
  onNavigate,
}: PredictionsScreenProps) {
  const homeTeamName = getHomeTeamName(matchDetails);
  const awayTeamName = getAwayTeamName(matchDetails);
  const homeLogo = getTeamLogo(matchDetails, "home");
  const awayLogo = getTeamLogo(matchDetails, "away");
  const competitionName = getCompetitionName(matchDetails);
  const matchRound = getMatchRound(matchDetails);
  const matchDate = formatMatchDate(matchDetails);
  const matchTime = formatMatchTime(matchDetails);
  const isModelComputed = nationalMlPrediction?.status === "computed";
  const marketPredictions = nationalMlPrediction?.market_predictions;
  const selectorResult = nationalMlPrediction?.selector_result ?? null;

  const oneXTwoMarket = buildOneXTwoDisplayMarket(
    marketPredictions?.["1x2"],
    homeTeamName,
    awayTeamName
  );
  const goalsMarket = buildGoalsDisplayMarket(marketPredictions?.over_1_5);
  const bttsMarket = buildBttsDisplayMarket(marketPredictions?.btts);
  const bestMarketFallback = findBestMarketFallback(marketPredictions);

  const selectorPredictionLabel = selectorResult
    ? formatSelectorPrediction(selectorResult, homeTeamName, awayTeamName)
    : bestMarketFallback
      ? bestMarketFallback.market.prediction
      : "Signal complémentaire indisponible";

  const selectorMarketLabel = selectorResult
    ? formatMarketName(selectorResult.selected_market)
    : bestMarketFallback
      ? formatMarketName(bestMarketFallback.key)
      : "Signal modèle";

  const selectorConfidenceLabel = selectorResult
    ? formatProbability(selectorResult.selected_confidence)
    : bestMarketFallback
      ? formatProbability(bestMarketFallback.market.max_probability)
      : "non disponible";

  const referenceReliabilityLabel = selectorResult?.reference_reliability
    ? formatProbability(selectorResult.reference_reliability)
    : "non disponible";

  const gaugeValue = selectorResult?.reference_reliability
    ? probabilityToGaugeValue(selectorResult.reference_reliability)
    : probabilityToGaugeValue(bestMarketFallback?.market.max_probability);

  const safeGaugeValue = gaugeValue || 0;
  const gaugeStyle = {
    "--rb-pred-v3-gauge": `${Math.round((safeGaugeValue / 100) * 360)}deg`,
  } as CSSProperties;

  const predictionStatusLabel = isModelComputed
    ? "Modèle national calculé"
    : matchPredictionsStatus || "Modèle national indisponible";

  const globalRisk = formatRisk(selectorResult?.risk_level);
  const globalConfidence = safeGaugeValue >= 80
    ? "fiabilité de référence élevée"
    : safeGaugeValue >= 60
      ? "fiabilité de référence modérée"
      : "fiabilité de référence limitée";

  const contextSummary = readText(
    matchContext,
    [["context", "summary", "title"], ["summary"], ["main_context"], ["context"], ["overview"]],
    "Match analysé avant le coup d’envoi, à partir des données disponibles."
  );

  const unavailableReason = nationalMlPrediction?.unavailable_reason ||
    "Le modèle national expérimental n’a pas retourné de prédiction calculable pour ce match.";

  return (
    <div className="rb-pred-v3-screen">
      <header className="rb-pred-v3-header">
        <button
          type="button"
          className="rb-pred-v3-back"
          onClick={() => onNavigate("matches")}
        >
          <ArrowLeft size={17} aria-hidden="true" />
          Retour aux matchs
        </button>

        <div className="rb-pred-v3-title-row">
          <div className="rb-pred-v3-title">
            <span className="rb-pred-v3-title__icon">
              <BarChart3 size={25} aria-hidden="true" />
            </span>
            <div>
              <h2>Prédictions</h2>
              <p>Signaux du modèle RubyBets national expérimental.</p>
            </div>
          </div>

          <button
            type="button"
            className="rb-pred-v3-secondary-action"
            onClick={() => onNavigate("analysis")}
          >
            <BarChart3 size={16} aria-hidden="true" />
            Voir l’analyse du match
          </button>
        </div>
      </header>

      <section className="rb-pred-v3-detail-hero" aria-label="Résumé du match">
        <span className="rb-pred-v3-detail-hero__glow" aria-hidden="true" />
        <span className="rb-pred-v3-detail-hero__pitch" aria-hidden="true" />

        <div className="rb-pred-v3-detail-team rb-pred-v3-detail-team--home">
          <TeamVisual logo={homeLogo} name={homeTeamName} />
          <div>
            <p>Domicile</p>
            <h3>{homeTeamName}</h3>
            <span>Équipe A du modèle</span>
          </div>
        </div>

        <div className="rb-pred-v3-detail-hero-center">
          <p>{matchDate}</p>
          <strong>{matchTime}</strong>
          <span>Programmé</span>
          <small>{competitionName} · {matchRound}</small>
        </div>

        <div className="rb-pred-v3-detail-team rb-pred-v3-detail-team--away">
          <TeamVisual logo={awayLogo} name={awayTeamName} />
          <div>
            <p>Extérieur</p>
            <h3>{awayTeamName}</h3>
            <span>Équipe B du modèle</span>
          </div>
        </div>
      </section>

      <div className="rb-pred-v3-layout">
        <main className="rb-pred-v3-main">
          <section className="rb-pred-v3-panel">
            <header className="rb-pred-v3-panel__header">
              <div>
                <p className="rb-pred-v3-eyebrow">MODÈLE RUBYBETS NATIONAL EXPÉRIMENTAL</p>
                <h3>Prédictions par marché</h3>
                <span>
                  Basées sur le modèle national V18.3.4 dc018, sans cote FlashScore et sans promesse de résultat.
                </span>
              </div>

              <span className="rb-pred-v3-status">
                <i aria-hidden="true" />
                {predictionStatusLabel}
              </span>
            </header>

            {!isModelComputed && (
              <article className="rb-pred-v3-signal-card">
                <div className="rb-pred-v3-signal-card__title">
                  <Info size={22} aria-hidden="true" />
                  <div>
                    <p>MODÈLE INDISPONIBLE</p>
                    <h4>Prédiction nationale non calculable</h4>
                    <span>{unavailableReason}</span>
                  </div>
                </div>
              </article>
            )}

            <div className="rb-pred-v3-predictions-grid">
              <PredictionCard
                icon={<Trophy size={17} aria-hidden="true" />}
                title={oneXTwoMarket.title}
                subtitle={oneXTwoMarket.subtitle}
                bodyTitle={oneXTwoMarket.predictionLabel}
                bodyText={oneXTwoMarket.reading}
                probability={oneXTwoMarket.probabilityLabel}
                modelName={oneXTwoMarket.modelLabel}
                muted={oneXTwoMarket.muted}
              />

              <PredictionCard
                icon={<BarChart3 size={17} aria-hidden="true" />}
                title={goalsMarket.title}
                subtitle={goalsMarket.subtitle}
                bodyTitle={goalsMarket.predictionLabel}
                bodyText={goalsMarket.reading}
                probability={goalsMarket.probabilityLabel}
                modelName={goalsMarket.modelLabel}
                muted={goalsMarket.muted}
              />

              <PredictionCard
                icon={<Sparkles size={17} aria-hidden="true" />}
                title={bttsMarket.title}
                subtitle={bttsMarket.subtitle}
                bodyTitle={bttsMarket.predictionLabel}
                bodyText={bttsMarket.reading}
                probability={bttsMarket.probabilityLabel}
                modelName={bttsMarket.modelLabel}
                muted={bttsMarket.muted}
              />
            </div>

            <article className="rb-pred-v3-signal-card rb-pred-v3-signal-card--premium-final">
              <div className="rb-pred-v3-signal-card__title">
                <Zap size={22} aria-hidden="true" />
                <div>
                  <p>SIGNAL COMPLÉMENTAIRE</p>
                  <h4>{selectorMarketLabel} · {selectorPredictionLabel}</h4>
                  <span>
                    Signal sélectionné par le modèle national expérimental selon son profil prudent.
                  </span>
                </div>
              </div>

              <div className="rb-pred-v3-signal-card__premium-side">
                <strong>{selectorConfidenceLabel}</strong>
                <span>Confiance sélection</span>

                <div className="rb-pred-v3-signal-card__badges">
                  <span>Fiabilité réf. {referenceReliabilityLabel}</span>
                  <span>Risque {globalRisk}</span>
                </div>
              </div>
            </article>
          </section>

          <section className="rb-pred-v3-panel rb-pred-v3-global-reading">
            <p className="rb-pred-v3-eyebrow">LECTURE GLOBALE DE LA RENCONTRE</p>
            <h3>Synthèse des signaux modèle</h3>
            <p>
              Les cartes affichent les trois marchés principaux demandés : 1X2, Over 1.5 et BTTS.
              Le signal complémentaire correspond au marché sélectionné par le modèle national expérimental,
              avec sa confiance et sa fiabilité de référence lorsqu’elles sont disponibles.
            </p>

            <div className="rb-pred-v3-reading-grid">
              <article>
                <Gauge size={30} aria-hidden="true" />
                <strong>{globalConfidence}</strong>
                <span>Lecture issue des métriques de référence du sélecteur.</span>
              </article>

              <article>
                <ShieldCheck size={30} aria-hidden="true" />
                <strong>Cadre expérimental</strong>
                <span>Le modèle national reste une aide analytique, pas une garantie.</span>
              </article>

              <article>
                <Eye size={30} aria-hidden="true" />
                <strong>Aucune cote utilisée</strong>
                <span>RubyBets n’utilise pas les odds FlashScore pour cet écran.</span>
              </article>
            </div>
          </section>

          <p className="rb-pred-v3-footer-note">
            <Info size={16} aria-hidden="true" />
            Les prédictions présentées sont expérimentales et ne garantissent aucun résultat sportif.
          </p>
        </main>

        <aside className="rb-pred-v3-sidebar">
          <section className="rb-pred-v3-side-card rb-pred-v3-side-card--summary">
            <p className="rb-pred-v3-eyebrow">SYNTHÈSE GLOBALE</p>

            <div className="rb-pred-v3-gauge-row">
              <div className="rb-pred-v3-gauge" style={gaugeStyle}>
                <span>{safeGaugeValue}%</span>
              </div>

              <div>
                <span>Fiabilité référence</span>
                <strong>{globalConfidence}</strong>
                <p>Risque signal : {globalRisk}.</p>
                <small>Basée uniquement sur la réponse du modèle national.</small>
              </div>
            </div>
          </section>

          <section className="rb-pred-v3-side-card">
            <p className="rb-pred-v3-eyebrow">EN RÉSUMÉ</p>

            <ul className="rb-pred-v3-sidebar-list">
              <SidebarLine icon={<Trophy size={17} aria-hidden="true" />}>
                1X2 : {oneXTwoMarket.predictionLabel} · {oneXTwoMarket.probabilityLabel}.
              </SidebarLine>
              <SidebarLine icon={<BarChart3 size={17} aria-hidden="true" />}>
                Nombre de buts : {goalsMarket.predictionLabel} · {goalsMarket.probabilityLabel}.
              </SidebarLine>
              <SidebarLine icon={<Sparkles size={17} aria-hidden="true" />}>
                BTTS : {bttsMarket.predictionLabel} · {bttsMarket.probabilityLabel}.
              </SidebarLine>
              <SidebarLine icon={<Zap size={17} aria-hidden="true" />}>
                Signal complémentaire : {selectorMarketLabel} · {selectorConfidenceLabel}.
              </SidebarLine>
            </ul>
          </section>

          <section className="rb-pred-v3-side-card">
            <p className="rb-pred-v3-eyebrow">CONTEXTE & ENJEUX</p>

            <ul className="rb-pred-v3-sidebar-list">
              <SidebarLine icon={<CalendarDays size={17} aria-hidden="true" />}>
                Match analysé avant le coup d’envoi.
              </SidebarLine>
              <SidebarLine icon={<ShieldCheck size={17} aria-hidden="true" />}>
                Source match : {nationalMlPrediction?.source_used_for_match || "donnée non disponible"}.
              </SidebarLine>
              <SidebarLine icon={<Info size={17} aria-hidden="true" />}>
                {contextSummary}
              </SidebarLine>
            </ul>
          </section>

          <section className="rb-pred-v3-side-card rb-pred-v3-side-card--responsible">
            <ShieldCheck size={30} aria-hidden="true" />
            <div>
              <p className="rb-pred-v3-eyebrow">CADRE RESPONSABLE</p>
              <p>
                RubyBets est un outil d’aide à la décision. Le modèle national expérimental produit des signaux,
                mais ne garantit aucun résultat.
              </p>
              <strong>Aucune cote FlashScore utilisée.</strong>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

export default PredictionsScreen;

// Schéma de communication du fichier :
// PredictionsScreen.tsx
// ├── reçoit nationalMlPrediction, matchDetails et matchContext depuis App.tsx
// ├── affiche 1X2, Over 1.5, BTTS et Signal complémentaire depuis le modèle national
// ├── n’utilise aucune cote FlashScore et ne calcule pas de prédiction côté interface
// └── utilise App.css avec les classes rb-pred-v3-* sans modifier le backend
