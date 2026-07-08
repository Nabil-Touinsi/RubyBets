// Ce fichier crée l’écran Archives RubyBets avec des données mockées pour valider la maquette front avant le branchement backend.
// Il affiche les prédictions archivées, leur score final, leur verdict et le détail de l’archive sélectionnée.

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

type ArchiveVerdict = "Correcte" | "Incorrecte" | "En attente";
type ArchiveConfidence = "Élevée" | "Moyenne" | "Faible";
type ArchiveRisk = "Faible" | "Moyen" | "Élevé";

type ArchivePrediction = {
  id: number;
  date: string;
  match: string;
  flags: string[];
  competition: string;
  market: string;
  prediction: string;
  finalScore: string;
  verdict: ArchiveVerdict;
  confidence: ArchiveConfidence;
  risk: ArchiveRisk;
};

type ArchiveKpi = {
  label: string;
  value: string;
  tone: "teal" | "blue" | "cyan" | "amber";
  icon: LucideIcon;
};

const archiveKpis: ArchiveKpi[] = [
  { label: "Prédictions archivées", value: "128", tone: "teal", icon: Archive },
  { label: "Matchs terminés", value: "84", tone: "blue", icon: CalendarCheck2 },
  { label: "Taux de réussite global", value: "61 %", tone: "cyan", icon: Target },
  { label: "En attente de résultat", value: "44", tone: "amber", icon: Hourglass },
];

const archiveRows: ArchivePrediction[] = [
  {
    id: 1,
    date: "18/06/2026",
    match: "France vs Italie",
    flags: ["🇫🇷", "🇮🇹"],
    competition: "International",
    market: "1X2",
    prediction: "France gagne",
    finalScore: "2 - 1",
    verdict: "Correcte",
    confidence: "Élevée",
    risk: "Moyen",
  },
  {
    id: 2,
    date: "17/06/2026",
    match: "Espagne vs Croatie",
    flags: ["🇪🇸", "🇭🇷"],
    competition: "International",
    market: "BTTS",
    prediction: "Oui",
    finalScore: "1 - 0",
    verdict: "Incorrecte",
    confidence: "Moyenne",
    risk: "Moyen",
  },
  {
    id: 3,
    date: "20/06/2026",
    match: "Brésil vs Japon",
    flags: ["🇧🇷", "🇯🇵"],
    competition: "International",
    market: "Over 1.5",
    prediction: "Oui",
    finalScore: "—",
    verdict: "En attente",
    confidence: "Élevée",
    risk: "Faible",
  },
  {
    id: 4,
    date: "15/06/2026",
    match: "Portugal vs Pays-Bas",
    flags: ["🇵🇹", "🇳🇱"],
    competition: "Nations League",
    market: "1X2",
    prediction: "Portugal gagne",
    finalScore: "0 - 2",
    verdict: "Incorrecte",
    confidence: "Moyenne",
    risk: "Élevé",
  },
  {
    id: 5,
    date: "14/06/2026",
    match: "Angleterre vs Belgique",
    flags: ["🏴", "🇧🇪"],
    competition: "International",
    market: "BTTS",
    prediction: "Non",
    finalScore: "0 - 0",
    verdict: "Correcte",
    confidence: "Faible",
    risk: "Faible",
  },
];

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
    .replace(/\s+/g, "-");

  return (
    <span className={`rb-archive-badge rb-archive-badge--${type}-${normalizedValue}`}>
      {value}
    </span>
  );
}

// Ce composant affiche un contrôle de filtre visuel, sans logique de filtrage pour cette première passe front.
function ArchiveFilter({ label, value }: { label: string; value: string }) {
  return (
    <label className="rb-archive-filter">
      <span>{label}</span>
      <button type="button" aria-label={`${label} : ${value}`}>
        {value}
        <ChevronDown size={16} strokeWidth={2} aria-hidden="true" />
      </button>
    </label>
  );
}

// Ce composant affiche une ligne du tableau d’archives avec l’état sélectionné sur la première archive.
function ArchiveTableRow({ row, selected }: { row: ArchivePrediction; selected: boolean }) {
  return (
    <tr className={selected ? "rb-archive-table__row rb-archive-table__row--selected" : "rb-archive-table__row"}>
      <td>{row.date}</td>
      <td>
        <span className="rb-archive-match-cell">
          <span className="rb-archive-flags" aria-hidden="true">
            {row.flags.map((flag) => (
              <span key={`${row.id}-${flag}`}>{flag}</span>
            ))}
          </span>
          <strong>{row.match}</strong>
        </span>
      </td>
      <td>{row.competition}</td>
      <td>{row.market}</td>
      <td>{row.prediction}</td>
      <td>{row.finalScore}</td>
      <td>
        <ArchiveBadge value={row.verdict} type="verdict" />
      </td>
      <td>
        <ArchiveBadge value={row.confidence} type="confidence" />
      </td>
      <td>
        <ArchiveBadge value={row.risk} type="risk" />
      </td>
    </tr>
  );
}

