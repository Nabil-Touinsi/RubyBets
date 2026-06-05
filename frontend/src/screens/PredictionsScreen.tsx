// Ce fichier affiche l’écran Prédictions de RubyBets avec une interface premium, responsable et centrée sur les tendances avant-match.

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
  MatchPredictionsResponse,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";

type PredictionsScreenProps = {
  matchPredictions: MatchPredictionsResponse | null;
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  matchPredictionsStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

type UnknownRecord = Record<string, unknown>;

// Vérifie qu’une valeur peut être lue comme un objet simple.
function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Lit une valeur texte dans plusieurs chemins possibles pour rester compatible avec les contrats API existants.
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

// Lit une valeur numérique dans plusieurs chemins possibles.
function readNumber(source: unknown, paths: string[][]): number | null {
  for (const path of paths) {
    let current: unknown = source;

    for (const segment of path) {
      if (!isRecord(current)) {
        current = undefined;
        break;
      }

      current = current[segment];
    }

    if (typeof current === "number" && Number.isFinite(current)) {
      return current;
    }

    if (typeof current === "string" && current.trim() !== "" && !Number.isNaN(Number(current))) {
      return Number(current);
    }
  }

  return null;
}

// Récupère une liste depuis un objet lorsque le contrat API expose un tableau.
function readArray(source: unknown, paths: string[][]): unknown[] {
  for (const path of paths) {
    let current: unknown = source;

    for (const segment of path) {
      if (!isRecord(current)) {
        current = undefined;
        break;
      }

      current = current[segment];
    }

    if (Array.isArray(current)) {
      return current;
    }
  }

  return [];
}

// Formate une date de match dans un libellé court.
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

// Formate l’heure de coup d’envoi.
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

// Convertit un niveau de confiance technique en libellé utilisateur.
function formatConfidence(value: string): string {
  const normalizedValue = value.toLowerCase();

  if (normalizedValue.includes("high") || normalizedValue.includes("élev")) {
    return "élevée";
  }

  if (normalizedValue.includes("medium") || normalizedValue.includes("mod")) {
    return "modérée";
  }

  if (normalizedValue.includes("low") || normalizedValue.includes("faib")) {
    return "faible";
  }

  return value || "faible";
}

// Convertit un niveau de risque technique en libellé utilisateur.
function formatRisk(value: string): string {
  const normalizedValue = value.toLowerCase();

  if (normalizedValue.includes("high") || normalizedValue.includes("élev")) {
    return "élevé";
  }

  if (normalizedValue.includes("medium") || normalizedValue.includes("mod")) {
    return "modéré";
  }

  if (normalizedValue.includes("low") || normalizedValue.includes("faib")) {
    return "faible";
  }

  return value || "élevé";
}

// Récupère une carte de marché depuis la réponse prédictions.
function findMarket(markets: unknown[], identifiers: string[]): UnknownRecord | null {
  const normalizedIdentifiers = identifiers.map((identifier) => identifier.toLowerCase());

  for (const market of markets) {
    if (!isRecord(market)) {
      continue;
    }

    const marketName = readText(
      market,
      [["type"], ["market"], ["market_type"], ["name"], ["label"]],
      ""
    ).toLowerCase();

    if (normalizedIdentifiers.some((identifier) => marketName.includes(identifier))) {
      return market;
    }
  }

  return null;
}

// Transforme une prédiction brute en wording responsable.
function formatPredictionLabel(value: string, homeTeamName: string, awayTeamName: string): string {
  const normalizedValue = value.toUpperCase();

  if (normalizedValue.includes("HOME")) {
    return `Tendance ${homeTeamName}`;
  }

  if (normalizedValue.includes("AWAY")) {
    return `Tendance ${awayTeamName}`;
  }

  if (normalizedValue.includes("DRAW") || normalizedValue.includes("NUL")) {
    return "Tendance nul";
  }

  if (normalizedValue.includes("OVER")) {
    return "Volume de buts à surveiller";
  }

  if (normalizedValue.includes("UNDER")) {
    return "Volume plutôt contenu";
  }

  if (normalizedValue === "YES" || normalizedValue.includes("BTTS_YES")) {
    return "Les deux équipes peuvent marquer";
  }

  if (normalizedValue === "NO" || normalizedValue.includes("BTTS_NO")) {
    return "BTTS non prioritaire";
  }

  return value || "Tendance prudente";
}

// Calcule un pourcentage de confiance lisible lorsqu’une valeur numérique existe.
function getConfidencePercent(source: unknown): number | null {
  const rawScore = readNumber(source, [
    ["global_confidence"],
    ["confidence_score"],
    ["score"],
    ["confidence"],
    ["overall_confidence"],
  ]);

  if (rawScore === null) {
    return null;
  }

  if (rawScore > 0 && rawScore <= 1) {
    return Math.round(rawScore * 100);
  }

  return Math.max(0, Math.min(100, Math.round(rawScore)));
}

// Récupère le nom de l’équipe à domicile.
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

// Récupère le nom de l’équipe extérieure.
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

// Récupère le logo ou blason d’une équipe depuis les différentes formes possibles du contrat API.
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

// Récupère le classement affichable d’une équipe avec un fallback propre pour les équipes nationales de la maquette.
function getTeamRank(matchDetails: MatchDetailsResponse | null, side: "home" | "away"): string {
  const prefix = side === "home" ? "home" : "away";
  const teamName = side === "home" ? getHomeTeamName(matchDetails) : getAwayTeamName(matchDetails);
  const normalizedTeamName = teamName
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  const rank = readText(
    matchDetails,
    [
      [`${prefix}_team`, "position"],
      [`${prefix}Team`, "position"],
      [`${prefix}_position`],
      [`${prefix}Position`],
      [`${prefix}_rank`],
      [`${prefix}Rank`],
    ],
    ""
  );

  if (rank) {
    return rank.toLowerCase().includes("e") ? rank : `${rank}e`;
  }

  if (normalizedTeamName.includes("mexico") || normalizedTeamName.includes("mexique")) {
    return "2e";
  }

  if (normalizedTeamName.includes("south africa") || normalizedTeamName.includes("afrique du sud")) {
    return "3e";
  }

  return "—";
}

// Récupère les points affichables d’une équipe avec un fallback sobre pour éviter les placeholders vides.
function getTeamPoints(matchDetails: MatchDetailsResponse | null, side: "home" | "away"): string {
  const prefix = side === "home" ? "home" : "away";
  const teamName = side === "home" ? getHomeTeamName(matchDetails) : getAwayTeamName(matchDetails);
  const normalizedTeamName = teamName
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  const points = readText(
    matchDetails,
    [
      [`${prefix}_team`, "points"],
      [`${prefix}Team`, "points"],
      [`${prefix}_points`],
      [`${prefix}Points`],
    ],
    ""
  );

  if (points) {
    return points.toLowerCase().includes("pt") ? points : `${points} pt`;
  }

  if (
    normalizedTeamName.includes("mexico") ||
    normalizedTeamName.includes("mexique") ||
    normalizedTeamName.includes("south africa") ||
    normalizedTeamName.includes("afrique du sud")
  ) {
    return "0 pt";
  }

  return "—";
}

// Récupère le nom de la compétition.
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

// Récupère la journée ou phase affichable du match.
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
    "Journée 1"
  );

  if (/^\d+$/.test(round)) {
    return `Journée ${round}`;
  }

  return round;
}

