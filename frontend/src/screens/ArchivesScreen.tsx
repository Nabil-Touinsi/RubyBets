// Ce fichier crée l’écran Archives RubyBets branché sur l’API réelle des prédictions archivées.
// Il affiche les archives, leurs filtres, leur score final, leur verdict et le détail de l’archive sélectionnée.

import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  CalendarCheck2,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  FileText,
  Hourglass,
  Info,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Target,
  TrendingUp,
  Trophy,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type {
  ArchivedPrediction,
  ArchivedPredictionVerdict,
  ArchivedPredictionsQuery,
} from "../models/rubybets";
import { getArchivedPredictions } from "../services/api";

type ArchiveKpi = {
  label: string;
  value: string;
  tone: "teal" | "blue" | "cyan" | "amber";
  icon: LucideIcon;
};

type ArchiveFilterOption<T extends string> = {
  value: T;
  label: string;
};

type MarketFilter = "all" | "1X2" | "DOUBLE_CHANCE" | "OVER_1_5" | "OVER_2_5" | "BTTS";
type VerdictFilter = "all" | "correct" | "incorrect" | "pending" | "not_verifiable";
type CompetitionFilter = "all" | string;

const PAGE_LIMIT = 10;

const marketFilterOptions: ArchiveFilterOption<MarketFilter>[] = [
  { value: "all", label: "Tous" },
  { value: "1X2", label: "1X2" },
  { value: "DOUBLE_CHANCE", label: "Double chance" },
  { value: "OVER_1_5", label: "Over 1.5" },
  { value: "OVER_2_5", label: "Over 2.5" },
  { value: "BTTS", label: "BTTS" },
];

const verdictFilterOptions: ArchiveFilterOption<VerdictFilter>[] = [
  { value: "all", label: "Tous" },
  { value: "correct", label: "Correcte" },
  { value: "incorrect", label: "Incorrecte" },
  { value: "pending", label: "En attente" },
  { value: "not_verifiable", label: "Non vérifiable" },
];