// Ce composant affiche le détail de l’archive sélectionnée pour montrer la traçabilité de la prédiction.
function ArchiveDetailPanel() {
  return (
    <aside className="rb-archive-detail" aria-label="Détail de l’archive sélectionnée">
      <div className="rb-archive-detail__header">
        <FileText size={20} strokeWidth={1.8} aria-hidden="true" />
        <h3>Détail de l’archive</h3>
      </div>

      <div className="rb-archive-detail__line" aria-label="Match">
        <UserRound size={16} aria-hidden="true" />
        <span>Match</span>
        <strong>France vs Italie 🇫🇷 🇮🇹</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Date de prédiction">
        <CalendarDays size={16} aria-hidden="true" />
        <span>Date de prédiction</span>
        <strong>18/06/2026 à 14:32</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Marché">
        <SlidersHorizontal size={16} aria-hidden="true" />
        <span>Marché</span>
        <strong>1X2</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Prédiction">
        <TrendingUp size={16} aria-hidden="true" />
        <span>Prédiction</span>
        <strong>Victoire France</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Confiance">
        <Target size={16} aria-hidden="true" />
        <span>Confiance</span>
        <strong>
          <ArchiveBadge value="Élevée" type="confidence" />
        </strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Risque">
        <ShieldAlert size={16} aria-hidden="true" />
        <span>Risque</span>
        <strong>
          <ArchiveBadge value="Moyen" type="risk" />
        </strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Score final">
        <Trophy size={16} aria-hidden="true" />
        <span>Score final</span>
        <strong>2 - 1</strong>
      </div>
      <div className="rb-archive-detail__line" aria-label="Verdict">
        <CircleCheck size={16} aria-hidden="true" />
        <span>Verdict</span>
        <strong>
          <ArchiveBadge value="Correcte" type="verdict" />
        </strong>
      </div>

      <div className="rb-archive-detail__separator" />

      <div className="rb-archive-detail__note">
        <span>Justification initiale</span>
        <p>Signaux favorables à domicile, dynamique récente positive.</p>
      </div>
      <div className="rb-archive-detail__note">
        <span>Version moteur</span>
        <p>rubybets_ml_national_v18_3_4_dynamic_inference</p>
      </div>
    </aside>
  );
}

// Ce composant rend l’écran complet Archives avec KPI, filtres, tableau mocké et panneau détail.
function ArchivesScreen() {
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
        {archiveKpis.map((item) => (
          <ArchiveKpiCard key={item.label} item={item} />
        ))}
      </section>

      <div className="rb-archives-layout">
        <div className="rb-archives-main">
          <section className="rb-archive-filters" aria-label="Filtres des archives">
            <ArchiveFilter label="Compétition" value="Toutes" />
            <ArchiveFilter label="Statut du match" value="Tous" />
            <ArchiveFilter label="Marché" value="Tous" />
            <ArchiveFilter label="Verdict" value="Tous" />
            <label className="rb-archive-search">
              <span>Recherche équipe</span>
              <span className="rb-archive-search__field">
                <Search size={17} strokeWidth={1.9} aria-hidden="true" />
                <input type="search" placeholder="Rechercher une équipe" aria-label="Rechercher une équipe" />
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
                  {archiveRows.map((row) => (
                    <ArchiveTableRow key={row.id} row={row} selected={row.id === 1} />
                  ))}
                </tbody>
              </table>
            </div>

            <footer className="rb-archive-pagination" aria-label="Pagination des archives">
              <span>1–5 sur 128</span>
              <div>
                <button type="button" aria-label="Page précédente">
                  <ChevronLeft size={18} aria-hidden="true" />
                </button>
                <button type="button" aria-current="page">1</button>
                <button type="button">2</button>
                <button type="button">3</button>
                <span>...</span>
                <button type="button">26</button>
                <button type="button" aria-label="Page suivante">
                  <ChevronRight size={18} aria-hidden="true" />
                </button>
              </div>
            </footer>
          </section>
        </div>

        <ArchiveDetailPanel />
      </div>
    </div>
  );
}

export default ArchivesScreen;

// Schéma de communication du fichier :
// ArchivesScreen.tsx
// ├── est appelé par App.tsx quand currentScreen vaut "archives"
// ├── utilise navigation.ts et TopNavigation.tsx pour apparaître dans la navbar
// ├── utilise uniquement des données mockées pour cette première validation front
// └── utilise App.css pour reproduire la maquette visuelle Archives avant branchement backend