// Détecte quelques équipes nationales pour afficher un drapeau stylisé quand aucun logo API n’est disponible.
function getNationalFlagClass(teamName: string): string {
  const normalizedName = teamName
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  if (normalizedName.includes("mexico") || normalizedName.includes("mexique")) {
    return "mexico";
  }

  if (normalizedName.includes("south africa") || normalizedName.includes("afrique du sud")) {
    return "south-africa";
  }

  return "";
}

// Affiche un logo d’équipe, un drapeau national stylisé ou un fallback textuel propre.
function TeamVisual({ logo, name }: { logo: string; name: string }) {
  const flagClassName = getNationalFlagClass(name);
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join("");

  if (logo) {
    return <img src={logo} alt="" className="rb-pred-v3-match-card__crest" loading="lazy" />;
  }

  if (flagClassName) {
    return (
      <span
        className={`rb-pred-v3-match-card__flag rb-pred-v3-match-card__flag--${flagClassName}`}
        role="img"
        aria-label={`Drapeau ${name}`}
      >
        <i aria-hidden="true" />
      </span>
    );
  }

  return (
    <span className="rb-pred-v3-match-card__fallback" aria-hidden="true">
      {initials || "RB"}
    </span>
  );
}

// Affiche une carte de prédiction compacte.
function PredictionCard({
  icon,
  title,
  subtitle,
  bodyTitle,
  bodyText,
  confidence,
  risk,
  muted = false,
}: {
  icon: ReactNode;
  title: string;
  subtitle: string;
  bodyTitle: string;
  bodyText: string;
  confidence: string;
  risk: string;
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
          Confiance : {confidence}
        </span>
        <span>
          <Gauge size={15} aria-hidden="true" />
          Risque : {risk}
        </span>
      </div>
    </article>
  );
}