// Cette fonction formate une date API en date française lisible.
function formatArchiveDate(value: string | null, withTime = false): string {
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

// Cette fonction transforme un marché technique backend en libellé court pour l’interface.
function formatMarketType(marketType: string | null): string {
  const normalizedMarket = (marketType ?? "").toUpperCase();

  const labels: Record<string, string> = {
    "1X2": "1X2",
    DOUBLE_CHANCE: "Double chance",
    OVER_1_5: "Over 1.5",
    OVER_2_5: "Over 2.5",
    BTTS: "BTTS",
    GOALS: "Buts",
  };

  return labels[normalizedMarket] ?? marketType ?? "—";
}

// Cette fonction transforme une valeur de prédiction technique en libellé métier lisible.
function formatPredictionValue(predictedValue: string | null): string {
  const normalizedPrediction = (predictedValue ?? "").toUpperCase();

  const labels: Record<string, string> = {
    "1": "Victoire domicile",
    HOME: "Victoire domicile",
    HOME_WIN: "Victoire domicile",
    TEAM_A_WIN: "Victoire domicile",
    "2": "Victoire extérieure",
    AWAY: "Victoire extérieure",
    AWAY_WIN: "Victoire extérieure",
    TEAM_B_WIN: "Victoire extérieure",
    X: "Match nul",
    DRAW: "Match nul",
    YES: "Oui",
    TRUE: "Oui",
    NO: "Non",
    FALSE: "Non",
    OVER: "Over",
    UNDER: "Under",
    OVER_1_5: "Over 1.5",
    OVER_2_5: "Over 2.5",
    UNDER_1_5: "Under 1.5",
    UNDER_2_5: "Under 2.5",
    HOME_OR_DRAW: "Domicile ou nul",
    TEAM_A_OR_DRAW: "Domicile ou nul",
    AWAY_OR_DRAW: "Extérieur ou nul",
    TEAM_B_OR_DRAW: "Extérieur ou nul",
    HOME_OR_AWAY: "Pas de nul",
    NO_DRAW: "Pas de nul",
  };

  return labels[normalizedPrediction] ?? predictedValue ?? "—";
}

// Cette fonction transforme les niveaux techniques en libellés français.
function formatLevel(value: string | null): string {
  const normalizedValue = (value ?? "").toLowerCase();

  const labels: Record<string, string> = {
    high: "Élevée",
    medium: "Moyenne",
    low: "Faible",
  };

  return labels[normalizedValue] ?? value ?? "—";
}

// Cette fonction transforme les niveaux de risque techniques en libellés français.
function formatRiskLevel(value: string | null): string {
  const normalizedValue = (value ?? "").toLowerCase();

  const labels: Record<string, string> = {
    high: "Élevé",
    medium: "Moyen",
    low: "Faible",
  };

  return labels[normalizedValue] ?? value ?? "—";
}

// Cette fonction transforme un verdict technique en libellé français.
function formatVerdict(verdict: ArchivedPredictionVerdict | null): string {
  const labels: Record<string, string> = {
    correct: "Correcte",
    incorrect: "Incorrecte",
    pending: "En attente",
    not_verifiable: "Non vérifiable",
  };

  return labels[String(verdict ?? "")] ?? verdict ?? "—";
}

// Cette fonction affiche le score final uniquement quand il est disponible.
function formatFinalScore(archive: ArchivedPrediction): string {
  if (archive.final_home_score === null || archive.final_away_score === null) {
    return "—";
  }

  return `${archive.final_home_score} - ${archive.final_away_score}`;
}

// Cette fonction indique si un statut backend correspond à un match terminé.
function isFinishedStatus(matchStatus: string | null): boolean {
  return ["FINISHED", "FINISH", "FINISHED_AET", "FINISHED_AP", "COMPLETE", "COMPLETED", "FT", "AET", "PEN"].includes(
    String(matchStatus ?? "").toUpperCase()
  );
}

// Cette fonction construit une clé unique pour compter un match une seule fois dans les archives.
function getArchiveMatchKey(archive: ArchivedPrediction): string {
  return String(
    archive.rubybets_match_id ??
      archive.source_match_id ??
      `${archive.home_team_name}-${archive.away_team_name}-${archive.match_date}`
  );
}

// Ce composant affiche une carte KPI du haut de page avec son icône, sa valeur et sa couleur métier.
function ArchiveKpiCard({ item }: { item: ArchiveKpi }) {
  const Icon = item.icon;

  return (
    <article className={`rb-archive-kpi rb-archive-kpi--${item.tone}`}>
      <span className="rb-archive-kpi__icon" aria-hidden="true">
        <Icon size={30} strokeWidth={1.8} />
      </span>
      <span className="rb-archive-kpi__content">
        <span>{item.label}</span>
        <strong>{item.value}</strong>
      </span>
    </article>
  );
}

// Ce composant affiche un badge coloré selon le type de valeur : verdict, confiance ou risque.
function ArchiveBadge({ value, type }: { value: string; type: "verdict" | "confidence" | "risk" }) {
  const normalizedValue = value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

  return (
    <span className={`rb-archive-badge rb-archive-badge--${type}-${normalizedValue}`}>
      {value}
    </span>
  );
}

// Ce composant affiche un filtre compact qui cycle entre les valeurs au clic pour conserver le style de la maquette.
function ArchiveFilter<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: ArchiveFilterOption<T>[];
  onChange: (nextValue: T) => void;
}) {
  const selectedOption = options.find((option) => option.value === value) ?? options[0];

  function handleCycleFilter() {
    const currentIndex = options.findIndex((option) => option.value === value);
    const nextOption = options[(currentIndex + 1) % options.length];
    onChange(nextOption.value);
  }

  return (
    <label className="rb-archive-filter">
      <span>{label}</span>
      <button type="button" aria-label={`${label} : ${selectedOption.label}`} onClick={handleCycleFilter}>
        {selectedOption.label}
        <ChevronDown size={16} strokeWidth={2} aria-hidden="true" />
      </button>
    </label>
  );
}

