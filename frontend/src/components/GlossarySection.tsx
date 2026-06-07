// Ce composant affiche le centre de ressources RubyBets avec recherche, catégories, fiche de définition et cadre responsable.

import { useMemo, useState } from "react";
import {
  BookOpen,
  CircleHelp,
  Database,
  Eye,
  Grid2X2,
  Info,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { GlossaryItem, GlossaryResponse } from "../models/rubybets";

type GlossarySectionProps = {
  glossary: GlossaryResponse | null;
  glossaryStatus: string;
};

type ResourceCategory = {
  id: string;
  label: string;
  count: number;
  icon: LucideIcon;
};

const CATEGORY_LABELS: Record<string, string> = {
  analysis: "Analyse",
  prediction: "Prédictions",
  predictions: "Prédictions",
  interpretation: "Interprétation",
  data: "Données",
  model: "Méthodologie",
  project: "Projet",
  recommendation: "Recommandation",
  risk: "Risque",
  confidence: "Analyse",
  market: "Prédictions",
  markets: "Prédictions",
};

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  all: Grid2X2,
  prediction: Target,
  predictions: Target,
  analysis: TrendingUp,
  interpretation: TrendingUp,
  risk: ShieldCheck,
  data: Database,
  model: Sparkles,
  methodology: Sparkles,
  responsible: Info,
};

const TERM_PRIORITY = [
  "1x2",
  "btts",
  "over",
  "under",
  "confiance",
  "risque",
  "analyse pré-match",
  "données réelles",
  "scoring",
  "forme",
  "xg",
];

// Cette fonction transforme une catégorie technique en libellé lisible pour l’utilisateur.
function formatCategory(category: string) {
  const normalizedCategory = category.trim().toLowerCase();

  if (CATEGORY_LABELS[normalizedCategory]) {
    return CATEGORY_LABELS[normalizedCategory];
  }

  return category
    .replace(/[-_]/g, " ")
    .replace(/\b\p{L}/gu, (letter) => letter.toUpperCase());
}

