// Ce composant affiche les informations de fraîcheur des données utilisées par RubyBets.
import type {
  CacheFreshness,
  MatchCompositeDataFreshness,
  RecommendationDataFreshness,
  SimpleDataFreshness,
} from "../models/rubybets";
import {
  formatCacheStatus,
  formatDateTime,
  formatTtlMinutes,
} from "../helpers/displayText";

type DataFreshness =
  | SimpleDataFreshness
  | MatchCompositeDataFreshness
  | RecommendationDataFreshness;

type DataFreshnessBlockProps = {
  title?: string;
  dataFreshness: DataFreshness;
};

// Cette fonction affiche un bloc de cache simple avec source, statut, mise à jour et durée de validité.
function renderCacheFreshness(
  label: string,
  cacheFreshness: CacheFreshness | null | undefined
) {
  if (!cacheFreshness) {
    return (
      <li>
        <strong>{label}</strong> : information de fraîcheur non disponible.
      </li>
    );
  }

  return (
    <li>
      <strong>{label}</strong> : {formatCacheStatus(cacheFreshness.from_cache)} —
      mise à jour : {formatDateTime(cacheFreshness.updated_at)} — validité :{" "}
      {formatTtlMinutes(cacheFreshness.ttl_minutes)}
    </li>
  );
}

// Cette fonction vérifie si la fraîcheur correspond à une réponse simple.
function isSimpleDataFreshness(
  dataFreshness: DataFreshness
): dataFreshness is SimpleDataFreshness {
  return "from_cache" in dataFreshness;
}

// Cette fonction vérifie si la fraîcheur correspond à une réponse match + classement.
function isMatchCompositeDataFreshness(
  dataFreshness: DataFreshness
): dataFreshness is MatchCompositeDataFreshness {
  return "match_cache" in dataFreshness;
}

// Cette fonction vérifie si la fraîcheur correspond à une recommandation multi-matchs.
function isRecommendationDataFreshness(
  dataFreshness: DataFreshness
): dataFreshness is RecommendationDataFreshness {
  return "matches_cache" in dataFreshness;
}

// Ce composant affiche une synthèse lisible de la fraîcheur des données backend.
function DataFreshnessBlock({
  title = "Fraîcheur des données",
  dataFreshness,
}: DataFreshnessBlockProps) {
  return (
    <aside>
      <h4>{title}</h4>

      {isSimpleDataFreshness(dataFreshness) && (
        <ul>
          <li>
            <strong>Source</strong> :{" "}
            {dataFreshness.provider || dataFreshness.source}
          </li>
          {renderCacheFreshness("Données", dataFreshness)}
          {dataFreshness.last_updated && (
            <li>
              <strong>Dernière mise à jour source</strong> :{" "}
              {formatDateTime(dataFreshness.last_updated)}
            </li>
          )}
        </ul>
      )}

      {isMatchCompositeDataFreshness(dataFreshness) && (
        <ul>
          <li>
            <strong>Source</strong> : {dataFreshness.provider}
          </li>
          <li>
            <strong>Dernière mise à jour du match</strong> :{" "}
            {formatDateTime(dataFreshness.match_last_updated)}
          </li>
          {renderCacheFreshness("Cache match", dataFreshness.match_cache)}
          {renderCacheFreshness(
            "Cache classement",
            dataFreshness.standings_cache
          )}
        </ul>
      )}

      {isRecommendationDataFreshness(dataFreshness) && (
        <ul>
          <li>
            <strong>Source</strong> : {dataFreshness.provider}
          </li>
          <li>
            <strong>Recommandation générée le</strong> :{" "}
            {formatDateTime(dataFreshness.generated_at)}
          </li>
          {renderCacheFreshness("Cache matchs", dataFreshness.matches_cache)}
          {renderCacheFreshness(
            "Cache classement",
            dataFreshness.standings_cache
          )}
        </ul>
      )}
    </aside>
  );
}

export default DataFreshnessBlock;

// Schéma de communication du fichier :
// DataFreshnessBlock.tsx
// ├── reçoit data_freshness depuis les composants métier
// ├── utilise rubybets.ts pour typer les structures de fraîcheur
// ├── utilise displayText.ts pour formater cache, dates et TTL
// └── sera utilisé par les blocs détail match, analyse, prédictions et recommandation