// Ce composant affiche une ligne du tableau d’archives et permet de choisir l’archive affichée dans le détail.
function ArchiveTableRow({
  row,
  selected,
  onSelect,
}: {
  row: ArchivedPrediction;
  selected: boolean;
  onSelect: () => void;
}) {
  const homeCode = row.home_team_country_code ?? "";
  const awayCode = row.away_team_country_code ?? "";

  return (
    <tr
      className={selected ? "rb-archive-table__row rb-archive-table__row--selected" : "rb-archive-table__row"}
      onClick={onSelect}
    >
      <td>{formatArchiveDate(row.prediction_date ?? row.match_date)}</td>
      <td>
        <span className="rb-archive-match-cell">
          <span className="rb-archive-flags" aria-hidden="true">
            <span>{homeCode || "🏠"}</span>
            <span>{awayCode || "✈️"}</span>
          </span>
          <strong>
            {row.home_team_name ?? "Équipe domicile"} vs {row.away_team_name ?? "Équipe extérieure"}
          </strong>
        </span>
      </td>
      <td>{row.competition_name ?? "—"}</td>
      <td>{formatMarketType(row.market_type)}</td>
      <td>{formatPredictionValue(row.predicted_value)}</td>
      <td>{formatFinalScore(row)}</td>
      <td>
        <ArchiveBadge value={formatVerdict(row.verdict)} type="verdict" />
      </td>
      <td>
        <ArchiveBadge value={formatLevel(row.confidence_level)} type="confidence" />
      </td>
      <td>
        <ArchiveBadge value={formatRiskLevel(row.risk_level)} type="risk" />
      </td>
    </tr>
  );
}

