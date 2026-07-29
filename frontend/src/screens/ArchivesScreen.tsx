// Ce fichier construit l’écran Historique des analyses à partir des archives réelles de RubyBets.
// Il actualise les résultats connus, applique les filtres utilisateur et affiche un détail lisible sans jargon technique.

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  Archive,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  ShieldAlert,
  SlidersHorizontal,
  Hourglass,
  Info,
  RefreshCcw,
  Search,
  ShieldCheck,
  Target,
  TrendingUp,
  Trophy,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type {
  ArchivedPrediction,
  ArchivedPredictionsQuery,
  ArchivedPredictionsSummary,
  ArchivedPredictionVerdict,
} from "../models/rubybets";
import {
  getArchivedPredictions,
  reconcileArchivedPredictions,
} from "../services/api";
import "../styles/ArchivesScreen.css";

type HistoryKpiTone = "teal" | "green" | "blue" | "amber";

type HistoryKpi = {
  label: string;
  value: string;
  tone: HistoryKpiTone;
  icon: LucideIcon;
};

type MarketFilter =
  | "all"
  | "1X2"
  | "DOUBLE_CHANCE"
  | "OVER_1_5"
  | "OVER_2_5"
  | "BTTS";

type VerdictFilter =
  | "all"
  | "correct"
  | "incorrect"
  | "pending"
  | "not_verifiable";

type CompetitionFilter = "all" | string;

type SelectOption<T extends string> = {
  value: T;
  label: string;
};

const PAGE_LIMIT = 10;
const SEARCH_DELAY_MS = 350;
const AUTO_REFRESH_COOLDOWN_MS = 120_000;

let lastAutomaticRefreshAt = 0;

const marketFilterOptions: SelectOption<MarketFilter>[] = [
  { value: "all", label: "Tous" },
  { value: "1X2", label: "Résultat du match" },
  { value: "DOUBLE_CHANCE", label: "Deux issues possibles" },
  { value: "OVER_1_5", label: "Plus de 1,5 but" },
  { value: "OVER_2_5", label: "Plus de 2,5 buts" },
  { value: "BTTS", label: "Les deux équipes marquent" },
];

const verdictFilterOptions: SelectOption<VerdictFilter>[] = [
  { value: "all", label: "Tous" },
  { value: "correct", label: "Réussi" },
  { value: "incorrect", label: "Non réussi" },
  { value: "pending", label: "En attente" },
  { value: "not_verifiable", label: "Non vérifiable" },
];

// Cette fonction formate une date API en date française lisible.
function formatHistoryDate(value: string | null, withTime = false): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

// Cette fonction transforme une valeur technique en choix compréhensible par l’utilisateur.
function formatHistoryChoice(archive: ArchivedPrediction): string {
  const marketType = String(archive.market_type ?? "").toUpperCase();
  const predictedValue = String(archive.predicted_value ?? "").toUpperCase();

  if (marketType === "BTTS") {
    return ["YES", "TRUE", "1", "BTTS_YES"].includes(predictedValue)
      ? "Les deux équipes marquent"
      : "Au moins une équipe ne marque pas";
  }

  if (marketType === "OVER_1_5") {
    return predictedValue.includes("UNDER")
      ? "Moins de 1,5 but"
      : "Plus de 1,5 but";
  }

  if (marketType === "OVER_2_5" || marketType === "GOALS") {
    return predictedValue.includes("UNDER")
      ? "Moins de 2,5 buts"
      : "Plus de 2,5 buts";
  }

  const labels: Record<string, string> = {
    "1": "Victoire à domicile",
    HOME: "Victoire à domicile",
    HOME_WIN: "Victoire à domicile",
    TEAM_A_WIN: "Victoire à domicile",
    "2": "Victoire à l’extérieur",
    AWAY: "Victoire à l’extérieur",
    AWAY_WIN: "Victoire à l’extérieur",
    TEAM_B_WIN: "Victoire à l’extérieur",
    X: "Match nul",
    DRAW: "Match nul",
    "1X": "Domicile ou nul",
    HOME_OR_DRAW: "Domicile ou nul",
    TEAM_A_OR_DRAW: "Domicile ou nul",
    X2: "Extérieur ou nul",
    AWAY_OR_DRAW: "Extérieur ou nul",
    TEAM_B_OR_DRAW: "Extérieur ou nul",
    "12": "Une équipe gagne",
    HOME_OR_AWAY: "Une équipe gagne",
    NO_DRAW: "Une équipe gagne",
  };

  return labels[predictedValue] ?? archive.predicted_value ?? "Choix indisponible";
}

