// Ce fichier affiche l’accueil premium RubyBets validé : hero, aperçu et trois rencontres réelles de la compétition active.

import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Grid2X2,
  LockKeyholeOpen,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  TrendingUp,
  Trophy,
} from "lucide-react";
import HomeFeaturedMatchCard from "../components/HomeFeaturedMatchCard";
import { getTeamShortName, hasKnownTeams } from "../helpers/displayText";
import type { Competition, Match } from "../models/rubybets";
import type { AppScreen } from "../types/navigation";
import "../styles/DashboardScreen.css";

type DashboardScreenProps = {
  apiStatus: string;
  competitions: Competition[];
  matches: Match[];
  selectedCompetition: string;
  onSelectCompetition: (competitionCode: string) => void;
  onSelectMatch: (matchId: number) => void;
  onNavigate: (screen: AppScreen) => void;
};

const FEATURED_MATCH_COUNT = 3;

// Trie les rencontres de la compétition active sans inventer de notion d’importance sportive.
function getMatchesToFollow(matches: Match[]) {
  return [...matches].sort((firstMatch, secondMatch) => {
    const firstKnown = hasKnownTeams(firstMatch) ? 0 : 1;
    const secondKnown = hasKnownTeams(secondMatch) ? 0 : 1;

    if (firstKnown !== secondKnown) {
      return firstKnown - secondKnown;
    }

    return new Date(firstMatch.utc_date).getTime() - new Date(secondMatch.utc_date).getTime();
  });
}

// Transforme le statut de santé en formulation courte et compréhensible pour l’utilisateur.
function getAccessStatus(apiStatus: string) {
  const normalizedStatus = apiStatus.toLowerCase();

  if (normalizedStatus.includes("connect") || normalizedStatus.includes("ok")) {
    return { label: "Disponible", tone: "available" as const };
  }

  if (normalizedStatus.includes("cours") || normalizedStatus.includes("vérif")) {
    return { label: "Vérification", tone: "checking" as const };
  }

  return { label: "Indisponible", tone: "unavailable" as const };
}

// Calcule un libellé de fraîcheur lisible à partir de la dernière mise à jour disponible.
function getFreshnessLabel(matches: Match[]) {
  const latestTimestamp = matches.reduce<number | null>((latest, match) => {
    if (!match.last_updated) {
      return latest;
    }

    const timestamp = new Date(match.last_updated).getTime();

    if (Number.isNaN(timestamp)) {
      return latest;
    }

    return latest === null || timestamp > latest ? timestamp : latest;
  }, null);

  if (latestTimestamp === null) {
    return "En direct";
  }

  const elapsedMinutes = Math.max(0, Math.round((Date.now() - latestTimestamp) / 60_000));

  if (elapsedMinutes < 1) {
    return "À l’instant";
  }

  if (elapsedMinutes < 60) {
    return `Il y a ${elapsedMinutes} min`;
  }

  const elapsedHours = Math.round(elapsedMinutes / 60);
  return `Il y a ${elapsedHours} h`;
}

// Retourne les trois cartes visibles à partir de l’index courant du carrousel.
function getVisibleMatches(matches: Match[], startIndex: number) {
  return matches.slice(startIndex, startIndex + FEATURED_MATCH_COUNT);
}

