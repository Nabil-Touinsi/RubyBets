// Ce fichier affiche le contexte d'actualité premium d'un match avec filtres, images et couverture des équipes.
// Il présente uniquement les articles réellement fournis par le backend et distingue les états vide, partiel et indisponible.

import { useMemo, useState } from "react";
import {
  Clock3,
  ExternalLink,
  HeartPulse,
  ImageOff,
  Info,
  MessageSquareText,
  Newspaper,
  RefreshCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Swords,
  Trophy,
  Users,
} from "lucide-react";
import type {
  Match,
  MatchNewsContextLoadState,
  MatchNewsContextResponse,
  TeamNewsArticle,
  TeamNewsBlock,
} from "../models/rubybets";
import { getTeamInitials } from "../helpers/displayText";

type MatchNewsContextSectionProps = {
  match: Match;
  matchNewsContext: MatchNewsContextResponse | null;
  matchNewsContextStatus: string;
  loadState: MatchNewsContextLoadState;
  onRetry: () => void;
};

type ContextNewsFilter =
  | "all"
  | "teams"
  | "injuries"
  | "declarations"
  | "tactics"
  | "competition";

type ContextNewsSort = "relevance" | "recent";

const CONTEXT_NEWS_FILTERS: Array<{
  key: ContextNewsFilter;
  label: string;
  icon: typeof Newspaper;
}> = [
  { key: "all", label: "Toutes", icon: Newspaper },
  { key: "teams", label: "Équipes", icon: Users },
  { key: "injuries", label: "Blessures", icon: HeartPulse },
  { key: "declarations", label: "Déclarations", icon: MessageSquareText },
  { key: "tactics", label: "Tactique", icon: SlidersHorizontal },
  { key: "competition", label: "Compétition", icon: Trophy },
];