// Ce composant affiche le détail de l’archive sélectionnée pour montrer la traçabilité de la prédiction.
function ArchiveDetailPanel({ archive }: { archive: ArchivedPrediction | null }) {
  if (!archive) {
    return (
      <aside className="rb-archive-detail" aria-label="Détail de l’archive sélectionnée">
        <div className="rb-archive-detail__header">
          <FileText size={20} strokeWidth={1.8} aria-hidden="true" />
          <h3>Détail de l’archive</h3>
        </div>
        <div className="rb-archive-detail__note">
          <span>Aucune archive sélectionnée</span>
          <p>Sélectionne une ligne lorsque des archives sont disponibles.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="rb-archive-detail" aria-label="Détail de l’archive sélectionnée">
      <div className="rb-archive-detail__header">
        <FileText size={20} strokeWidth={1.8} aria-hidden="true" />
        <h3>Détail de l’archive</h3>
      </div>

      <div className="rb-archive-detail__line" aria-label="Match">
        <UserRound size={16} aria-hidden="true" />
        <span>Match</span>
        <strong>
          {archive.home_team_name ?? "Équipe domicile"} vs {archive.away_team_name ?? "Équipe extérieure"}
        </strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Date de prédiction">
        <CalendarDays size={16} aria-hidden="true" />
        <span>Date de prédiction</span>
        <strong>{formatArchiveDate(archive.prediction_date, true)}</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Marché">
        <SlidersHorizontal size={16} aria-hidden="true" />
        <span>Marché</span>
        <strong>{formatMarketType(archive.market_type)}</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Prédiction">
        <TrendingUp size={16} aria-hidden="true" />
        <span>Prédiction</span>
        <strong>{formatPredictionValue(archive.predicted_value)}</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Confiance">
        <Target size={16} aria-hidden="true" />
        <span>Confiance</span>
        <strong>
          <ArchiveBadge value={formatLevel(archive.confidence_level)} type="confidence" />
        </strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Risque">
        <ShieldAlert size={16} aria-hidden="true" />
        <span>Risque</span>
        <strong>
          <ArchiveBadge value={formatRiskLevel(archive.risk_level)} type="risk" />
        </strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Score final">
        <Trophy size={16} aria-hidden="true" />
        <span>Score final</span>
        <strong>{formatFinalScore(archive)}</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Verdict">
        <CircleCheck size={16} aria-hidden="true" />
        <span>Verdict</span>
        <strong>
          <ArchiveBadge value={formatVerdict(archive.verdict)} type="verdict" />
        </strong>
      </div>

      <div className="rb-archive-detail__separator" />

      <div className="rb-archive-detail__note">
        <span>Justification initiale</span>
        <p>{archive.justification ?? "Aucune justification enregistrée pour cette archive."}</p>
      </div>
      <div className="rb-archive-detail__note">
        <span>Version moteur</span>
        <p>{archive.engine_version ?? "—"}</p>
      </div>
      <div className="rb-archive-detail__note">
        <span>Vérification</span>
        <p>
          {archive.checked_at
            ? `Archive vérifiée le ${formatArchiveDate(archive.checked_at, true)}.`
            : "Archive non vérifiée ou en attente du résultat final."}
        </p>
      </div>
    </aside>
  );
}

// Ce composant rend l’écran complet Archives avec KPI, filtres, tableau réel et panneau détail.
function ArchivesScreen() {
  const [competitionName, setCompetitionName] = useState<CompetitionFilter>("all");
  const [marketType, setMarketType] = useState<MarketFilter>("all");
  const [verdict, setVerdict] = useState<VerdictFilter>("all");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [archives, setArchives] = useState<ArchivedPrediction[]>([]);
  const [availableCompetitions, setAvailableCompetitions] = useState<string[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedArchiveId, setSelectedArchiveId] = useState<number | null>(null);

  const competitionFilterOptions = useMemo<ArchiveFilterOption<CompetitionFilter>[]>(() => {
    return [
      { value: "all", label: "Toutes" },
      ...availableCompetitions.map((competition) => ({
        value: competition,
        label: competition,
      })),
    ];
  }, [availableCompetitions]);

  const selectedArchive = useMemo(
    () => archives.find((archive) => archive.id === selectedArchiveId) ?? archives[0] ?? null,
    [archives, selectedArchiveId]
  );

  const kpis = useMemo<ArchiveKpi[]>(() => {
    const verifiableCount = archives.filter((archive) => archive.verdict === "correct" || archive.verdict === "incorrect").length;
    const correctCount = archives.filter((archive) => archive.verdict === "correct").length;
    const pendingCount = archives.filter((archive) => archive.verdict === "pending").length;
    const finishedMatchCount = new Set(
      archives.filter((archive) => isFinishedStatus(archive.match_status)).map(getArchiveMatchKey)
    ).size;
    const successRate = verifiableCount > 0 ? `${Math.round((correctCount / verifiableCount) * 100)} %` : "—";

    return [
      { label: "Prédictions archivées", value: String(totalCount), tone: "teal", icon: Archive },
      { label: "Matchs terminés affichés", value: String(finishedMatchCount), tone: "blue", icon: CalendarCheck2 },
      { label: "Taux page affichée", value: successRate, tone: "cyan", icon: Target },
      { label: "En attente affichées", value: String(pendingCount), tone: "amber", icon: Hourglass },
    ];
  }, [archives, totalCount]);

  const currentPage = Math.floor(offset / PAGE_LIMIT) + 1;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_LIMIT));
  const displayStart = totalCount === 0 ? 0 : offset + 1;
  const displayEnd = Math.min(offset + archives.length, totalCount);

  // Cette fonction remet la pagination au début après chaque changement de filtre.
  function resetPagination() {
    setOffset(0);
  }

  useEffect(() => {
    const query: ArchivedPredictionsQuery = {
      market_type: marketType === "all" ? undefined : marketType,
      verdict: verdict === "all" ? undefined : verdict,
      competition_name: competitionName === "all" ? undefined : competitionName,
      search: search.trim() || undefined,
      limit: PAGE_LIMIT,
      offset,
    };

    let isActive = true;

    async function loadArchives() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await getArchivedPredictions(query);

        if (!isActive) {
          return;
        }

        setArchives(response.items);
        setAvailableCompetitions(response.available_competitions ?? []);
        setTotalCount(response.count);

        if (response.status !== "available") {
          setError(response.message ?? "Les archives sont momentanément indisponibles.");
        }
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setArchives([]);
        setAvailableCompetitions([]);
        setTotalCount(0);
        setError(loadError instanceof Error ? loadError.message : "Erreur inconnue lors du chargement des archives.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    loadArchives();

    return () => {
      isActive = false;
    };
  }, [competitionName, marketType, verdict, search, offset]);

  useEffect(() => {
    if (archives.length === 0) {
      setSelectedArchiveId(null);
      return;
    }

    if (!archives.some((archive) => archive.id === selectedArchiveId)) {
      setSelectedArchiveId(archives[0].id);
    }
  }, [archives, selectedArchiveId]);

  return (
    <div className="rb-archives-screen">
      <header className="rb-archives-hero">
        <div className="rb-archives-hero__content">
          <p className="rb-eyebrow">Suivi & traçabilité</p>
          <h2>Archives des prédictions</h2>
          <p>
            Suivi des prédictions générées par RubyBets et comparaison avec les résultats réels.
          </p>
        </div>

        <aside className="rb-archives-hero__note">
          <Info size={20} strokeWidth={1.9} aria-hidden="true" />
          <p>
            Les archives servent à analyser la cohérence du moteur dans le temps. Elles ne
            garantissent aucun résultat futur.
          </p>
        </aside>
      </header>

      <section className="rb-archive-kpis" aria-label="Indicateurs des archives">
        {kpis.map((item) => (
          <ArchiveKpiCard key={item.label} item={item} />
        ))}
      </section>

      <div className="rb-archives-layout">
        <div className="rb-archives-main">
          <section className="rb-archive-filters" aria-label="Filtres des archives">
            <ArchiveFilter
              label="Compétition"
              value={competitionName}
              options={competitionFilterOptions}
              onChange={(nextValue) => {
                setCompetitionName(nextValue);
                resetPagination();
              }}
            />
            <ArchiveFilter
              label="Marché"
              value={marketType}
              options={marketFilterOptions}
              onChange={(nextValue) => {
                setMarketType(nextValue);
                resetPagination();
              }}
            />
            <ArchiveFilter
              label="Verdict"
              value={verdict}
              options={verdictFilterOptions}
              onChange={(nextValue) => {
                setVerdict(nextValue);
                resetPagination();
              }}
            />
            <label className="rb-archive-search">
              <span>Recherche équipe</span>
              <span className="rb-archive-search__field">
                <Search size={17} strokeWidth={1.9} aria-hidden="true" />
                <input
                  type="search"
                  placeholder="Rechercher une équipe"
                  aria-label="Rechercher une équipe ou une compétition"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    resetPagination();
                  }}
                />
              </span>
            </label>
          </section>

          <section className="rb-archive-table-card" aria-label="Tableau des prédictions archivées">
            <div className="rb-archive-table-wrap">
              <table className="rb-archive-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Match</th>
                    <th>Compétition</th>
                    <th>Marché</th>
                    <th>Prédiction RubyBets</th>
                    <th>Score final</th>
                    <th>Verdict</th>
                    <th>Confiance</th>
                    <th>Risque</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr className="rb-archive-table__row">
                      <td colSpan={9}>Chargement des archives...</td>
                    </tr>
                  ) : error ? (
                    <tr className="rb-archive-table__row">
                      <td colSpan={9}>{error}</td>
                    </tr>
                  ) : archives.length === 0 ? (
                    <tr className="rb-archive-table__row">
                      <td colSpan={9}>Aucune archive ne correspond aux filtres sélectionnés.</td>
                    </tr>
                  ) : (
                    archives.map((row) => (
                      <ArchiveTableRow
                        key={row.id}
                        row={row}
                        selected={row.id === selectedArchive?.id}
                        onSelect={() => setSelectedArchiveId(row.id)}
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <footer className="rb-archive-pagination" aria-label="Pagination des archives">
              <span>
                {displayStart}–{displayEnd} sur {totalCount}
              </span>
              <div>
                <button
                  type="button"
                  aria-label="Page précédente"
                  disabled={currentPage <= 1 || isLoading}
                  onClick={() => setOffset((currentOffset) => Math.max(0, currentOffset - PAGE_LIMIT))}
                >
                  <ChevronLeft size={18} aria-hidden="true" />
                </button>
                <button type="button" aria-current="page">
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
                  onClick={() => setOffset((currentOffset) => currentOffset + PAGE_LIMIT)}
                >
                  <ChevronRight size={18} aria-hidden="true" />
                </button>
              </div>
            </footer>
          </section>
        </div>

        <ArchiveDetailPanel archive={selectedArchive} />
      </div>
    </div>
  );
}

export default ArchivesScreen;

// Schéma de communication du fichier :
// ArchivesScreen.tsx
// ├── est appelé par App.tsx quand currentScreen vaut "archives"
// ├── appelle getArchivedPredictions dans services/api.ts
// ├── consomme les types ArchivedPrediction définis dans models/rubybets.ts
// ├── affiche les données réelles retournées par GET /api/archives/predictions
// └── utilise App.css pour conserver la maquette visuelle Archives branchée au backend
