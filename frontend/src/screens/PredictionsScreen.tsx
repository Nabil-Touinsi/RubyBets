// Rôle du fichier :
// Cet écran présente la décision officielle RubyBets V19 et son explicabilité publique sans recalculer de score côté frontend.

import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  CircleHelp,
  Database,
  FileSearch,
  Info,
  Layers3,
  Scale,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type {
  MatchContextResponse,
  MatchDetailsResponse,
  V19ProductPredictionResponse,
} from "../models/rubybets";
import type { AppScreen } from "../types/navigation";

type PredictionsScreenProps = {
  v19ProductPrediction: V19ProductPredictionResponse | null;
  matchDetails: MatchDetailsResponse | null;
  matchContext: MatchContextResponse | null;
  v19ProductStatus: string;
  onNavigate: (screen: AppScreen) => void;
};

type TeamVisualProps = {
  crest: string | null | undefined;
  name: string;
};

type ExplanationListProps = {
  icon: ReactNode;
  eyebrow: string;
  title: string;
  items: string[];
  emptyMessage: string;
  tone?: "positive" | "caution" | "neutral";
};

// Cette fonction formate la date du match sans modifier la donnée source.
function formatMatchDate(utcDate: string | undefined): string {
  if (!utcDate) {
    return "Date à confirmer";
  }

  const parsedDate = new Date(utcDate);

  if (Number.isNaN(parsedDate.getTime())) {
    return utcDate;
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsedDate);
}

// Cette fonction formate l’heure du match sans produire de valeur artificielle.
function formatMatchTime(utcDate: string | undefined): string {
  if (!utcDate) {
    return "Heure à confirmer";
  }

  const parsedDate = new Date(utcDate);

  if (Number.isNaN(parsedDate.getTime())) {
    return "Heure à confirmer";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsedDate);
}

// Cette fonction construit un libellé lisible pour la phase ou la journée du match.
function formatMatchRound(
  matchday: number | undefined,
  stage: string | undefined,
): string {
  if (stage?.trim()) {
    return stage.replaceAll("_", " ").toLocaleLowerCase("fr-FR");
  }

  if (typeof matchday === "number") {
    return `Journée ${matchday}`;
  }

  return "Phase à confirmer";
}

// Cette fonction affiche le blason d’une équipe ou un fallback textuel.
function TeamVisual({ crest, name }: TeamVisualProps) {
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join("");

  if (crest) {
    return (
      <img
        src={crest}
        alt=""
        className="rb-v19-pred-team__crest"
        loading="lazy"
      />
    );
  }

  return (
    <span className="rb-v19-pred-team__fallback" aria-hidden="true">
      {initials || "RB"}
    </span>
  );
}

// Cette fonction affiche une liste publique d’explications sans interpréter les codes techniques.
function ExplanationList({
  icon,
  eyebrow,
  title,
  items,
  emptyMessage,
  tone = "neutral",
}: ExplanationListProps) {
  return (
    <article className={`rb-v19-pred-list-card rb-v19-pred-list-card--${tone}`}>
      <header className="rb-v19-pred-list-card__header">
        <span className="rb-v19-pred-icon-chip">{icon}</span>
        <div>
          <p className="rb-v19-pred-eyebrow">{eyebrow}</p>
          <h3>{title}</h3>
        </div>
      </header>

      {items.length > 0 ? (
        <ul className="rb-v19-pred-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="rb-v19-pred-empty-copy">{emptyMessage}</p>
      )}
    </article>
  );
}

// Cette fonction affiche l’état de chargement ou d’indisponibilité du moteur V19.
function PredictionStateCard({
  title,
  message,
  loading,
}: {
  title: string;
  message: string;
  loading: boolean;
}) {
  return (
    <section
      className={`rb-v19-pred-state ${loading ? "rb-v19-pred-state--loading" : ""}`}
      aria-live="polite"
    >
      <span className="rb-v19-pred-icon-chip">
        {loading ? (
          <Sparkles size={20} aria-hidden="true" />
        ) : (
          <CircleHelp size={20} aria-hidden="true" />
        )}
      </span>
      <div>
        <p className="rb-v19-pred-eyebrow">DÉCISION PRODUIT V19</p>
        <h2>{title}</h2>
        <p>{message}</p>
      </div>
    </section>
  );
}

