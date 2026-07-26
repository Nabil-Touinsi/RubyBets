// Ce composant transforme les données du glossaire en centre d’apprentissage simple, navigable et responsable.

import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CircleHelp,
  Database,
  Grid2X2,
  Info,
  Lightbulb,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type {
  GlossaryItem,
  GlossaryResponse,
  ResponsibleInfoResponse,
} from "../models/rubybets";

type GlossarySectionProps = {
  glossary: GlossaryResponse | null;
  glossaryStatus: string;
  responsibleInfo?: ResponsibleInfoResponse | null;
  responsibleInfoStatus?: string;
};

type ResourceCategoryId = "all" | "results" | "goals" | "reading" | "data" | "caution";

type ResourceCategory = {
  id: ResourceCategoryId;
  label: string;
  count: number;
  icon: LucideIcon;
};

const CATEGORY_DEFINITIONS: Array<Omit<ResourceCategory, "count">> = [
  { id: "all", label: "Tous les termes", icon: Grid2X2 },
  { id: "results", label: "Résultats", icon: Target },
  { id: "goals", label: "Buts", icon: Target },
  { id: "reading", label: "Lecture du match", icon: TrendingUp },
  { id: "data", label: "Données", icon: Database },
  { id: "caution", label: "Prudence", icon: ShieldCheck },
];

const TERM_ORDER = [
  "1x2",
  "double chance",
  "btts",
  "over",
  "buts attendus (xg)",
  "buts attendus cadres (xgot)",
  "passes decisives attendues (xa)",
  "buts marques",
  "buts encaisses",
  "tirs cadres",
  "precision des tirs",
  "conversion des tirs",
  "grandes occasions",
  "possession",
  "precision des passes",
  "passes dans le dernier tiers",
  "duels gagnes",
  "forme recente",
  "indice de forme",
  "serie de resultats",
  "face a face",
  "avantage domicile",
  "classement",
  "composition probable",
  "composition officielle",
  "absence ou indisponibilite",
  "joueur incertain",
  "analyse pre-match",
  "confiance",
  "risque",
  "qualite des informations",
  "donnees partielles",
  "donnees reelles",
  "fraicheur",
  "scoring",
  "recommandation multi-matchs",
];