// Cette fonction traduit le statut d’une archive en libellé utilisateur.
function formatHistoryStatus(verdict: ArchivedPredictionVerdict | null): string {
  const labels: Record<string, string> = {
    correct: "Réussi",
    incorrect: "Non réussi",
    pending: "En attente",
    not_verifiable: "Non vérifiable",
  };

  return labels[String(verdict ?? "")] ?? "En attente";
}

// Cette fonction retourne la classe visuelle correspondant au statut affiché.
function getHistoryStatusTone(verdict: ArchivedPredictionVerdict | null): string {
  const normalizedVerdict = String(verdict ?? "pending");

  if (normalizedVerdict === "correct") {
    return "success";
  }

  if (normalizedVerdict === "incorrect") {
    return "failure";
  }

  if (normalizedVerdict === "not_verifiable") {
    return "neutral";
  }

  return "pending";
}

// Cette fonction affiche le score final uniquement lorsqu’il est connu.
function formatFinalScore(archive: ArchivedPrediction): string {
  if (archive.final_home_score === null || archive.final_away_score === null) {
    return "—";
  }

  return `${archive.final_home_score} – ${archive.final_away_score}`;
}

// Cette fonction crée une phrase simple sur la dernière mise à jour de l’analyse.
function formatUpdateMessage(archive: ArchivedPrediction): string {
  if (archive.checked_at) {
    return `Résultat vérifié le ${formatHistoryDate(archive.checked_at, true)}.`;
  }

  if (archive.verdict === "not_verifiable") {
    return "Cette rencontre ne peut pas être comparée à un résultat final exploitable.";
  }

  return "Résultat réel encore indisponible.";
}

// Cette fonction prépare un résumé par défaut lorsque le backend ne fournit pas encore les indicateurs globaux.
function buildFallbackSummary(
  archives: ArchivedPrediction[],
  totalCount: number
): ArchivedPredictionsSummary {
  const successful = archives.filter((archive) => archive.verdict === "correct").length;
  const unsuccessful = archives.filter((archive) => archive.verdict === "incorrect").length;
  const evaluated = successful + unsuccessful;
  const pending = archives.filter((archive) => archive.verdict === "pending").length;
  const notVerifiable = archives.filter(
    (archive) => archive.verdict === "not_verifiable"
  ).length;

  return {
    total: totalCount,
    evaluated,
    successful,
    unsuccessful,
    pending,
    not_verifiable: notVerifiable,
    success_rate:
      evaluated > 0 ? Math.round((successful / evaluated) * 1000) / 10 : null,
  };
}

// Ce composant affiche un logo d’équipe avec un fallback lisible lorsque l’image est absente.
function HistoryTeamLogo({
  name,
  logoUrl,
}: {
  name: string | null;
  logoUrl: string | null;
}) {
  const [hasImageError, setHasImageError] = useState(false);
  const fallback = (name ?? "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

  return (
    <span className="rb-history-team-logo" aria-hidden="true">
      {!hasImageError && logoUrl ? (
        <img
          src={logoUrl}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setHasImageError(true)}
        />
      ) : (
        <span>{fallback || "?"}</span>
      )}
    </span>
  );
}