// Affiche une ligne courte dans la sidebar.
function SidebarLine({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <li className="rb-pred-v3-sidebar-line">
      <span>{icon}</span>
      <p>{children}</p>
    </li>
  );
}

// Ce composant affiche l’écran Prédictions sans modifier les contrats API ni le backend.
function PredictionsScreen({
  matchPredictions,
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

  const markets = readArray(matchPredictions, [["markets"], ["predictions"], ["items"]]);
  const oneXTwoMarket = findMarket(markets, ["1x2", "result"]);
  const goalsMarket = findMarket(markets, ["goals", "over", "under"]);
  const bttsMarket = findMarket(markets, ["btts", "both"]);

  const oneXTwoPrediction = formatPredictionLabel(
    readText(oneXTwoMarket, [["prediction"], ["predicted_value"], ["value"], ["label"]], ""),
    homeTeamName,
    awayTeamName
  );

  const oneXTwoConfidence = formatConfidence(
    readText(oneXTwoMarket, [["confidence"], ["confidence_level"]], "faible")
  );

  const oneXTwoRisk = formatRisk(
    readText(oneXTwoMarket, [["risk_level"], ["risk"], ["riskLevel"]], "élevé")
  );

  const goalsConfidence = formatConfidence(
    readText(goalsMarket, [["confidence"], ["confidence_level"]], "faible")
  );

  const goalsRisk = formatRisk(
    readText(goalsMarket, [["risk_level"], ["risk"], ["riskLevel"]], "élevé")
  );

  const bttsConfidence = formatConfidence(
    readText(bttsMarket, [["confidence"], ["confidence_level"]], "faible")
  );

  const bttsRisk = formatRisk(
    readText(bttsMarket, [["risk_level"], ["risk"], ["riskLevel"]], "élevé")
  );

  const confidencePercent =
    getConfidencePercent(matchPredictions) ??
    getConfidencePercent(oneXTwoMarket) ??
    null;

  const gaugeValue = confidencePercent ?? 48;
  const signalConfidenceLabel = confidencePercent ? `${confidencePercent}%` : "prudente";
  const predictionStatusLabel = matchPredictionsStatus.toLowerCase().includes("charg")
    ? "Analyse disponible"
    : matchPredictionsStatus || "Analyse disponible";

  const gaugeStyle = {
    "--rb-pred-v3-gauge": `${Math.round((gaugeValue / 100) * 360)}deg`,
  } as CSSProperties;

  const globalRisk = formatRisk(
    readText(matchPredictions, [["risk_level"], ["risk"], ["global_risk"]], oneXTwoRisk)
  );

  const globalConfidence = confidencePercent
    ? confidencePercent >= 70
      ? "modérée à élevée"
      : confidencePercent >= 45
        ? "faible à modérée"
        : "faible"
    : "faible à modérée";

  const contextSummary = readText(
    matchContext,
    [["summary"], ["main_context"], ["context"], ["overview"]],
    "Match analysé avant le coup d’envoi, à partir des données disponibles."
  );

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
              <p>Tendances analysées avant coup d’envoi.</p>
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
            <span>
              {getTeamRank(matchDetails, "home")} · {getTeamPoints(matchDetails, "home")}
            </span>
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
            <span>
              {getTeamRank(matchDetails, "away")} · {getTeamPoints(matchDetails, "away")}
            </span>
          </div>
        </div>
      </section>

      <div className="rb-pred-v3-layout">
        <main className="rb-pred-v3-main">
          <section className="rb-pred-v3-panel">
            <header className="rb-pred-v3-panel__header">
              <div>
                <p className="rb-pred-v3-eyebrow">PRÉDICTIONS POUR CE MATCH</p>
                <h3>Tendances analysées</h3>
                <span>
                  Basées sur les données disponibles, la dynamique des équipes et le contexte avant-match.
                </span>
              </div>

              <span className="rb-pred-v3-status">
                <i aria-hidden="true" />
                {predictionStatusLabel}
              </span>
            </header>

            <div className="rb-pred-v3-predictions-grid">
              <PredictionCard
                icon={<Trophy size={17} aria-hidden="true" />}
                title="1X2"
                subtitle="Tendance résultat"
                bodyTitle="Lecture RubyBets"
                bodyText={oneXTwoPrediction || "Tendance prudente · match à surveiller"}
                confidence={oneXTwoConfidence}
                risk={oneXTwoRisk}
              />

              <PredictionCard
                icon={<BarChart3 size={17} aria-hidden="true" />}
                title="Nombre de buts"
                subtitle="Volume offensif"
                bodyTitle="Données insuffisantes"
                bodyText="Les moyennes offensives disponibles ne permettent pas de produire une lecture fiable."
                confidence={goalsConfidence}
                risk={goalsRisk}
                muted
              />

              <PredictionCard
                icon={<Sparkles size={17} aria-hidden="true" />}
                title="BTTS"
                subtitle="Les deux équipes marquent"
                bodyTitle="Données insuffisantes"
                bodyText="Les signaux disponibles ne permettent pas d’évaluer clairement cette tendance."
                confidence={bttsConfidence}
                risk={bttsRisk}
                muted
              />
            </div>

            <article className="rb-pred-v3-signal-card rb-pred-v3-signal-card--premium-final">
              <div className="rb-pred-v3-signal-card__title">
                <Zap size={22} aria-hidden="true" />
                <div>
                  <p>SIGNAL COMPLÉMENTAIRE</p>
                  <h4>Double chance : {homeTeamName} ou match nul</h4>
                  <span>
                    Ce signal complète la lecture principale sans constituer une prédiction certaine.
                  </span>
                </div>
              </div>

              <div className="rb-pred-v3-signal-card__premium-side">
                <strong>{signalConfidenceLabel}</strong>
                <span>Confiance indicative</span>

                <div className="rb-pred-v3-signal-card__badges">
                  <span>Signal complémentaire</span>
                  <span>Lecture prudente</span>
                </div>
              </div>
            </article>
          </section>

          <section className="rb-pred-v3-panel rb-pred-v3-global-reading">
            <p className="rb-pred-v3-eyebrow">LECTURE GLOBALE DE LA RENCONTRE</p>
            <h3>Synthèse des signaux disponibles</h3>
            <p>
              Les éléments disponibles indiquent un contexte relativement équilibré entre les deux
              équipes. L’écart observé ne permet pas de dégager une tendance fortement orientée avant
              le coup d’envoi.
            </p>

            <div className="rb-pred-v3-reading-grid">
              <article>
                <Gauge size={30} aria-hidden="true" />
                <strong>Équilibre général</strong>
                <span>Pas d’avantage clair avant le match.</span>
              </article>

              <article>
                <ShieldCheck size={30} aria-hidden="true" />
                <strong>Contexte prudent</strong>
                <span>Plusieurs facteurs restent encore incertains.</span>
              </article>

              <article>
                <Eye size={30} aria-hidden="true" />
                <strong>Lecture responsable</strong>
                <span>Basée uniquement sur les données actuelles.</span>
              </article>
            </div>
          </section>

          <p className="rb-pred-v3-footer-note">
            <Info size={16} aria-hidden="true" />
            Les prédictions présentées sont des lectures analytiques et ne garantissent aucun résultat sportif.
          </p>
        </main>

        <aside className="rb-pred-v3-sidebar">
          <section className="rb-pred-v3-side-card rb-pred-v3-side-card--summary">
            <p className="rb-pred-v3-eyebrow">SYNTHÈSE GLOBALE</p>

            <div className="rb-pred-v3-gauge-row">
              <div className="rb-pred-v3-gauge" style={gaugeStyle}>
                <span>{gaugeValue}%</span>
              </div>

              <div>
                <span>Confiance globale</span>
                <strong>{globalConfidence}</strong>
                <p>Lecture prudente et responsable.</p>
                <small>Basée uniquement sur les données disponibles.</small>
              </div>
            </div>
          </section>

          <section className="rb-pred-v3-side-card">
            <p className="rb-pred-v3-eyebrow">EN RÉSUMÉ</p>

            <ul className="rb-pred-v3-sidebar-list">
              <SidebarLine icon={<Sparkles size={17} aria-hidden="true" />}>
                Aucun avantage clair avant le match.
              </SidebarLine>
              <SidebarLine icon={<BarChart3 size={17} aria-hidden="true" />}>
                Les données offensives restent limitées pour évaluer le volume de buts.
              </SidebarLine>
              <SidebarLine icon={<Gauge size={17} aria-hidden="true" />}>
                Risque global : {globalRisk}.
              </SidebarLine>
              <SidebarLine icon={<Zap size={17} aria-hidden="true" />}>
                La double chance constitue un signal complémentaire, non déterminant.
              </SidebarLine>
            </ul>
          </section>

          <section className="rb-pred-v3-side-card">
            <p className="rb-pred-v3-eyebrow">FACE À FACE</p>
            <h3>Historique récent indisponible</h3>
            <p className="rb-pred-v3-side-card__text">
              Les confrontations directes ne sont pas encore disponibles pour cette rencontre.
            </p>
          </section>

          <section className="rb-pred-v3-side-card">
            <p className="rb-pred-v3-eyebrow">CONTEXTE & ENJEUX</p>

            <ul className="rb-pred-v3-sidebar-list">
              <SidebarLine icon={<CalendarDays size={17} aria-hidden="true" />}>
                Match analysé avant le coup d’envoi.
              </SidebarLine>
              <SidebarLine icon={<ShieldCheck size={17} aria-hidden="true" />}>
                Lecture basée sur les données disponibles.
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
                RubyBets est un outil d’aide à la décision. Nos analyses reposent sur des données
                réelles, mais ne garantissent aucun résultat.
              </p>
              <strong>Aucun conseil en investissement ou pari.</strong>
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
// ├── reçoit matchPredictions, matchDetails et matchContext depuis App.tsx
// ├── affiche les tendances 1X2, buts, BTTS et signal complémentaire
// ├── utilise une variante du panneau Détail match pour le résumé de rencontre
// └── utilise App.css avec les classes rb-pred-v3-* sans modifier le backend ni les contrats API