// Affiche l’accueil validé en conservant uniquement des données réelles issues du frontend existant.
function DashboardScreen({
  apiStatus,
  competitions,
  matches,
  selectedCompetition,
  onSelectCompetition,
  onSelectMatch,
  onNavigate,
}: DashboardScreenProps) {
  const [carouselStart, setCarouselStart] = useState(0);

  const selectedCompetitionData = competitions.find(
    (competition) => competition.code === selectedCompetition,
  );

  const matchesToFollow = useMemo(() => getMatchesToFollow(matches), [matches]);
  const visibleMatches = getVisibleMatches(matchesToFollow, carouselStart);
  const readyMatchesCount = matches.filter((match) => hasKnownTeams(match)).length;
  const accessStatus = getAccessStatus(apiStatus);
  const freshnessLabel = getFreshnessLabel(matches);
  const hasPreviousPage = carouselStart > 0;
  const hasNextPage = carouselStart + FEATURED_MATCH_COUNT < matchesToFollow.length;
  const firstMatch = matchesToFollow[0] || null;

  useEffect(() => {
    setCarouselStart(0);
  }, [selectedCompetition, matchesToFollow.length]);

  // Affiche le groupe précédent de rencontres mises en avant.
  function showPreviousMatches() {
    setCarouselStart((currentStart) => Math.max(0, currentStart - FEATURED_MATCH_COUNT));
  }

  // Affiche le groupe suivant de rencontres mises en avant.
  function showNextMatches() {
    setCarouselStart((currentStart) =>
      Math.min(
        Math.max(0, matchesToFollow.length - FEATURED_MATCH_COUNT),
        currentStart + FEATURED_MATCH_COUNT,
      ),
    );
  }

  return (
    <div className="rb-home-v2" aria-labelledby="rb-home-v2-title">
      <section className="rb-home-v2-hero" aria-label="Bienvenue sur RubyBets">
        <div className="rb-home-v2-hero__main">
          <span className="rb-home-v2-hero__particles" aria-hidden="true" />

          <div className="rb-home-v2-hero__content">
            <p className="rb-home-v2-eyebrow">Bienvenue sur RubyBets</p>

            <h1 id="rb-home-v2-title">
              Préparez vos
              <span>matchs avant le coup d’envoi.</span>
            </h1>

            <p className="rb-home-v2-hero__lead">
              Des analyses claires pour comprendre les enjeux
              <span>des grandes rencontres.</span>
            </p>

            <div className="rb-home-v2-hero__actions" aria-label="Actions principales">
              <button
                type="button"
                className="rb-home-v2-button rb-home-v2-button--primary"
                onClick={() => onNavigate("matches")}
              >
                Explorer les matchs
                <ChevronRight aria-hidden="true" size={18} strokeWidth={2.2} />
              </button>

              <button
                type="button"
                className="rb-home-v2-button rb-home-v2-button--secondary"
                onClick={() => onNavigate("recommendation")}
              >
                <Star aria-hidden="true" size={17} strokeWidth={2} />
                Ma sélection
              </button>
            </div>

            <p className="rb-home-v2-hero__note">
              <ShieldCheck aria-hidden="true" size={16} strokeWidth={2.1} />
              Un outil d’aide à la décision, sans promesse de résultat.
            </p>
          </div>
        </div>

        <aside className="rb-home-v2-overview" aria-label="Aperçu des données disponibles">
          <header className="rb-home-v2-overview__header">
            <p className="rb-home-v2-eyebrow">Aperçu</p>
            <span className={`rb-home-v2-live rb-home-v2-live--${accessStatus.tone}`}>
              <i aria-hidden="true" />
              En direct
            </span>
          </header>

          <dl className="rb-home-v2-overview__list">
            <div>
              <dt>
                <Trophy aria-hidden="true" size={18} strokeWidth={1.9} />
                Compétition suivie
              </dt>
              <dd>{selectedCompetitionData?.code || selectedCompetition}</dd>
            </div>

            <div>
              <dt>
                <CalendarDays aria-hidden="true" size={18} strokeWidth={1.9} />
                Matchs à venir
              </dt>
              <dd>{matches.length}</dd>
            </div>

            <div>
              <dt>
                <TrendingUp aria-hidden="true" size={18} strokeWidth={1.9} />
                Rencontres prêtes
              </dt>
              <dd>{readyMatchesCount}</dd>
            </div>

            <div>
              <dt>
                <Clock3 aria-hidden="true" size={18} strokeWidth={1.9} />
                Mise à jour
              </dt>
              <dd>{freshnessLabel}</dd>
            </div>

            <div>
              <dt>
                <LockKeyholeOpen aria-hidden="true" size={18} strokeWidth={1.9} />
                Accès
              </dt>
              <dd className={`rb-home-v2-overview__access rb-home-v2-overview__access--${accessStatus.tone}`}>
                {accessStatus.label}
              </dd>
            </div>
          </dl>

          <p className="rb-home-v2-overview__welcome">
            Bon retour ! Prêt pour de belles analyses.
          </p>
        </aside>
      </section>

      <section className="rb-home-v2-featured" aria-labelledby="rb-home-v2-featured-title">
        <header className="rb-home-v2-featured__header">
          <div>
            <p className="rb-home-v2-eyebrow" id="rb-home-v2-featured-title">
              <Sparkles aria-hidden="true" size={15} strokeWidth={2.2} />
              Matchs à suivre
            </p>
            <span>Les rencontres de la compétition active à ne pas manquer.</span>
          </div>

          <div className="rb-home-v2-featured__tools">
            <label className="rb-home-v2-competition-select">
              <span className="sr-only">Choisir une compétition</span>
              <select
                value={selectedCompetition}
                onChange={(event) => onSelectCompetition(event.target.value)}
                aria-label="Choisir une compétition"
              >
                {competitions.map((competition) => (
                  <option key={competition.id} value={competition.code}>
                    {competition.name}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              className="rb-home-v2-calendar-link"
              onClick={() => onNavigate("matches")}
            >
              <CalendarDays aria-hidden="true" size={17} strokeWidth={1.9} />
              Voir tout le calendrier
            </button>
          </div>
        </header>

        <div className="rb-home-v2-featured__carousel">
          {hasPreviousPage ? (
            <button
              type="button"
              className="rb-home-v2-carousel-arrow rb-home-v2-carousel-arrow--previous"
              onClick={showPreviousMatches}
              aria-label="Afficher les matchs précédents"
            >
              <ChevronLeft aria-hidden="true" size={19} />
            </button>
          ) : null}

          <div className="rb-home-v2-featured__grid">
            {visibleMatches.length > 0 ? (
              visibleMatches.map((match, index) => (
                <HomeFeaturedMatchCard
                  key={match.id}
                  match={match}
                  competition={selectedCompetitionData || null}
                  position={carouselStart + index}
                  onSelect={onSelectMatch}
                />
              ))
            ) : (
              <div className="rb-home-v2-featured__empty" role="status">
                <CalendarDays aria-hidden="true" size={28} strokeWidth={1.8} />
                <div>
                  <strong>Aucune rencontre disponible</strong>
                  <span>Les prochains matchs apparaîtront ici dès leur publication.</span>
                </div>
              </div>
            )}
          </div>

          {hasNextPage ? (
            <button
              type="button"
              className="rb-home-v2-carousel-arrow rb-home-v2-carousel-arrow--next"
              onClick={showNextMatches}
              aria-label="Afficher les matchs suivants"
            >
              <ChevronRight aria-hidden="true" size={19} />
            </button>
          ) : null}
        </div>
      </section>

      <section className="rb-home-v2-shortcuts" aria-label="Accès rapides">
        <article className="rb-home-v2-shortcut rb-home-v2-shortcut--analysis">
          <span className="rb-home-v2-shortcut__icon" aria-hidden="true">
            <Search size={25} strokeWidth={1.9} />
          </span>

          <div>
            <p className="rb-home-v2-eyebrow">À analyser</p>
            <span>
              {firstMatch
                ? `${getTeamShortName(firstMatch.home_team)} — ${getTeamShortName(firstMatch.away_team)}`
                : "Choisissez une rencontre pour découvrir notre analyse simple et claire."}
            </span>
          </div>

          {firstMatch ? (
            <button
              type="button"
              onClick={() => onSelectMatch(firstMatch.id)}
              aria-label="Ouvrir la première rencontre à analyser"
            >
              Ouvrir
              <ArrowUpRight aria-hidden="true" size={16} />
            </button>
          ) : null}
        </article>

        <article className="rb-home-v2-shortcut rb-home-v2-shortcut--upcoming">
          <span className="rb-home-v2-shortcut__icon" aria-hidden="true">
            <CalendarDays size={25} strokeWidth={1.9} />
          </span>

          <div>
            <p className="rb-home-v2-eyebrow">Prochains matchs</p>
            <span>Retrouvez ici vos prochains rendez-vous à venir.</span>
          </div>

          <button type="button" onClick={() => onNavigate("matches")}>
            Voir tous
          </button>
        </article>
      </section>

      <section className="rb-home-v2-benefits" aria-label="Avantages de RubyBets">
        <article>
          <span aria-hidden="true">
            <TrendingUp size={25} strokeWidth={1.9} />
          </span>
          <div>
            <h2>Analyses claires</h2>
            <p>Des points essentiels pour comprendre l’essentiel.</p>
          </div>
        </article>

        <article>
          <span aria-hidden="true">
            <Grid2X2 size={24} strokeWidth={1.9} />
          </span>
          <div>
            <h2>Tout en un</h2>
            <p>Calendrier, analyses et suivi au même endroit.</p>
          </div>
        </article>

        <article>
          <span aria-hidden="true">
            <Clock3 size={25} strokeWidth={1.9} />
          </span>
          <div>
            <h2>Gain de temps</h2>
            <p>L’important, résumé simplement avant chaque match.</p>
          </div>
        </article>

        <article>
          <span aria-hidden="true">
            <ShieldCheck size={25} strokeWidth={1.9} />
          </span>
          <div>
            <h2>Usage responsable</h2>
            <p>Garder du recul, c’est faire des choix plus éclairés.</p>
          </div>
        </article>
      </section>

      <p className="rb-home-v2-footer-note" role="note">
        <ShieldCheck aria-hidden="true" size={15} strokeWidth={2} />
        RubyBets est un outil d’aide à la décision. Il ne garantit en aucun cas un gain ou un résultat.
      </p>
    </div>
  );
}

export default DashboardScreen;

// Schéma de communication du fichier :
// DashboardScreen.tsx
// ├── reçoit compétitions, matchs, état de disponibilité et actions depuis App.tsx
// ├── utilise HomeFeaturedMatchCard.tsx pour les trois rencontres de la compétition active
// ├── utilise les images locales de assets/home/ via DashboardScreen.css
// ├── renvoie les sélections de compétition et de match à App.tsx
// └── ouvre les écrans Matchs, Sélection et Détail sans modifier le backend
