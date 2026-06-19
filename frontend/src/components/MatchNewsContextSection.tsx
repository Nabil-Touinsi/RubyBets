// Ce fichier affiche les actualités contextuelles des deux équipes dans l’onglet Contexte.
// Il présente uniquement les articles réellement fournis par le backend, avec un état vide responsable.

import type { MatchNewsContextResponse, TeamNewsArticle, TeamNewsBlock } from "../models/rubybets";

type MatchNewsContextSectionProps = {
  matchNewsContext: MatchNewsContextResponse | null;
  matchNewsContextStatus: string;
};

// Cette fonction formate une date de publication d’article sans inventer de valeur.
function formatNewsPublishedDate(value: string | null) {
  if (!value) {
    return "Date non fournie";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date non fournie";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

// Cette fonction affiche une source lisible pour un article.
function getNewsSourceLabel(article: TeamNewsArticle) {
  return article.source_name || "Source non fournie";
}

// Cette fonction affiche un libellé de pertinence simple pour éviter une lecture trop affirmative.
function getNewsRelevanceLabel(article: TeamNewsArticle) {
  if (article.relevance === "high") {
    return "Pertinence élevée";
  }

  if (article.relevance === "medium") {
    return "Pertinence moyenne";
  }

  return "Pertinence faible";
}

// Ce composant affiche une carte d’article d’actualité contextuelle.
function TeamNewsArticleCard({ article }: { article: TeamNewsArticle }) {
  return (
    <article className="rb-detail-v2-side-card">
      <h3>{article.title || "Actualité sans titre"}</h3>
      <p className="rb-detail-v2-info-line">
        <span>◈</span>
        <small>{article.category_label || "Autre"}</small>
        <strong>{getNewsRelevanceLabel(article)}</strong>
      </p>
      <p>{article.description || "Aucune description courte fournie par le flux RSS."}</p>

      <p className="rb-detail-v2-info-line">
        <span>↗</span>
        <small>{getNewsSourceLabel(article)}</small>
        <strong>{formatNewsPublishedDate(article.published_at)}</strong>
      </p>
      {article.url ? (
        <a href={article.url} target="_blank" rel="noreferrer">
          Lire la source
        </a>
      ) : null}
    </article>
  );
}

// Ce composant affiche les actualités disponibles pour une équipe donnée.
function TeamNewsBlockSection({ teamBlock }: { teamBlock: TeamNewsBlock }) {
  return (
    <section className="rb-detail-v2-card rb-detail-v2-recent-card">
      <div className="rb-detail-v2-section-header">
        <div>
          <p>Équipe</p>
          <h3>{teamBlock.name || "Équipe non fournie"}</h3>
        </div>
        <span>{teamBlock.articles_count} article(s)</span>
      </div>

      {teamBlock.articles.length ? (
        <div className="rb-detail-v2-recent-grid">
          {teamBlock.articles.map((article) => (
            <TeamNewsArticleCard
              key={`${teamBlock.name}-${article.url ?? article.title}`}
              article={article}
            />
          ))}
        </div>
      ) : (
        <div className="rb-detail-v2-empty-mini">
          <span>◈</span>
          <p>
            {teamBlock.message ||
              "Aucune actualité récente exploitable pour cette équipe."}
          </p>
        </div>
      )}
    </section>
  );
}

// Ce composant affiche le bloc complet Actualités récentes des équipes.
function MatchNewsContextSection({
  matchNewsContext,
  matchNewsContextStatus,
}: MatchNewsContextSectionProps) {
  if (!matchNewsContext) {
    return (
      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Actualités récentes des équipes</p>
        <h3>Actualités contextuelles en attente</h3>
        <p>
          {matchNewsContextStatus ||
            "Les actualités contextuelles n’ont pas encore été chargées pour cette rencontre."}
        </p>
        <p className="rb-detail-v2-footer-note">
          ⓘ Articles publics relayés à titre contextuel. RubyBets ne reprend pas les
          recommandations de pari éventuellement présentes dans les sources externes et
          ne garantit aucun résultat.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className="rb-detail-v2-card rb-detail-v2-analysis-card">
        <div className="rb-detail-v2-section-header">
          <div>
            <p>Contexte d’actualité</p>
            <h3>Actualités récentes des équipes</h3>
          </div>
          <span>{matchNewsContext.source_used || matchNewsContext.source}</span>
        </div>

        <p className="rb-detail-v2-analysis-lead">
          RubyBets récupère des actualités publiques récentes liées aux deux équipes,
          puis les filtre pour éviter d’afficher des articles trop génériques ou non pertinents.
        </p>

        {matchNewsContext.empty_state ? (
          <div className="rb-detail-v2-empty-mini">
            <span>◈</span>
            <p>{matchNewsContext.empty_state}</p>
          </div>
        ) : null}
      </section>

      <TeamNewsBlockSection teamBlock={matchNewsContext.home_team} />
      <TeamNewsBlockSection teamBlock={matchNewsContext.away_team} />

      <section className="rb-detail-v2-card rb-detail-v2-pending-tab">
        <p>Limites de lecture</p>
        <h3>Cadre responsable</h3>
        <ul className="rb-detail-v2-context-list">
          {matchNewsContext.limits.map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </section>
    </>
  );
}

export default MatchNewsContextSection;

// Schéma de communication :
// App.tsx -> MatchDetailsScreen.tsx -> MatchNewsContextSection.tsx
// ├── consomme MatchNewsContextResponse depuis models/rubybets.ts
// ├── affiche les articles fournis par /api/matches/{match_id}/news-context
// └── utilise les classes rb-detail-v2-* définies dans App.css