// Cette fonction génère un repère court pour identifier visuellement chaque terme.
function getTermMarker(term: string) {
  const cleanedTerm = term.trim();

  if (cleanedTerm.length <= 4) {
    return cleanedTerm.toUpperCase();
  }

  return cleanedTerm
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

// Cette fonction filtre les termes techniques qui ne doivent pas apparaître dans l’écran final.
function isTechnicalTerm(item: GlossaryItem) {
  const normalizedTerm = item.term.toLowerCase();
  const normalizedCategory = item.category.toLowerCase();

  return (
    normalizedTerm.includes("mvp") ||
    normalizedTerm.includes("backend") ||
    normalizedTerm.includes("api") ||
    normalizedTerm.includes("csv") ||
    normalizedTerm.includes("flashscore") ||
    normalizedTerm.includes("football-data") ||
    normalizedCategory.includes("project")
  );
}

// Cette fonction reformule les expressions sensibles pour garder une communication responsable.
function getResponsibleDefinition(definition: string) {
  return definition
    .replace(/paris sportifs/gi, "analyses sportives avant-match")
    .replace(/pari sportif/gi, "analyse sportive avant-match")
    .replace(/parier/gi, "interpréter une tendance")
    .replace(/bookmaker/gi, "opérateur externe");
}

// Cette fonction prépare une phrase d’usage adaptée au terme sélectionné.
function getUsageSentence(item: GlossaryItem) {
  const term = item.term.toLowerCase();

  if (term.includes("1x2")) {
    return "RubyBets utilise cette notion pour lire une tendance entre victoire à domicile, match nul ou victoire à l’extérieur.";
  }

  if (term.includes("btts")) {
    return "Cette notion aide à comprendre si les deux équipes présentent une tendance à marquer.";
  }

  if (term.includes("over") || term.includes("under")) {
    return "Cette lecture permet d’interpréter le volume probable de buts avant une rencontre.";
  }

  if (term.includes("confiance")) {
    return "Ce niveau aide à comprendre la solidité relative d’une recommandation analytique.";
  }

  if (term.includes("risque")) {
    return "Ce repère indique le niveau de prudence à conserver dans l’interprétation.";
  }

  if (term.includes("xg")) {
    return "Cet indicateur aide à qualifier la qualité des occasions plutôt que le seul score final.";
  }

  return "Ce terme aide à mieux interpréter les analyses, prédictions et recommandations affichées dans RubyBets.";
}

// Cette fonction rapproche l’ordre d’affichage du glossaire de la maquette validée.
function sortGlossaryItems(items: GlossaryItem[]) {
  return [...items].sort((firstItem, secondItem) => {
    const firstTerm = firstItem.term.toLowerCase();
    const secondTerm = secondItem.term.toLowerCase();
    const firstIndex = TERM_PRIORITY.findIndex((keyword) => firstTerm.includes(keyword));
    const secondIndex = TERM_PRIORITY.findIndex((keyword) => secondTerm.includes(keyword));
    const normalizedFirstIndex = firstIndex === -1 ? TERM_PRIORITY.length : firstIndex;
    const normalizedSecondIndex = secondIndex === -1 ? TERM_PRIORITY.length : secondIndex;

    if (normalizedFirstIndex !== normalizedSecondIndex) {
      return normalizedFirstIndex - normalizedSecondIndex;
    }

    return firstItem.term.localeCompare(secondItem.term, "fr");
  });
}

// Cette fonction sélectionne les termes les plus utiles à afficher dans la colonne latérale.
function getPopularItems(items: GlossaryItem[]) {
  const preferredTerms = ["1x2", "btts", "over", "confiance", "risque"];

  const selectedItems = preferredTerms
    .map((keyword) => items.find((item) => item.term.toLowerCase().includes(keyword)))
    .filter((item): item is GlossaryItem => Boolean(item));

  if (selectedItems.length >= 5) {
    return selectedItems.slice(0, 5);
  }

  const remainingItems = items.filter(
    (item) => !selectedItems.some((selectedItem) => selectedItem.slug === item.slug),
  );

  return [...selectedItems, ...remainingItems].slice(0, 5);
}

// Cette fonction prépare les catégories utilisées dans la navigation du centre de ressources.
function buildResourceCategories(items: GlossaryItem[]): ResourceCategory[] {
  const categories = [
    { id: "all", label: "Tous les termes", icon: Grid2X2 },
    { id: "prediction", label: "Prédictions", icon: Target },
    { id: "analysis", label: "Analyse", icon: TrendingUp },
    { id: "interpretation", label: "Interprétation", icon: TrendingUp },
    { id: "risk", label: "Risque", icon: ShieldCheck },
    { id: "data", label: "Données", icon: Database },
    { id: "model", label: "Méthodologie", icon: Sparkles },
    { id: "responsible", label: "Responsable", icon: Info },
  ];

  return categories.map((category) => {
    const count =
      category.id === "all"
        ? items.length
        : items.filter((item) => {
            const normalizedCategory = item.category.toLowerCase();
            const normalizedTerm = item.term.toLowerCase();

            if (category.id === "responsible") {
              return normalizedTerm.includes("responsable") || normalizedTerm.includes("garantie");
            }

            if (category.id === "risk") {
              return normalizedCategory.includes("risk") || normalizedTerm.includes("risque");
            }

            if (category.id === "data") {
              return normalizedCategory.includes("data") || normalizedTerm.includes("donnée");
            }

            if (category.id === "analysis") {
              return (
                normalizedCategory.includes("analysis") ||
                normalizedTerm.includes("analyse") ||
                normalizedTerm.includes("confiance")
              );
            }

            if (category.id === "prediction") {
              return (
                normalizedCategory.includes("prediction") ||
                normalizedCategory.includes("market") ||
                normalizedTerm.includes("1x2") ||
                normalizedTerm.includes("btts") ||
                normalizedTerm.includes("over")
              );
            }

            if (category.id === "interpretation") {
              return normalizedCategory.includes("interpretation");
            }

            if (category.id === "model") {
              return normalizedCategory.includes("model") || normalizedTerm.includes("scoring");
            }

            return normalizedCategory.includes(category.id);
          }).length;

    return {
      ...category,
      count,
    };
  });
}

// Cette fonction vérifie si un terme appartient à la catégorie active.
function itemMatchesCategory(item: GlossaryItem, activeCategory: string) {
  const normalizedCategory = item.category.toLowerCase();
  const normalizedTerm = item.term.toLowerCase();

  if (activeCategory === "all") {
    return true;
  }

  if (activeCategory === "responsible") {
    return normalizedTerm.includes("responsable") || normalizedTerm.includes("garantie");
  }

  if (activeCategory === "risk") {
    return normalizedCategory.includes("risk") || normalizedTerm.includes("risque");
  }

  if (activeCategory === "data") {
    return normalizedCategory.includes("data") || normalizedTerm.includes("donnée");
  }

  if (activeCategory === "analysis") {
    return (
      normalizedCategory.includes("analysis") ||
      normalizedTerm.includes("analyse") ||
      normalizedTerm.includes("confiance")
    );
  }

  if (activeCategory === "prediction") {
    return (
      normalizedCategory.includes("prediction") ||
      normalizedCategory.includes("market") ||
      normalizedTerm.includes("1x2") ||
      normalizedTerm.includes("btts") ||
      normalizedTerm.includes("over")
    );
  }

  if (activeCategory === "interpretation") {
    return normalizedCategory.includes("interpretation");
  }

  if (activeCategory === "model") {
    return normalizedCategory.includes("model") || normalizedTerm.includes("scoring");
  }

  return normalizedCategory.includes(activeCategory);
}

// Ce composant structure la maquette Ressources V2 en recherche, catégories, fiche centrale et cadre responsable.
function GlossarySection({ glossary, glossaryStatus }: GlossarySectionProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSlug, setSelectedSlug] = useState("");
  const [activeCategory, setActiveCategory] = useState("all");

  const sortedItems = useMemo(() => sortGlossaryItems(glossary?.items ?? []), [glossary]);

  const visibleSourceItems = useMemo(
    () => sortedItems.filter((item) => !isTechnicalTerm(item)),
    [sortedItems],
  );

  const categories = useMemo(
    () => buildResourceCategories(visibleSourceItems),
    [visibleSourceItems],
  );

  const filteredItems = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();

    return visibleSourceItems.filter((item) => {
      const searchableContent = `${item.term} ${item.category} ${item.definition}`.toLowerCase();
      const matchesSearch = normalizedSearch ? searchableContent.includes(normalizedSearch) : true;
      const matchesCategory = itemMatchesCategory(item, activeCategory);

      return matchesSearch && matchesCategory;
    });
  }, [visibleSourceItems, searchTerm, activeCategory]);

  const defaultSelectedItem =
    filteredItems.find((item) => item.term.toLowerCase().includes("1x2")) ??
    filteredItems[0] ??
    visibleSourceItems.find((item) => item.term.toLowerCase().includes("1x2")) ??
    visibleSourceItems[0] ??
    null;

  const selectedItem =
    filteredItems.find((item) => item.slug === selectedSlug) ??
    visibleSourceItems.find((item) => item.slug === selectedSlug) ??
    defaultSelectedItem;

  const popularItems = getPopularItems(visibleSourceItems);

  return (
    <div className="rb-resources-v2-body">
      <div className="rb-resources-v2-toolbar">
        <label className="rb-resources-v2-search" htmlFor="rb-resource-search">
          <Search size={18} strokeWidth={1.8} aria-hidden="true" />
          <input
            id="rb-resource-search"
            type="search"
            value={searchTerm}
            placeholder="Rechercher un terme, un concept..."
            onChange={(event) => {
              setSearchTerm(event.target.value);
              setSelectedSlug("");
            }}
          />
        </label>

        <div className="rb-resources-v2-filter-row" aria-label="Filtrer les ressources">
          {["all", "prediction", "analysis", "risk", "data", "responsible"].map((categoryId) => {
            const category = categories.find((item) => item.id === categoryId);
            const label = categoryId === "all" ? "Tous" : category?.label ?? categoryId;

            return (
              <button
                key={categoryId}
                type="button"
                className={
                  activeCategory === categoryId
                    ? "rb-resources-v2-filter rb-resources-v2-filter--active"
                    : "rb-resources-v2-filter"
                }
                onClick={() => {
                  setActiveCategory(categoryId);
                  setSelectedSlug("");
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {visibleSourceItems.length > 0 ? (
        <div className="rb-resources-v2-grid">
          <aside className="rb-resources-v2-categories" aria-label="Catégories du glossaire">
            <p className="rb-resources-v2-panel-label">Catégories</p>

            <div className="rb-resources-v2-category-list">
              {categories.map((category) => {
                const Icon = CATEGORY_ICONS[category.id] ?? category.icon;
                const isActive = activeCategory === category.id;

                return (
                  <button
                    key={category.id}
                    type="button"
                    className={
                      isActive
                        ? "rb-resources-v2-category rb-resources-v2-category--active"
                        : "rb-resources-v2-category"
                    }
                    onClick={() => {
                      setActiveCategory(category.id);
                      setSelectedSlug("");
                    }}
                  >
                    <span className="rb-resources-v2-category__icon">
                      <Icon size={15} strokeWidth={1.9} aria-hidden="true" />
                    </span>

                    <strong>{category.label}</strong>
                    <span className="rb-resources-v2-category__count">{category.count}</span>
                  </button>
                );
              })}
            </div>
          </aside>

          {selectedItem ? (
            <article className="rb-resources-v2-detail">
              <div className="rb-resources-v2-detail__top">
                <span className="rb-resources-v2-detail__marker">
                  {getTermMarker(selectedItem.term)}
                </span>

                <div>
                  <h3>{selectedItem.term}</h3>
                  <p>{formatCategory(selectedItem.category)}</p>
                </div>

                <span className="rb-resources-v2-featured">
                  <Sparkles size={13} strokeWidth={1.8} aria-hidden="true" />
                  Le plus consulté
                </span>
              </div>

              <div className="rb-resources-v2-definition">
                <h4>
                  <BookOpen size={15} strokeWidth={1.9} aria-hidden="true" />
                  Définition
                </h4>
                <p>{getResponsibleDefinition(selectedItem.definition)}</p>
              </div>

              <div className="rb-resources-v2-chips">
                <span>
                  <Eye size={15} strokeWidth={1.8} aria-hidden="true" />
                  Lecture analytique
                </span>
                <span>
                  <ShieldCheck size={15} strokeWidth={1.8} aria-hidden="true" />
                  Interprétation prudente
                </span>
                <span>
                  <Info size={15} strokeWidth={1.8} aria-hidden="true" />
                  Aucune garantie
                </span>
              </div>

              <div className="rb-resources-v2-example">
                <h4>Exemple d’utilisation dans RubyBets</h4>
                <p>{getUsageSentence(selectedItem)}</p>

                <div className="rb-resources-v2-example-card">
                  <div>
                    <span>Exemple</span>
                    <strong>{selectedItem.term}</strong>
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

                <p className="rb-resources-v2-note">
                  <Info size={16} strokeWidth={1.8} aria-hidden="true" />
                  Cette définition aide à comprendre une analyse. Elle ne constitue pas une promesse
                  de résultat sportif et ne permet aucun pari réel.
                </p>
              </div>
            </article>
          ) : (
            <div className="rb-resources-v2-empty">
              <h3>Aucun terme trouvé</h3>
              <p>Aucun terme ne correspond à la recherche actuelle.</p>
            </div>
          )}

          <aside className="rb-resources-v2-side" aria-label="Informations complémentaires">
            <article className="rb-resources-v2-side-card">
              <h3>
                <CircleHelp size={16} strokeWidth={1.9} aria-hidden="true" />
                Pourquoi cette ressource ?
              </h3>
              <p>
                Notre objectif est de rendre l’analyse sportive accessible à tous. Ce centre de
                ressources vous aide à comprendre les indicateurs et concepts utilisés dans
                RubyBets.
              </p>
            </article>

            <article className="rb-resources-v2-side-card">
              <h3>
                <TrendingUp size={16} strokeWidth={1.9} aria-hidden="true" />
                Termes les plus consultés
              </h3>

              <div className="rb-resources-v2-popular-list">
                {popularItems.map((item, index) => (
                  <button
                    key={item.slug}
                    type="button"
                    onClick={() => {
                      setSelectedSlug(item.slug);
                      setActiveCategory("all");
                    }}
                  >
                    <span>{index + 1}</span>
                    <strong>{item.term}</strong>
                  </button>
                ))}
              </div>
            </article>

            <article className="rb-resources-v2-side-card rb-resources-v2-side-card--responsible">
              <h3>
                <ShieldCheck size={16} strokeWidth={1.9} aria-hidden="true" />
                Cadre responsable
              </h3>
              <p>
                {glossaryStatus}. RubyBets est une aide à la décision avant-match : aucun pari
                réel, aucune promesse de résultat sportif.
              </p>
            </article>
          </aside>
        </div>
      ) : (
        <div className="rb-resources-v2-empty">
          <h3>Aucun terme disponible pour le moment</h3>
          <p>Le glossaire sera affiché dès que les définitions seront disponibles.</p>
        </div>
      )}

      <p className="rb-resources-v2-footer-note">
        <Info size={16} strokeWidth={1.8} aria-hidden="true" />
        <strong>RubyBets ne remplace ni votre jugement ni votre responsabilité.</strong>
        <span>Vous restez seul décisionnaire de vos choix.</span>
      </p>
    </div>
  );
}

export default GlossarySection;

// Schéma de communication du fichier :
// GlossarySection.tsx
// ├── reçoit glossary et glossaryStatus depuis ResourcesScreen.tsx
// ├── utilise GlossaryResponse et GlossaryItem depuis models/rubybets.ts
// ├── gère la recherche, les catégories et le terme sélectionné côté frontend
// ├── affiche le centre de ressources sans modifier l’API ni le backend
// └── est stylisé par App.css avec les classes rb-resources-v2-*