// Ce composant affiche le badge coloré du résultat de l’analyse.
function HistoryStatusBadge({ verdict }: { verdict: ArchivedPredictionVerdict | null }) {
  const tone = getHistoryStatusTone(verdict);
  const Icon =
    tone === "success"
      ? CheckCircle2
      : tone === "failure"
        ? ShieldAlert
        : tone === "neutral"
          ? Info
          : Clock3;

  return (
    <span className={`rb-history-status rb-history-status--${tone}`}>
      <Icon size={14} strokeWidth={2.2} aria-hidden="true" />
      {formatHistoryStatus(verdict)}
    </span>
  );
}

// Ce composant affiche une carte indicateur avec un halo adapté à son rôle.
function HistoryKpiCard({ item }: { item: HistoryKpi }) {
  const Icon = item.icon;

  return (
    <div className={`rb-history-kpi rb-history-kpi--${item.tone}`}>
      <span className="rb-history-kpi__icon" aria-hidden="true">
        <Icon size={30} strokeWidth={1.8} />
      </span>
      <span className="rb-history-kpi__copy">
        <span>{item.label}</span>
        <strong>{item.value}</strong>
      </span>
    </div>
  );
}

// Ce composant affiche un filtre natif accessible avec le style premium de l’écran.
function HistorySelect<T extends string>({
  label,
  icon: Icon,
  value,
  options,
  onChange,
}: {
  label: string;
  icon: LucideIcon;
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <label className="rb-history-control">
      <span className="rb-history-control__label">
        <Icon size={17} strokeWidth={1.9} aria-hidden="true" />
        {label}
      </span>
      <span className="rb-history-control__field">
        <select
          value={value}
          aria-label={label}
          onChange={(event) => onChange(event.target.value as T)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronRight
          className="rb-history-control__chevron"
          size={16}
          strokeWidth={2}
          aria-hidden="true"
        />
      </span>
    </label>
  );
}

// Ce composant dessine le visuel lumineux du hero sans dépendance ni image externe.
function HistoryHeroVisual() {
  return (
    <div className="rb-history-hero-visual" aria-hidden="true">
      <span className="rb-history-hero-visual__grid" />
      <span className="rb-history-orbit rb-history-orbit--one" />
      <span className="rb-history-orbit rb-history-orbit--two" />
      <span className="rb-history-orbit rb-history-orbit--three" />
      <span className="rb-history-timeline">
        <i />
        <i />
        <i />
        <i />
      </span>

      <span className="rb-history-floating-card rb-history-floating-card--left">
        <FileText size={34} strokeWidth={1.55} />
        <i />
        <i />
        <i />
      </span>

      <span className="rb-history-floating-card rb-history-floating-card--right">
        <TrendingUp size={37} strokeWidth={1.55} />
        <i />
        <i />
      </span>

      <span className="rb-history-clock">
        <Clock3 size={62} strokeWidth={1.5} />
      </span>
      <span className="rb-history-clock-platform" />
      <span className="rb-history-particle rb-history-particle--one" />
      <span className="rb-history-particle rb-history-particle--two" />
      <span className="rb-history-particle rb-history-particle--three" />
    </div>
  );
}

// Ce composant affiche une ligne de l’historique et permet d’ouvrir son détail.
function HistoryRow({
  archive,
  selected,
  index,
  onSelect,
}: {
  archive: ArchivedPrediction;
  selected: boolean;
  index: number;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="row"
      className={
        selected
          ? "rb-history-row rb-history-row--selected"
          : "rb-history-row"
      }
      style={{ "--rb-history-row-index": index } as CSSProperties}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="rb-history-row__date" role="cell">
        {formatHistoryDate(archive.prediction_date ?? archive.match_date)}
      </span>

      <span className="rb-history-row__match" role="cell">
        <span className="rb-history-row__teams">
          <HistoryTeamLogo
            name={archive.home_team_name}
            logoUrl={archive.home_team_logo_url}
          />
          <HistoryTeamLogo
            name={archive.away_team_name}
            logoUrl={archive.away_team_logo_url}
          />
        </span>
        <strong>
          <span>{archive.home_team_name ?? "Équipe domicile"}</span>
          <em>vs</em>
          <span>{archive.away_team_name ?? "Équipe extérieure"}</span>
        </strong>
      </span>

      <span className="rb-history-row__competition" role="cell">
        {archive.competition_name ?? "Compétition non renseignée"}
      </span>

      <span className="rb-history-row__choice" role="cell">
        {formatHistoryChoice(archive)}
      </span>

      <span className="rb-history-row__status" role="cell">
        <HistoryStatusBadge verdict={archive.verdict} />
      </span>
    </button>
  );
}

// Ce composant affiche la fiche claire de l’analyse sélectionnée.
function HistoryDetailPanel({ archive }: { archive: ArchivedPrediction | null }) {
  if (!archive) {
    return (
      <aside className="rb-history-detail" aria-label="Détail de l’analyse">
        <div className="rb-history-detail__title">
          <FileText size={20} strokeWidth={1.8} aria-hidden="true" />
          <h2>Détail de l’analyse</h2>
        </div>
        <div className="rb-history-detail__empty">
          <Archive size={28} strokeWidth={1.7} aria-hidden="true" />
          <strong>Aucune analyse sélectionnée</strong>
          <p>Choisissez une ligne pour consulter son historique.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="rb-history-detail" aria-label="Détail de l’analyse sélectionnée">
      <div className="rb-history-detail__title">
        <FileText size={20} strokeWidth={1.8} aria-hidden="true" />
        <h2>Détail de l’analyse</h2>
      </div>

      <div className="rb-history-detail__versus">
        <span>
          <small>{archive.home_team_name ?? "Équipe domicile"}</small>
          <HistoryTeamLogo
            name={archive.home_team_name}
            logoUrl={archive.home_team_logo_url}
          />
        </span>
        <strong>VS</strong>
        <span>
          <HistoryTeamLogo
            name={archive.away_team_name}
            logoUrl={archive.away_team_logo_url}
          />
          <small>{archive.away_team_name ?? "Équipe extérieure"}</small>
        </span>
      </div>

      <dl className="rb-history-detail__list">
        <div>
          <dt>
            <Trophy size={15} aria-hidden="true" />
            Match
          </dt>
          <dd>
            {archive.home_team_name ?? "Équipe domicile"} vs {archive.away_team_name ?? "Équipe extérieure"}
          </dd>
        </div>
        <div>
          <dt>
            <CalendarDays size={15} aria-hidden="true" />
            Date de l’analyse
          </dt>
          <dd>{formatHistoryDate(archive.prediction_date, true)}</dd>
        </div>
        <div>
          <dt>
            <Target size={15} aria-hidden="true" />
            Choix proposé
          </dt>
          <dd>{formatHistoryChoice(archive)}</dd>
        </div>
        <div>
          <dt>
            <BarChart3 size={15} aria-hidden="true" />
            Résultat final
          </dt>
          <dd>{formatFinalScore(archive)}</dd>
        </div>
        <div>
          <dt>
            <CheckCircle2 size={15} aria-hidden="true" />
            Statut
          </dt>
          <dd>
            <HistoryStatusBadge verdict={archive.verdict} />
          </dd>
        </div>
        <div className="rb-history-detail__long-row">
          <dt>
            <FileText size={15} aria-hidden="true" />
            Pourquoi ce choix ?
          </dt>
          <dd>
            {archive.justification ??
              "Cette analyse a été construite à partir des informations disponibles avant le match."}
          </dd>
        </div>
        <div className="rb-history-detail__long-row">
          <dt>
            <RefreshCcw size={15} aria-hidden="true" />
            Mise à jour
          </dt>
          <dd>{formatUpdateMessage(archive)}</dd>
        </div>
      </dl>

      <div className="rb-history-responsible-note">
        <ShieldCheck size={22} strokeWidth={1.8} aria-hidden="true" />
        <p>
          Les archives aident à relire les analyses passées. Elles ne garantissent jamais un résultat futur.
        </p>
      </div>
    </aside>
  );
}

// Ce composant rend l’écran complet Historique avec actualisation, filtres, liste et détail.
function ArchivesScreen() {
  const [competitionName, setCompetitionName] = useState<CompetitionFilter>("all");
  const [marketType, setMarketType] = useState<MarketFilter>("all");
  const [verdict, setVerdict] = useState<VerdictFilter>("all");
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [archives, setArchives] = useState<ArchivedPrediction[]>([]);
  const [summary, setSummary] = useState<ArchivedPredictionsSummary | null>(null);
  const [availableCompetitions, setAvailableCompetitions] = useState<string[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [selectedArchiveId, setSelectedArchiveId] = useState<number | null>(null);
  const initialRefreshStartedRef = useRef(false);

  const competitionFilterOptions = useMemo<SelectOption<CompetitionFilter>[]>(
    () => [
      { value: "all", label: "Toutes" },
      ...availableCompetitions.map((competition) => ({
        value: competition,
        label: competition,
      })),
    ],
    [availableCompetitions]
  );

  const selectedArchive = useMemo(
    () =>
      archives.find((archive) => archive.id === selectedArchiveId) ??
      archives[0] ??
      null,
    [archives, selectedArchiveId]
  );

  const effectiveSummary = useMemo(
    () => summary ?? buildFallbackSummary(archives, totalCount),
    [archives, summary, totalCount]
  );

  const kpis = useMemo<HistoryKpi[]>(
    () => [
      {
        label: "Analyses enregistrées",
        value: String(effectiveSummary.total),
        tone: "teal",
        icon: Archive,
      },
      {
        label: "Résultats confirmés",
        value: String(effectiveSummary.evaluated),
        tone: "green",
        icon: CheckCircle2,
      },
      {
        label: "Taux de réussite",
        value:
          effectiveSummary.success_rate === null
            ? "—"
            : `${Math.round(effectiveSummary.success_rate)}%`,
        tone: "blue",
        icon: Target,
      },
      {
        label: "En attente",
        value: String(effectiveSummary.pending),
        tone: "amber",
        icon: Hourglass,
      },
    ],
    [effectiveSummary]
  );

  const currentPage = Math.floor(offset / PAGE_LIMIT) + 1;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_LIMIT));
  const displayStart = totalCount === 0 ? 0 : offset + 1;
  const displayEnd = Math.min(offset + archives.length, totalCount);

  // Cette fonction replace la pagination sur la première page après un filtre.
  function resetPagination() {
    setOffset(0);
  }

  // Cette fonction relance la lecture des archives après une actualisation réussie ou partielle.
  async function refreshKnownResults(showFeedback = true) {
    setIsRefreshing(true);

    if (showFeedback) {
      setRefreshMessage(null);
    }

    try {
      const response = await reconcileArchivedPredictions(25);

      if (showFeedback) {
        setRefreshMessage(response.message ?? "Les résultats connus ont été actualisés.");
      }
    } catch {
      if (showFeedback) {
        setRefreshMessage("L’actualisation n’a pas pu être terminée pour le moment.");
      }
    } finally {
      setIsRefreshing(false);
      setReloadVersion((currentVersion) => currentVersion + 1);
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setOffset(0);
    }, SEARCH_DELAY_MS);

    return () => window.clearTimeout(timeoutId);
  }, [searchInput]);

  useEffect(() => {
    if (initialRefreshStartedRef.current) {
      return;
    }

    initialRefreshStartedRef.current = true;
    const now = Date.now();

    if (now - lastAutomaticRefreshAt < AUTO_REFRESH_COOLDOWN_MS) {
      return;
    }

    lastAutomaticRefreshAt = now;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshKnownResults(false);
  }, []);

  useEffect(() => {
    const abortController = new AbortController();
    const query: ArchivedPredictionsQuery = {
      market_type: marketType === "all" ? undefined : marketType,
      verdict: verdict === "all" ? undefined : verdict,
      competition_name: competitionName === "all" ? undefined : competitionName,
      search: debouncedSearch || undefined,
      limit: PAGE_LIMIT,
      offset,
    };

    async function loadArchives() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await getArchivedPredictions(
          query,
          abortController.signal
        );

        setArchives(response.items);
        setSummary(response.summary ?? null);
        setAvailableCompetitions(response.available_competitions ?? []);
        setTotalCount(response.count);

        if (response.status !== "available") {
          setError(response.message ?? "L’historique est momentanément indisponible.");
        }
      } catch (loadError) {
        if (abortController.signal.aborted) {
          return;
        }

        setArchives([]);
        setSummary(null);
        setTotalCount(0);
        setError(
          loadError instanceof Error
            ? loadError.message
            : "L’historique n’a pas pu être chargé."
        );
      } finally {
        if (!abortController.signal.aborted) {
          setIsLoading(false);
        }
      }
    }

    void loadArchives();

    return () => abortController.abort();
  }, [competitionName, debouncedSearch, marketType, offset, reloadVersion, verdict]);

  useEffect(() => {
    if (archives.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedArchiveId(null);
      return;
    }

    if (!archives.some((archive) => archive.id === selectedArchiveId)) {
      setSelectedArchiveId(archives[0].id);
    }
  }, [archives, selectedArchiveId]);

  return (
    <div className="rb-history-screen">
      <header className="rb-history-top">
        <div className="rb-history-hero">
          <div className="rb-history-hero__copy">
            <p className="rb-history-pill">
              <Archive size={15} strokeWidth={2} aria-hidden="true" />
              Suivi & historique
            </p>
            <h1>Historique des analyses</h1>
            <p>
              Retrouvez les analyses passées, comparez-les aux résultats réels et suivez leur évolution dans le temps.
            </p>
          </div>
          <HistoryHeroVisual />
        </div>

        <aside className="rb-history-purpose">
          <div className="rb-history-purpose__title">
            <Info size={19} strokeWidth={2} aria-hidden="true" />
            <h2>À quoi sert cet historique&nbsp;?</h2>
          </div>
          <ul>
            <li>
              <Clock3 size={20} strokeWidth={1.9} aria-hidden="true" />
              <span>Suivre les analyses déjà proposées</span>
            </li>
            <li>
              <CheckCircle2 size={20} strokeWidth={1.9} aria-hidden="true" />
              <span>Voir si le résultat réel a confirmé la lecture</span>
            </li>
            <li>
              <BarChart3 size={20} strokeWidth={1.9} aria-hidden="true" />
              <span>Mieux comprendre la régularité des choix dans le temps</span>
            </li>
          </ul>
          <div className="rb-history-purpose__note">
            <ShieldCheck size={20} strokeWidth={1.8} aria-hidden="true" />
            <p>
              Les archives aident à relire les analyses passées. Elles ne garantissent jamais un résultat futur.
            </p>
          </div>
        </aside>
      </header>

      <div className="rb-history-kpis" aria-label="Résumé de l’historique">
        {kpis.map((item) => (
          <HistoryKpiCard key={item.label} item={item} />
        ))}
      </div>

      <div className="rb-history-toolbar" aria-label="Filtres de l’historique">
        <HistorySelect
          label="Compétition"
          icon={Trophy}
          value={competitionName}
          options={competitionFilterOptions}
          onChange={(nextValue) => {
            setCompetitionName(nextValue);
            resetPagination();
          }}
        />
        <HistorySelect
          label="Type de choix"
          icon={Target}
          value={marketType}
          options={marketFilterOptions}
          onChange={(nextValue) => {
            setMarketType(nextValue);
            resetPagination();
          }}
        />
        <HistorySelect
          label="Statut"
          icon={SlidersHorizontal}
          value={verdict}
          options={verdictFilterOptions}
          onChange={(nextValue) => {
            setVerdict(nextValue);
            resetPagination();
          }}
        />

        <label className="rb-history-control rb-history-control--search">
          <span className="rb-history-control__label">
            <Search size={17} strokeWidth={1.9} aria-hidden="true" />
            Recherche équipe
          </span>
          <span className="rb-history-control__field">
            <input
              type="search"
              value={searchInput}
              placeholder="Rechercher une équipe..."
              aria-label="Rechercher une équipe"
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </span>
        </label>

        <div className="rb-history-refresh-wrap">
          <button
            type="button"
            className="rb-history-refresh"
            disabled={isRefreshing}
            onClick={() => void refreshKnownResults(true)}
          >
            <RefreshCcw
              className={isRefreshing ? "is-spinning" : ""}
              size={25}
              strokeWidth={1.9}
              aria-hidden="true"
            />
            <span>
              <strong>{isRefreshing ? "Actualisation..." : "Actualiser"}</strong>
              <small>Met à jour les résultats connus</small>
            </span>
          </button>
          {refreshMessage ? (
            <p className="rb-history-refresh-message" role="status">
              {refreshMessage}
            </p>
          ) : null}
        </div>
      </div>

      <div className="rb-history-content">
        <div className="rb-history-list-card" role="table" aria-label="Historique des analyses">
          <div className="rb-history-list-card__heading">
            <p className="rb-history-section-pill">Vos analyses passées</p>
            <h2>Historique des analyses</h2>
          </div>

          <div className="rb-history-table-head" role="row">
            <span role="columnheader">Date</span>
            <span role="columnheader">Match</span>
            <span role="columnheader">Compétition</span>
            <span role="columnheader">Choix proposé</span>
            <span role="columnheader">Statut</span>
          </div>

          <div className="rb-history-rows" role="rowgroup">
            {isLoading ? (
              <div className="rb-history-state">
                <RefreshCcw className="is-spinning" size={24} aria-hidden="true" />
                <strong>Chargement de l’historique...</strong>
              </div>
            ) : error ? (
              <div className="rb-history-state rb-history-state--error">
                <Info size={24} aria-hidden="true" />
                <strong>{error}</strong>
              </div>
            ) : archives.length === 0 ? (
              <div className="rb-history-state">
                <Archive size={28} aria-hidden="true" />
                <strong>Aucune analyse ne correspond à ces filtres.</strong>
                <span>Modifiez les critères pour élargir la recherche.</span>
              </div>
            ) : (
              archives.map((archive, index) => (
                <HistoryRow
                  key={archive.id}
                  archive={archive}
                  index={index}
                  selected={archive.id === selectedArchive?.id}
                  onSelect={() => setSelectedArchiveId(archive.id)}
                />
              ))
            )}
          </div>

          <footer className="rb-history-pagination" aria-label="Pagination de l’historique">
            <span>
              {displayStart}–{displayEnd} sur {totalCount}
            </span>
            <div>
              <button
                type="button"
                aria-label="Page précédente"
                disabled={currentPage <= 1 || isLoading}
                onClick={() =>
                  setOffset((currentOffset) =>
                    Math.max(0, currentOffset - PAGE_LIMIT)
                  )
                }
              >
                <ChevronLeft size={18} aria-hidden="true" />
              </button>
              <button type="button" className="is-current" aria-current="page">
                {currentPage}
              </button>
              <span>/</span>
              <button type="button" disabled>
                {totalPages}
              </button>
              <button
                type="button"
                aria-label="Page suivante"
                disabled={currentPage >= totalPages || isLoading}
                onClick={() =>
                  setOffset((currentOffset) => currentOffset + PAGE_LIMIT)
                }
              >
                <ChevronRight size={18} aria-hidden="true" />
              </button>
            </div>
          </footer>
        </div>

        <HistoryDetailPanel archive={selectedArchive} />
      </div>
    </div>
  );
}

export default ArchivesScreen;

// Schéma de communication du fichier :
// ArchivesScreen.tsx
// ├── est affiché par App.tsx lorsque l’utilisateur ouvre Archives
// ├── appelle getArchivedPredictions() et reconcileArchivedPredictions() dans services/api.ts
// ├── consomme les contrats Archives définis dans models/rubybets.ts
// └── utilise styles/ArchivesScreen.css pour le rendu Obsidian Teal, les animations et le responsive