// Cette fonction formate la date de dernière recherche sans exposer les détails techniques du fournisseur.
function formatContextSearchDate(value: string | null | undefined) {
  if (!value) {
    return "heure non fournie";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "heure non fournie";
  }

  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  const formattedTime = new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);

  return isToday
    ? `aujourd’hui à ${formattedTime}`
    : new Intl.DateTimeFormat("fr-FR", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

// Cette fonction transforme la date d'un article en délai relatif lisible.
function formatContextArticleAge(value: string | null) {
  if (!value) {
    return "Date non fournie";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Date non fournie";
  }

  const elapsedMilliseconds = Date.now() - date.getTime();
  const elapsedHours = Math.max(0, Math.floor(elapsedMilliseconds / 3_600_000));

  if (elapsedHours < 1) {
    return "Il y a moins d’1 h";
  }

  if (elapsedHours < 24) {
    return `Il y a ${elapsedHours} h`;
  }

  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays <= 7) {
    return `Il y a ${elapsedDays} j`;
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

// Cette fonction récupère l'URL éditeur résolue lorsqu'elle est disponible.
function getContextArticleUrl(article: TeamNewsArticle) {
  return article.resolved_url || article.url;
}

// Cette fonction retire le suffixe éditeur du titre lorsqu'il répète déjà la source affichée.
function getContextArticleTitle(article: TeamNewsArticle) {
  const title = String(article.title || "Actualité sans titre").trim();
  const sourceName = String(article.source_name || "").trim();

  if (!sourceName) {
    return title;
  }

  const sourceSuffix = ` - ${sourceName}`;
  return title.toLowerCase().endsWith(sourceSuffix.toLowerCase())
    ? title.slice(0, -sourceSuffix.length).trim()
    : title;
}

// Cette fonction évite de répéter le titre RSS dans la description de la carte.
function getContextArticleDescription(article: TeamNewsArticle) {
  const description = String(article.description || "").trim();
  const normalizedTitle = getContextArticleTitle(article).toLowerCase();
  const normalizedDescription = description.toLowerCase();

  if (!description || normalizedDescription === normalizedTitle) {
    return "Aucun extrait éditorial complémentaire n’a été fourni par cette source.";
  }

  if (
    normalizedDescription.startsWith(normalizedTitle) ||
    normalizedTitle.startsWith(normalizedDescription)
  ) {
    return "La source présente cette information comme un élément de contexte récent lié au match.";
  }

  return description;
}

// Cette fonction retourne le niveau de priorité public sans afficher un score technique interne.
function getContextPriorityLabel(article: TeamNewsArticle) {
  if (article.relevance === "high") {
    return "Priorité élevée";
  }

  if (article.relevance === "medium") {
    return "Priorité moyenne";
  }

  return "Information complémentaire";
}

// Cette fonction transforme la catégorie backend en libellé court adapté à la maquette.
function getContextCategoryLabel(article: TeamNewsArticle) {
  const labels: Record<string, string> = {
    injury_absence: "Blessures",
    lineup_squad: "Effectif",
    recent_form: "Équipe",
    coach_tactics: "Déclarations",
    competition_context: "Compétition",
    other: "Contexte",
  };

  return labels[String(article.category)] || article.category_label || "Contexte";
}

// Cette fonction vérifie si un article correspond au filtre sélectionné.
function matchesContextFilter(
  article: TeamNewsArticle,
  filter: ContextNewsFilter
) {
  const searchableText = `${article.title ?? ""} ${article.description ?? ""}`.toLowerCase();

  if (filter === "all") {
    return true;
  }

  if (filter === "teams") {
    return Boolean(article.team_detected || article.teams_detected?.length);
  }

  if (filter === "injuries") {
    return article.category === "injury_absence" || /injur|bless|absen|suspend/.test(searchableText);
  }

  if (filter === "competition") {
    return article.category === "competition_context";
  }

  if (filter === "tactics") {
    return /tactic|formation|system|pressing|stratég|dispositif/.test(searchableText);
  }

  return (
    article.category === "coach_tactics" &&
    /coach|manager|entraîneur|déclar|conference|conférence|said|explains/.test(
      searchableText
    )
  );
}

// Cette fonction fusionne les anciens blocs équipe lorsque le backend ne fournit pas encore la liste globale.
function buildFallbackMatchArticles(response: MatchNewsContextResponse) {
  const seenKeys = new Set<string>();
  const mergedArticles: TeamNewsArticle[] = [];
  const teamArticles = [
    response.home_team.articles,
    response.away_team.articles,
  ];
  const maxLength = Math.max(...teamArticles.map((articles) => articles.length), 0);

  for (let index = 0; index < maxLength; index += 1) {
    for (const articles of teamArticles) {
      const article = articles[index];
      if (!article) {
        continue;
      }

      const key = `${article.title ?? ""}-${getContextArticleUrl(article) ?? ""}`.toLowerCase();
      if (!key || seenKeys.has(key)) {
        continue;
      }

      seenKeys.add(key);
      mergedArticles.push(article);

      if (mergedArticles.length >= 5) {
        return mergedArticles;
      }
    }
  }

  return mergedArticles;
}

// Cette fonction produit les initiales de secours d'une équipe sans inventer de logo.
function getContextTeamInitials(teamName: string | null) {
  return getTeamInitials({ id: null, name: teamName, short_name: teamName, crest: null });
}

// Ce composant affiche le logo réel d'une équipe ou ses initiales lorsque le logo manque.
function ContextTeamLogo({
  name,
  crest,
}: {
  name: string | null;
  crest: string | null;
}) {
  const [hasImageError, setHasImageError] = useState(false);

  if (crest && !hasImageError) {
    return (
      <img
        className="rb-detail-context-team-logo"
        src={crest}
        alt=""
        onError={() => setHasImageError(true)}
      />
    );
  }

  return (
    <span className="rb-detail-context-team-logo rb-detail-context-team-logo--fallback" aria-hidden="true">
      {getContextTeamInitials(name)}
    </span>
  );
}

// Ce composant affiche une image d'article réelle ou un placeholder cohérent avec sa catégorie.
function ContextArticleImage({ article }: { article: TeamNewsArticle }) {
  const [hasImageError, setHasImageError] = useState(false);

  if (!article.image_url || hasImageError) {
    return (
      <div className={`rb-detail-context-article-image rb-detail-context-article-image--${String(article.category)}`}>
        <ImageOff size={24} strokeWidth={1.6} aria-hidden="true" />
        <span>{getContextCategoryLabel(article)}</span>
      </div>
    );
  }

  return (
    <div className="rb-detail-context-article-image">
      <img
        src={article.image_url}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setHasImageError(true)}
      />
    </div>
  );
}

// Ce composant affiche une carte d'article compacte conforme à la direction Obsidian Teal.
function ContextArticleCard({ article }: { article: TeamNewsArticle }) {
  const articleUrl = getContextArticleUrl(article);
  const detectedTeams = article.teams_detected?.length
    ? article.teams_detected
    : article.team_detected
      ? [article.team_detected]
      : [];

  return (
    <article className="rb-detail-context-article-card">
      <ContextArticleImage article={article} />

      <div className="rb-detail-context-article-copy">
        <div className="rb-detail-context-article-heading">
          <h3>{getContextArticleTitle(article)}</h3>
          <span className={`rb-detail-context-priority rb-detail-context-priority--${article.relevance}`}>
            {getContextPriorityLabel(article)}
          </span>
        </div>

        <p>{getContextArticleDescription(article)}</p>

        <div className="rb-detail-context-article-tags" aria-label="Catégories de l'article">
          <span>{getContextCategoryLabel(article)}</span>
          {detectedTeams.slice(0, 2).map((teamName) => (
            <span className="rb-detail-context-article-team-tag" key={teamName}>
              {teamName}
            </span>
          ))}
        </div>
      </div>

      <div className="rb-detail-context-article-meta">
        <strong>{article.source_name || "Source publique"}</strong>
        <span>
          <Clock3 size={13} strokeWidth={1.8} aria-hidden="true" />
          {formatContextArticleAge(article.published_at)}
        </span>
        {articleUrl ? (
          <a href={articleUrl} target="_blank" rel="noopener noreferrer">
            Lire
            <ExternalLink size={13} strokeWidth={1.8} aria-hidden="true" />
          </a>
        ) : null}
      </div>
    </article>
  );
}

// Ce composant affiche la couverture compacte des actualités pour une équipe.
function ContextCoverageCard({
  teamBlock,
  crest,
}: {
  teamBlock: TeamNewsBlock;
  crest: string | null;
}) {
  const uniqueSourceCount = new Set(
    teamBlock.articles
      .map((article) => String(article.source_name || "").trim().toLowerCase())
      .filter(Boolean)
  ).size;
  const sourceCount = uniqueSourceCount || teamBlock.articles_count;

  return (
    <article className="rb-detail-context-coverage-card">
      <ContextTeamLogo name={teamBlock.name} crest={crest} />
      <div>
        <strong>{teamBlock.name || "Équipe non fournie"}</strong>
        <span>
          {sourceCount} source{sourceCount > 1 ? "s" : ""} exploitable{sourceCount > 1 ? "s" : ""}
        </span>
        <small>
          {teamBlock.status === "available"
            ? "Couverture disponible"
            : teamBlock.status === "unavailable"
              ? "Source temporairement inaccessible"
              : "Aucune information récente"}
        </small>
      </div>
    </article>
  );
}

// Ce composant affiche un état d'attente, une erreur technique ou une absence réelle de contenu.
function ContextNewsState({
  loadState,
  statusMessage,
  emptyState,
  onRetry,
}: {
  loadState: MatchNewsContextLoadState;
  statusMessage: string;
  emptyState?: string | null;
  onRetry?: () => void;
}) {
  const isLoading = loadState === "loading";
  const isError = loadState === "error";

  return (
    <div className={`rb-detail-context-state rb-detail-context-state--${loadState}`} role={isError ? "alert" : "status"}>
      <span className="rb-detail-context-state-icon" aria-hidden="true">
        {isLoading ? <Sparkles size={22} /> : isError ? <Info size={22} /> : <Newspaper size={22} />}
      </span>
      <div>
        <strong>
          {isLoading
            ? "Recherche des actualités utiles"
            : isError
              ? "Actualités temporairement indisponibles"
              : "Aucune actualité pertinente trouvée"}
        </strong>
        <p>{emptyState || statusMessage}</p>
        {onRetry ? (
          <button type="button" onClick={onRetry}>
            <RefreshCcw size={15} strokeWidth={1.8} aria-hidden="true" />
            Relancer la recherche
          </button>
        ) : null}
      </div>
    </div>
  );
}

// Ce composant affiche le bloc complet Actualités liées au match.
function MatchNewsContextSection({
  match,
  matchNewsContext,
  matchNewsContextStatus,
  loadState,
  onRetry,
}: MatchNewsContextSectionProps) {
  const [activeFilter, setActiveFilter] = useState<ContextNewsFilter>("all");
  const [sortMode, setSortMode] = useState<ContextNewsSort>("relevance");
  const [showAllArticles, setShowAllArticles] = useState(false);

  const allArticles = useMemo(() => {
    if (!matchNewsContext) {
      return [];
    }

    return matchNewsContext.articles?.length
      ? matchNewsContext.articles
      : buildFallbackMatchArticles(matchNewsContext);
  }, [matchNewsContext]);

  const filteredArticles = useMemo(() => {
    const relevanceOrder: Record<string, number> = { high: 3, medium: 2, low: 1 };
    const articles = allArticles.filter((article) => matchesContextFilter(article, activeFilter));

    return [...articles].sort((firstArticle, secondArticle) => {
      if (sortMode === "recent") {
        return (
          new Date(secondArticle.published_at || 0).getTime() -
          new Date(firstArticle.published_at || 0).getTime()
        );
      }

      return (
        (relevanceOrder[secondArticle.relevance] || 0) -
          (relevanceOrder[firstArticle.relevance] || 0) ||
        new Date(secondArticle.published_at || 0).getTime() -
          new Date(firstArticle.published_at || 0).getTime()
      );
    });
  }, [activeFilter, allArticles, sortMode]);

  const visibleArticles = showAllArticles
    ? filteredArticles
    : filteredArticles.slice(0, 5);

  const showState =
    loadState !== "success" ||
    !matchNewsContext ||
    matchNewsContext.status === "empty" ||
    matchNewsContext.status === "unavailable" ||
    allArticles.length === 0;

  return (
    <section className="rb-detail-context-shell" aria-labelledby="rb-detail-context-title">
      <div className="rb-detail-context-header">
        <div>
          <p className="rb-detail-context-eyebrow">
            <Newspaper size={16} strokeWidth={1.8} aria-hidden="true" />
            Actualités liées au match
          </p>
          <h2 id="rb-detail-context-title">Contexte éditorial vérifié</h2>
          <span>
            Sources publiques filtrées · Dernière recherche : {formatContextSearchDate(matchNewsContext?.generated_at)}
          </span>
        </div>
        <span className="rb-detail-context-status-badge">
          <ShieldCheck size={15} strokeWidth={1.8} aria-hidden="true" />
          {matchNewsContext?.status === "partial" ? "Couverture partielle" : "Contexte filtré"}
        </span>
      </div>

      <div className="rb-detail-context-content-grid">
        <div className="rb-detail-context-news-column">
          <div className="rb-detail-context-toolbar">
            <div className="rb-detail-context-filters" role="group" aria-label="Filtrer les actualités">
              {CONTEXT_NEWS_FILTERS.map((filter) => {
                const FilterIcon = filter.icon;
                return (
                  <button
                    className={activeFilter === filter.key ? "is-active" : ""}
                    type="button"
                    key={filter.key}
                    onClick={() => {
                      setActiveFilter(filter.key);
                      setShowAllArticles(false);
                    }}
                  >
                    <FilterIcon size={14} strokeWidth={1.7} aria-hidden="true" />
                    {filter.label}
                  </button>
                );
              })}
            </div>

            <label className="rb-detail-context-sort">
              <span>Trier par</span>
              <select
                value={sortMode}
                onChange={(event) => setSortMode(event.target.value as ContextNewsSort)}
              >
                <option value="relevance">Pertinence</option>
                <option value="recent">Plus récentes</option>
              </select>
            </label>
          </div>

          {showState ? (
            <ContextNewsState
              loadState={loadState}
              statusMessage={matchNewsContextStatus}
              emptyState={matchNewsContext?.empty_state}
              onRetry={loadState === "error" ? onRetry : undefined}
            />
          ) : visibleArticles.length ? (
            <div className="rb-detail-context-article-list">
              {visibleArticles.map((article) => (
                <ContextArticleCard
                  article={article}
                  key={`${getContextArticleUrl(article) ?? "article"}-${article.title ?? "sans-titre"}`}
                />
              ))}
            </div>
          ) : (
            <ContextNewsState
              loadState="success"
              statusMessage="Aucun article ne correspond au filtre choisi."
            />
          )}

          {filteredArticles.length > 5 ? (
            <button
              className="rb-detail-context-more-button"
              type="button"
              onClick={() => setShowAllArticles((currentValue) => !currentValue)}
            >
              {showAllArticles ? "Réduire la liste" : "Voir plus d’actualités"}
            </button>
          ) : null}

          <aside className="rb-detail-context-coverage" aria-label="Couverture des actualités">
            <div className="rb-detail-context-coverage-heading">
              <p>Couverture actualités</p>
              <span>{allArticles.length} article{allArticles.length > 1 ? "s" : ""} retenu{allArticles.length > 1 ? "s" : ""}</span>
            </div>

            {matchNewsContext ? (
              <div className="rb-detail-context-coverage-cards">
                <ContextCoverageCard
                  teamBlock={matchNewsContext.home_team}
                  crest={match.home_team.crest}
                />
                <ContextCoverageCard
                  teamBlock={matchNewsContext.away_team}
                  crest={match.away_team.crest}
                />
              </div>
            ) : (
              <div className="rb-detail-context-coverage-placeholder">
                <Swords size={22} strokeWidth={1.6} aria-hidden="true" />
                <p>La couverture des deux équipes apparaîtra après la recherche.</p>
              </div>
            )}

            <div className="rb-detail-context-filter-note">
              <Info size={17} strokeWidth={1.8} aria-hidden="true" />
              <p>
                Les pages de score, résultats génériques et contenus sans lien direct avec l’avant-match sont écartés.
              </p>
            </div>
          </aside>
        </div>
      </div>

      <footer className="rb-detail-context-source-note">
        <Info size={15} strokeWidth={1.8} aria-hidden="true" />
        <span>
          Actualités publiques résolues vers leurs éditeurs lorsque cela est possible. Les informations peuvent être partielles et ne garantissent aucun résultat sportif.
        </span>
      </footer>
    </section>
  );
}

export default MatchNewsContextSection;

// Schéma de communication :
// App.tsx -> MatchDetailsScreen.tsx -> MatchNewsContextSection.tsx
// ├── consomme MatchNewsContextResponse depuis models/rubybets.ts
// ├── affiche les articles et images fournis par /api/matches/{match_id}/news-context
// ├── utilise les logos réels du Match sélectionné
// └── utilise uniquement les classes rb-detail-context-* de styles/MatchDetailsScreen.css