// Ce composant affiche l’écran Prédictions à partir du contrat public V19 chargé par App.tsx.
function PredictionsScreen({
  v19ProductPrediction,
  matchDetails,
  matchContext,
  v19ProductStatus,
  onNavigate,
}: PredictionsScreenProps) {
  const match = matchDetails?.match ?? matchContext?.match;
  const homeTeamName = match?.home_team.name || "Équipe domicile";
  const awayTeamName = match?.away_team.name || "Équipe extérieure";
  const competitionName = match?.competition.name || "Compétition";
  const contextTitle =
    matchContext?.context.summary.title ||
    "Contexte avant-match disponible dans la fiche détaillée.";
  const isLoading = v19ProductStatus.startsWith("Chargement");

  return (
    <div className="rb-v19-pred-screen">
      <header className="rb-v19-pred-topbar">
        <button
          type="button"
          className="rb-v19-pred-back"
          onClick={() => onNavigate("matches")}
        >
          <ArrowLeft size={17} aria-hidden="true" />
          Retour aux matchs
        </button>

        <div>
          <p className="rb-v19-pred-eyebrow">DECISION INTELLIGENCE ENGINE</p>
          <h1>Prédictions</h1>
          <p>
            Une seule décision officielle V19, expliquée sans score brut ni
            pourcentage de réussite.
          </p>
        </div>

        <button
          type="button"
          className="rb-v19-pred-secondary-action"
          onClick={() => onNavigate("analysis")}
        >
          <FileSearch size={17} aria-hidden="true" />
          Voir l’analyse
        </button>
      </header>

      <section className="rb-v19-pred-match-hero" aria-label="Match sélectionné">
        <div className="rb-v19-pred-team">
          <TeamVisual crest={match?.home_team.crest} name={homeTeamName} />
          <div>
            <span>Domicile</span>
            <strong>{homeTeamName}</strong>
          </div>
        </div>

        <div className="rb-v19-pred-match-meta">
          <span>{competitionName}</span>
          <strong>{formatMatchTime(match?.utc_date)}</strong>
          <p>{formatMatchDate(match?.utc_date)}</p>
          <small>{formatMatchRound(match?.matchday, match?.stage)}</small>
        </div>

        <div className="rb-v19-pred-team rb-v19-pred-team--away">
          <TeamVisual crest={match?.away_team.crest} name={awayTeamName} />
          <div>
            <span>Extérieur</span>
            <strong>{awayTeamName}</strong>
          </div>
        </div>
      </section>

      {!v19ProductPrediction ? (
        <PredictionStateCard
          loading={isLoading}
          title={isLoading ? "Décision en cours de préparation" : "Décision indisponible"}
          message={
            isLoading
              ? "RubyBets compare les signaux disponibles avant de produire une décision responsable."
              : v19ProductStatus
          }
        />
      ) : (
        <div className="rb-v19-pred-layout">
          <main className="rb-v19-pred-main">
            <section
              className={`rb-v19-pred-decision rb-v19-pred-decision--${v19ProductPrediction.status.toLowerCase()}`}
              aria-live="polite"
            >
              <div className="rb-v19-pred-decision__status">
                <span>
                  {v19ProductPrediction.status === "RECOMMEND" ? (
                    <CheckCircle2 size={17} aria-hidden="true" />
                  ) : (
                    <ShieldCheck size={17} aria-hidden="true" />
                  )}
                  {v19ProductPrediction.status === "RECOMMEND"
                    ? "RECOMMANDATION RETENUE"
                    : "ABSTENTION RESPONSABLE"}
                </span>
                <small>RubyBets V19</small>
              </div>

              <p className="rb-v19-pred-eyebrow">DÉCISION PRINCIPALE</p>
              <h2>{v19ProductPrediction.explanation.headline}</h2>
              <strong className="rb-v19-pred-decision__summary">
                {v19ProductPrediction.explanation.summary}
              </strong>

              {v19ProductPrediction.explanation.abstention_explanation && (
                <p className="rb-v19-pred-decision__abstention">
                  {v19ProductPrediction.explanation.abstention_explanation}
                </p>
              )}
            </section>

            <div className="rb-v19-pred-explanation-grid">
              <ExplanationList
                icon={<CheckCircle2 size={19} aria-hidden="true" />}
                eyebrow="FACTEURS FAVORABLES"
                title="Pourquoi ce signal ressort"
                items={v19ProductPrediction.explanation.supporting_factors}
                emptyMessage="Aucun facteur favorable supplémentaire n’a été transmis."
                tone="positive"
              />

              <ExplanationList
                icon={<AlertTriangle size={19} aria-hidden="true" />}
                eyebrow="FACTEURS DE PRUDENCE"
                title="Limites à conserver en tête"
                items={v19ProductPrediction.explanation.caution_factors}
                emptyMessage="Aucun facteur de prudence additionnel n’a été transmis."
                tone="caution"
              />
            </div>

            <ExplanationList
              icon={<Scale size={19} aria-hidden="true" />}
              eyebrow="ALTERNATIVES REJETÉES"
              title="Signaux examinés mais non retenus"
              items={v19ProductPrediction.explanation.rejected_alternatives}
              emptyMessage="Aucune alternative rejetée n’a été transmise."
            />

            <section className="rb-v19-pred-context-card">
              <span className="rb-v19-pred-icon-chip">
                <Info size={19} aria-hidden="true" />
              </span>
              <div>
                <p className="rb-v19-pred-eyebrow">CONTEXTE DU MATCH</p>
                <h3>Lecture factuelle associée</h3>
                <p>{contextTitle}</p>
              </div>
            </section>
          </main>

          <aside className="rb-v19-pred-sidebar">
            <section className="rb-v19-pred-info-card">
              <span className="rb-v19-pred-icon-chip">
                <Database size={19} aria-hidden="true" />
              </span>
              <div>
                <p className="rb-v19-pred-eyebrow">QUALITÉ DES DONNÉES</p>
                <h3>État des entrées</h3>
                <p>{v19ProductPrediction.explanation.data_quality_summary}</p>
              </div>
            </section>

            <section className="rb-v19-pred-info-card">
              <span className="rb-v19-pred-icon-chip">
                <ShieldCheck size={19} aria-hidden="true" />
              </span>
              <div>
                <p className="rb-v19-pred-eyebrow">CONFIANCE</p>
                <h3>Interprétation responsable</h3>
                <p>{v19ProductPrediction.explanation.confidence_explanation}</p>
              </div>
            </section>

            <section className="rb-v19-pred-info-card">
              <span className="rb-v19-pred-icon-chip">
                <CalendarDays size={19} aria-hidden="true" />
              </span>
              <div>
                <p className="rb-v19-pred-eyebrow">FRAÎCHEUR</p>
                <h3>Traçabilité temporelle</h3>
                <p>{v19ProductPrediction.explanation.source_freshness_summary}</p>
              </div>
            </section>

            <section className="rb-v19-pred-info-card rb-v19-pred-info-card--technical">
              <span className="rb-v19-pred-icon-chip">
                <Layers3 size={19} aria-hidden="true" />
              </span>
              <div>
                <p className="rb-v19-pred-eyebrow">VERSION TECHNIQUE</p>
                <h3>Moteur et contrat</h3>
                <dl className="rb-v19-pred-versions">
                  <div>
                    <dt>Moteur</dt>
                    <dd>{v19ProductPrediction.versions.engine}</dd>
                  </div>
                  <div>
                    <dt>Explication</dt>
                    <dd>{v19ProductPrediction.versions.explanation}</dd>
                  </div>
                </dl>
              </div>
            </section>

            <section className="rb-v19-pred-responsible">
              <ShieldCheck size={24} aria-hidden="true" />
              <div>
                <p className="rb-v19-pred-eyebrow">CADRE RESPONSABLE</p>
                <p>{v19ProductPrediction.explanation.responsible_note}</p>
              </div>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}

export default PredictionsScreen;

// Schéma de communication du fichier :
// App.tsx
//   -> fournit matchDetails, matchContext, v19ProductPrediction et v19ProductStatus
// PredictionsScreen.tsx
//   -> affiche uniquement le contrat public explanation de RubyBets V19
// App.css
//   <- fournit les styles rb-v19-pred-*
// Backend V19
//   <- aucune décision, probabilité ou règle sportive n’est recalculée dans cet écran