// Cette fonction uniformise une chaîne pour faciliter les recherches et les classements.
function normalizeText(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

// Cette fonction filtre les entrées internes ou trop techniques qui ne sont pas utiles à l’utilisateur.
function isUserFacingItem(item: GlossaryItem) {
  const term = normalizeText(item.term);
  const category = normalizeText(item.category);

  return !(
    term.includes("football-data") ||
    term.includes("flashscore") ||
    term === "mvp" ||
    term.includes("backend") ||
    term.includes("api") ||
    category === "project" ||
    category === "data-source"
  );
}

// Cette fonction classe un terme dans une seule catégorie claire afin d’éviter les doublons.
function getItemCategory(item: GlossaryItem): Exclude<ResourceCategoryId, "all"> {
  const term = normalizeText(item.term);
  const sourceCategory = normalizeText(item.category);

  if (
    term.includes("btts") ||
    term.includes("over") ||
    term.includes("under") ||
    term.includes("xg") ||
    term.includes("xgot") ||
    term.includes("xa") ||
    term.includes("but marque") ||
    term.includes("but encaisse") ||
    term.includes("tir") ||
    term.includes("grande occasion")
  ) {
    return "goals";
  }

  if (
    term.includes("1x2") ||
    term.includes("double chance") ||
    term.includes("recommandation multi-matchs") ||
    sourceCategory === "prediction" ||
    sourceCategory === "recommendation"
  ) {
    return "results";
  }

  if (
    term.includes("donnee") ||
    term.includes("fraicheur") ||
    term.includes("qualite des informations") ||
    sourceCategory === "data"
  ) {
    return "data";
  }

  if (
    term.includes("confiance") ||
    term.includes("risque") ||
    sourceCategory === "interpretation"
  ) {
    return "caution";
  }

  return "reading";
}

// Cette fonction retourne un libellé de catégorie court et orienté utilisateur.
function getCategoryLabel(item: GlossaryItem) {
  const categoryId = getItemCategory(item);
  return CATEGORY_DEFINITIONS.find((category) => category.id === categoryId)?.label ?? "Ressource";
}

// Cette fonction remplace uniquement les intitulés trop techniques par une formulation plus naturelle.
function getDisplayTerm(item: GlossaryItem) {
  const term = normalizeText(item.term);

  if (term.includes("scoring explicable")) {
    return "Lecture explicable";
  }

  if (term.includes("recommandation multi-matchs")) {
    return "Sélection multi-matchs";
  }

  return item.term;
}

// Cette fonction simplifie uniquement la définition de la méthode interne sans déformer les autres textes source.
function getDisplayDefinition(item: GlossaryItem) {
  const term = normalizeText(item.term);

  if (term.includes("scoring explicable")) {
    return "Méthode basée sur des règles lisibles qui permet de comprendre pourquoi une tendance est proposée.";
  }

  return item.definition;
}

// Cette fonction génère un repère visuel court à partir du nom du terme.
function getTermMarker(item: GlossaryItem) {
  const label = getDisplayTerm(item).trim();

  if (label.length <= 5) {
    return label.toUpperCase();
  }

  return label
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

// Cette fonction prépare un exemple d’usage adapté à chaque notion réellement disponible.
function getUsageSentence(item: GlossaryItem) {
  const term = normalizeText(item.term);

  if (term.includes("1x2")) {
    return "RubyBets utilise cette notion pour lire une tendance entre victoire à domicile, match nul ou victoire à l’extérieur.";
  }

  if (term.includes("double chance")) {
    return "RubyBets utilise cette notion lorsqu’une lecture prudente retient deux issues cohérentes plutôt qu’une seule.";
  }

  if (term.includes("btts")) {
    return "RubyBets utilise cette notion pour indiquer si les deux équipes peuvent présenter une tendance à marquer.";
  }

  if (term.includes("over") || term.includes("under")) {
    return "RubyBets utilise cette notion pour lire le volume possible de buts par rapport à un seuil donné.";
  }

  if (term.includes("xgot")) {
    return "RubyBets utilise cet indicateur pour compléter le xG par une lecture de la qualité réelle des tirs cadrés.";
  }

  if (term.includes("buts attendus") || term.includes("xg")) {
    return "RubyBets utilise cet indicateur pour comparer la qualité des occasions créées, au-delà du seul score final.";
  }

  if (term.includes("passes decisives attendues") || term.includes("xa")) {
    return "RubyBets utilise cet indicateur pour repérer la qualité des passes qui créent des occasions dangereuses.";
  }

  if (term.includes("tir cadre")) {
    return "RubyBets compare les tirs cadrés pour distinguer le volume offensif des tentatives réellement dirigées vers le but.";
  }

  if (term.includes("precision des tirs")) {
    return "RubyBets utilise ce rapport pour comparer la capacité des équipes à cadrer leurs tentatives.";
  }

  if (term.includes("conversion des tirs")) {
    return "RubyBets utilise ce rapport pour observer l’efficacité avec laquelle une équipe transforme ses tirs en buts.";
  }

  if (term.includes("grande occasion")) {
    return "RubyBets utilise ce repère pour compléter le nombre de tirs par une lecture des occasions les plus favorables.";
  }

  if (term === "tirs") {
    return "RubyBets utilise le volume de tirs comme un repère offensif, sans l’interpréter seul.";
  }

  if (term.includes("possession")) {
    return "RubyBets utilise la possession pour décrire le contrôle du ballon, sans l’assimiler automatiquement à une domination efficace.";
  }

  if (term.includes("precision des passes")) {
    return "RubyBets utilise cet indicateur pour comparer la maîtrise technique dans la circulation du ballon.";
  }

  if (term.includes("dernier tiers")) {
    return "RubyBets utilise ce repère pour observer la capacité d’une équipe à faire progresser le ballon dans la zone offensive.";
  }

  if (term.includes("duels gagnes")) {
    return "RubyBets utilise ce repère pour compléter la lecture de l’intensité et de la maîtrise des confrontations directes.";
  }

  if (term.includes("buts marques")) {
    return "RubyBets compare les buts marqués sur l’échantillon disponible pour situer la dynamique offensive récente.";
  }

  if (term.includes("buts encaisses")) {
    return "RubyBets compare les buts encaissés sur l’échantillon disponible pour situer la solidité défensive récente.";
  }

  if (term.includes("forme recente")) {
    return "RubyBets utilise les derniers résultats disponibles pour présenter la dynamique récente de chaque équipe.";
  }

  if (term.includes("indice de forme")) {
    return "RubyBets utilise cet indice comme un repère synthétique de comparaison, jamais comme une certitude.";
  }

  if (term.includes("serie de resultats")) {
    return "RubyBets affiche les séries récentes pour rendre l’enchaînement des résultats plus facile à lire.";
  }

  if (term.includes("face a face")) {
    return "RubyBets présente les confrontations directes disponibles comme un contexte historique complémentaire.";
  }

  if (term.includes("avantage domicile")) {
    return "RubyBets tient compte du contexte domicile ou extérieur comme un signal parmi d’autres.";
  }

  if (term.includes("classement")) {
    return "RubyBets affiche le classement disponible pour situer les équipes dans leur compétition au moment de l’analyse.";
  }

  if (term.includes("composition probable")) {
    return "RubyBets affiche une composition probable uniquement lorsqu’une source fournit une estimation exploitable.";
  }

  if (term.includes("composition officielle")) {
    return "RubyBets distingue clairement la composition officielle d’une estimation ou d’un historique récent.";
  }

  if (term.includes("absence") || term.includes("indisponibilite")) {
    return "RubyBets affiche les absences uniquement lorsque cette information est réellement fournie par une source.";
  }

  if (term.includes("joueur incertain")) {
    return "RubyBets signale l’incertitude sans présenter la participation du joueur comme confirmée ou exclue.";
  }

  if (term.includes("qualite des informations")) {
    return "RubyBets utilise ce repère pour expliquer la couverture et la complétude des informations disponibles.";
  }

  if (term.includes("donnees partielles")) {
    return "RubyBets indique cet état lorsqu’une partie de la fiche reste exploitable malgré certaines informations manquantes.";
  }

  if (term.includes("confiance")) {
    return "RubyBets utilise ce repère pour montrer la solidité relative d’une lecture lorsque cette information est disponible.";
  }

  if (term.includes("risque")) {
    return "RubyBets utilise ce repère pour indiquer le niveau de prudence à conserver face à une lecture.";
  }

  if (term.includes("fraicheur")) {
    return "RubyBets affiche ce repère pour aider à comprendre à quel moment les informations ont été actualisées.";
  }

  if (term.includes("donnees reelles")) {
    return "RubyBets s’appuie sur des informations sportives issues de sources externes plutôt que sur des données inventées.";
  }

  if (term.includes("recommandation multi-matchs")) {
    return "RubyBets rassemble plusieurs choix cohérents selon le style de sélection demandé par l’utilisateur.";
  }

  if (term.includes("scoring explicable")) {
    return "RubyBets privilégie une lecture dont les raisons peuvent être présentées clairement à l’utilisateur.";
  }

  return "RubyBets utilise cette notion pour rendre la lecture d’un match plus claire avant son coup d’envoi.";
}

// Cette fonction prépare le message essentiel associé au terme sélectionné.
function getTakeaway(item: GlossaryItem) {
  const term = normalizeText(item.term);
  const category = getItemCategory(item);

  if (category === "data") {
    return "La disponibilité, la couverture et la date de mise à jour des informations peuvent influencer la lecture d’un match.";
  }

  if (category === "caution") {
    return "Ce repère invite à conserver une lecture prudente et ne transforme jamais une tendance en certitude.";
  }

  if (
    term.includes("composition") ||
    term.includes("absence") ||
    term.includes("indisponibilite") ||
    term.includes("joueur incertain")
  ) {
    return "Ces informations peuvent évoluer jusqu’au coup d’envoi et doivent toujours être relues avec leur statut de disponibilité.";
  }

  if (term.includes("xg") || term.includes("xgot") || term.includes("xa")) {
    return "Cet indicateur décrit la qualité d’une action ou d’une occasion ; il ne prédit pas à lui seul le résultat final.";
  }

  return "Ceci est une aide à la décision avant-match, sans promesse de résultat sportif.";
}

// Cette fonction ordonne le glossaire avec les notions les plus utiles au parcours RubyBets en premier.
function sortItems(items: GlossaryItem[]) {
  return [...items].sort((firstItem, secondItem) => {
    const firstTerm = normalizeText(firstItem.term);
    const secondTerm = normalizeText(secondItem.term);
    const firstIndex = TERM_ORDER.findIndex((keyword) => firstTerm.includes(normalizeText(keyword)));
    const secondIndex = TERM_ORDER.findIndex((keyword) => secondTerm.includes(normalizeText(keyword)));
    const safeFirstIndex = firstIndex === -1 ? TERM_ORDER.length : firstIndex;
    const safeSecondIndex = secondIndex === -1 ? TERM_ORDER.length : secondIndex;

    if (safeFirstIndex !== safeSecondIndex) {
      return safeFirstIndex - safeSecondIndex;
    }

    return firstItem.term.localeCompare(secondItem.term, "fr");
  });
}

// Cette fonction calcule les catégories et leurs compteurs à partir des termes réellement affichés.
function buildCategories(items: GlossaryItem[]): ResourceCategory[] {
  return CATEGORY_DEFINITIONS.map((category) => ({
    ...category,
    count:
      category.id === "all"
        ? items.length
        : items.filter((item) => getItemCategory(item) === category.id).length,
  })).filter((category) => category.id === "all" || category.count > 0);
}

// Cette fonction retourne les notions associées au terme courant sans inventer de popularité.
function getRelatedItems(items: GlossaryItem[], selectedItem: GlossaryItem) {
  const selectedCategory = getItemCategory(selectedItem);
  const sameCategory = items.filter(
    (item) => item.slug !== selectedItem.slug && getItemCategory(item) === selectedCategory,
  );
  const otherItems = items.filter(
    (item) => item.slug !== selectedItem.slug && !sameCategory.some((related) => related.slug === item.slug),
  );

  return [...sameCategory, ...otherItems].slice(0, 4);
}

// Cette fonction construit les quatre engagements responsables à partir de la réponse backend.
function getResponsiblePoints(responsibleInfo: ResponsibleInfoResponse | null) {
  const defaultPoints = [
    "Aucun pari réel n’est proposé.",
    "Aucune garantie de résultat.",
    "Les informations proviennent de données réelles.",
    "Outil d’aide à la décision uniquement.",
  ];

  if (!responsibleInfo) {
    return defaultPoints;
  }

  const points = [
    responsibleInfo.summary.real_betting_enabled ? null : "Aucun pari réel n’est proposé.",
    responsibleInfo.summary.guarantees_result ? null : "Aucune garantie de résultat.",
    responsibleInfo.summary.uses_real_data ? "Les informations proviennent de données réelles." : null,
    responsibleInfo.summary.product_positioning || null,
  ].filter((point): point is string => Boolean(point));

  return points.length > 0 ? points.slice(0, 4) : defaultPoints;
}

// Ce composant affiche les catégories disponibles et permet de filtrer le glossaire.
function CategoryNavigation({
  categories,
  activeCategory,
  onSelect,
}: {
  categories: ResourceCategory[];
  activeCategory: ResourceCategoryId;
  onSelect: (categoryId: ResourceCategoryId) => void;
}) {
  return (
    <aside className="rb-learning-categories" aria-label="Catégories des ressources">
      <p className="rb-learning-panel-label">Catégories</p>

      <div className="rb-learning-category-list">
        {categories.map((category) => {
          const Icon = category.icon;
          const isActive = category.id === activeCategory;

          return (
            <button
              key={category.id}
              type="button"
              aria-pressed={isActive}
              className={
                isActive
                  ? "rb-learning-category rb-learning-category--active"
                  : "rb-learning-category"
              }
              onClick={() => onSelect(category.id)}
            >
              <span className="rb-learning-category__icon">
                <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
              </span>
              <strong>{category.label}</strong>
              <span className="rb-learning-category__count">{category.count}</span>
            </button>
          );
        })}
      </div>

      <div className="rb-learning-category-note">
        <Lightbulb size={20} strokeWidth={1.7} aria-hidden="true" />
        <span>Des termes clairs pour mieux comprendre nos analyses.</span>
      </div>
    </aside>
  );
}

// Ce composant affiche la définition sélectionnée et les commandes précédent/suivant.
function ResourceDetail({
  item,
  relatedItems,
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
  onSelectRelated,
}: {
  item: GlossaryItem;
  relatedItems: GlossaryItem[];
  hasPrevious: boolean;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onSelectRelated: (slug: string) => void;
}) {
  return (
    <article className="rb-learning-detail" key={item.slug}>
      <div className="rb-learning-detail__header">
        <span className="rb-learning-detail__marker">{getTermMarker(item)}</span>

        <div className="rb-learning-detail__identity">
          <h2>{getDisplayTerm(item)}</h2>
          <span>{getCategoryLabel(item)}</span>
        </div>

        <div className="rb-learning-detail__nav" aria-label="Naviguer entre les notions">
          <button type="button" disabled={!hasPrevious} onClick={onPrevious}>
            <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
            Précédent
          </button>
          <button type="button" disabled={!hasNext} onClick={onNext}>
            Suivant
            <ArrowRight size={16} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="rb-learning-definition">
        <h3>
          <BookOpen size={17} strokeWidth={1.8} aria-hidden="true" />
          Définition
        </h3>
        <p>{getDisplayDefinition(item)}</p>
      </div>

      <div className="rb-learning-usage">
        <h3>
          <Sparkles size={17} strokeWidth={1.8} aria-hidden="true" />
          Exemple d’utilisation dans RubyBets
        </h3>
        <p>{getUsageSentence(item)}</p>

        <div className="rb-learning-example-grid">
          <div>
            <span>Exemple</span>
            <strong>{getDisplayTerm(item)}</strong>
          </div>
          <div>
            <span>Usage RubyBets</span>
            <strong>Lecture avant-match</strong>
          </div>
          <div>
            <span>Cadre</span>
            <strong>Aide à la décision</strong>
          </div>
        </div>
      </div>

      <div className="rb-learning-takeaway">
        <Info size={18} strokeWidth={1.8} aria-hidden="true" />
        <span>
          <strong>À retenir</strong>
          {getTakeaway(item)}
        </span>
      </div>

      {relatedItems.length > 0 ? (
        <div className="rb-learning-related">
          <h3>Notions associées</h3>
          <div>
            {relatedItems.map((relatedItem) => (
              <button
                key={relatedItem.slug}
                type="button"
                onClick={() => onSelectRelated(relatedItem.slug)}
              >
                {getDisplayTerm(relatedItem)}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

// Ce composant affiche les repères complémentaires et le cadre responsable alimenté par le backend.
function ResourceSidePanel({
  discoverItems,
  responsiblePoints,
  responsibleInfoStatus,
  onSelect,
}: {
  discoverItems: GlossaryItem[];
  responsiblePoints: string[];
  responsibleInfoStatus: string;
  onSelect: (slug: string) => void;
}) {
  return (
    <aside className="rb-learning-side" aria-label="Informations complémentaires">
      <article className="rb-learning-side-card rb-learning-side-card--purpose">
        <h2>
          <CircleHelp size={17} strokeWidth={1.8} aria-hidden="true" />
          Pourquoi cette ressource ?
        </h2>
        <p>
          Ce centre vous aide à comprendre les notions essentielles de RubyBets avec des
          explications simples, pour mieux interpréter les analyses avant-match.
        </p>
        <BookOpen className="rb-learning-side-watermark" size={70} strokeWidth={1} aria-hidden="true" />
      </article>

      <article className="rb-learning-side-card">
        <h2>
          <Sparkles size={17} strokeWidth={1.8} aria-hidden="true" />
          Notions à découvrir
        </h2>
        <div className="rb-learning-discover-list">
          {discoverItems.map((item) => (
            <button key={item.slug} type="button" onClick={() => onSelect(item.slug)}>
              <span>{getDisplayTerm(item)}</span>
              <ArrowRight size={15} strokeWidth={1.8} aria-hidden="true" />
            </button>
          ))}
        </div>
      </article>

      <article className="rb-learning-side-card rb-learning-side-card--responsible">
        <h2>
          <ShieldCheck size={17} strokeWidth={1.8} aria-hidden="true" />
          Cadre responsable
        </h2>
        <ul>
          {responsiblePoints.map((point) => (
            <li key={point}>
              <span aria-hidden="true">✓</span>
              {point}
            </li>
          ))}
        </ul>
        {responsibleInfoStatus.toLowerCase().includes("erreur") ? (
          <p className="rb-learning-side-status">Les rappels essentiels restent disponibles.</p>
        ) : null}
        <ShieldCheck className="rb-learning-side-shield" size={90} strokeWidth={1} aria-hidden="true" />
      </article>
    </aside>
  );
}

// Ce composant principal gère la recherche, la navigation par catégorie et le terme sélectionné.
function GlossarySection({
  glossary,
  glossaryStatus,
  responsibleInfo = null,
  responsibleInfoStatus = "",
}: GlossarySectionProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [activeCategory, setActiveCategory] = useState<ResourceCategoryId>("all");
  const [selectedSlug, setSelectedSlug] = useState("");

  const visibleItems = useMemo(
    () => sortItems((glossary?.items ?? []).filter(isUserFacingItem)),
    [glossary],
  );

  const categories = useMemo(() => buildCategories(visibleItems), [visibleItems]);

  const filteredItems = useMemo(() => {
    const normalizedSearch = normalizeText(searchTerm);

    return visibleItems.filter((item) => {
      const searchableText = normalizeText(
        `${getDisplayTerm(item)} ${getDisplayDefinition(item)} ${getCategoryLabel(item)}`,
      );
      const matchesSearch = normalizedSearch.length === 0 || searchableText.includes(normalizedSearch);
      const matchesCategory = activeCategory === "all" || getItemCategory(item) === activeCategory;

      return matchesSearch && matchesCategory;
    });
  }, [activeCategory, searchTerm, visibleItems]);

  const selectedItem =
    filteredItems.find((item) => item.slug === selectedSlug) ??
    filteredItems.find((item) => normalizeText(item.term).includes("1x2")) ??
    filteredItems[0] ??
    null;

  const selectedIndex = selectedItem
    ? filteredItems.findIndex((item) => item.slug === selectedItem.slug)
    : -1;

  const relatedItems = selectedItem ? getRelatedItems(visibleItems, selectedItem) : [];
  const discoverItems = selectedItem
    ? visibleItems.filter((item) => item.slug !== selectedItem.slug).slice(0, 5)
    : visibleItems.slice(0, 5);
  const responsiblePoints = getResponsiblePoints(responsibleInfo);

  // Cette fonction sélectionne un terme depuis une notion associée ou la colonne latérale.
  function selectItem(slug: string) {
    setSelectedSlug(slug);
    setActiveCategory("all");
    setSearchTerm("");
  }

  // Cette fonction applique une catégorie et repositionne la sélection sur son premier terme.
  function selectCategory(categoryId: ResourceCategoryId) {
    setActiveCategory(categoryId);
    setSelectedSlug("");
  }

  // Cette fonction sélectionne le terme précédent dans la liste filtrée.
  function selectPrevious() {
    if (selectedIndex > 0) {
      setSelectedSlug(filteredItems[selectedIndex - 1].slug);
    }
  }

  // Cette fonction sélectionne le terme suivant dans la liste filtrée.
  function selectNext() {
    if (selectedIndex >= 0 && selectedIndex < filteredItems.length - 1) {
      setSelectedSlug(filteredItems[selectedIndex + 1].slug);
    }
  }

  return (
    <div className="rb-learning-body">
      <label className="rb-learning-search" htmlFor="rb-learning-search-input">
        <Search size={20} strokeWidth={1.7} aria-hidden="true" />
        <input
          id="rb-learning-search-input"
          type="search"
          value={searchTerm}
          placeholder="Rechercher un terme, un concept..."
          onChange={(event) => {
            setSearchTerm(event.target.value);
            setSelectedSlug("");
          }}
        />
      </label>

      {visibleItems.length > 0 ? (
        <div className="rb-learning-grid">
          <CategoryNavigation
            categories={categories}
            activeCategory={activeCategory}
            onSelect={selectCategory}
          />

          {selectedItem ? (
            <ResourceDetail
              item={selectedItem}
              relatedItems={relatedItems}
              hasPrevious={selectedIndex > 0}
              hasNext={selectedIndex >= 0 && selectedIndex < filteredItems.length - 1}
              onPrevious={selectPrevious}
              onNext={selectNext}
              onSelectRelated={selectItem}
            />
          ) : (
            <div className="rb-learning-empty">
              <Search size={28} strokeWidth={1.5} aria-hidden="true" />
              <h2>Aucune notion trouvée</h2>
              <p>Essaie un autre mot ou sélectionne une autre catégorie.</p>
            </div>
          )}

          <ResourceSidePanel
            discoverItems={discoverItems}
            responsiblePoints={responsiblePoints}
            responsibleInfoStatus={responsibleInfoStatus}
            onSelect={selectItem}
          />
        </div>
      ) : (
        <div className="rb-learning-empty rb-learning-empty--full">
          <BookOpen size={30} strokeWidth={1.5} aria-hidden="true" />
          <h2>Les ressources sont momentanément indisponibles</h2>
          <p>{glossaryStatus || "Les définitions réapparaîtront dès que le service sera disponible."}</p>
        </div>
      )}

      <footer className="rb-learning-footer-note">
        <Info size={17} strokeWidth={1.8} aria-hidden="true" />
        <strong>RubyBets ne remplace ni votre jugement ni votre responsabilité.</strong>
        <span>Vous restez seul décisionnaire de vos choix.</span>
      </footer>
    </div>
  );
}

export default GlossarySection;

// Schéma de communication du fichier :
// ResourcesScreen.tsx
//   └── GlossarySection.tsx
//         ├── reçoit GlossaryResponse et ResponsibleInfoResponse depuis App.tsx
//         ├── classe et recherche les termes côté frontend
//         ├── affiche CategoryNavigation, ResourceDetail et ResourceSidePanel
//         ├── enrichit les exemples des notions utilisées dans la fiche détail match
//         └── utilise ResourcesScreen.css avec les données de app/api/glossary.py
