// Ce composant affiche le glossaire RubyBets dans une interface pédagogique compacte et proche de la maquette.

import { useMemo, useState } from "react";
import type { GlossaryItem, GlossaryResponse } from "../models/rubybets";

type GlossarySectionProps = {
  glossary: GlossaryResponse | null;
  glossaryStatus: string;
};

const CATEGORY_LABELS: Record<string, string> = {
  analysis: "Analyse",
  prediction: "Prédiction",
  predictions: "Prédiction",
  interpretation: "Interprétation",
  data: "Donnée",
  model: "Méthode",
  project: "Projet",
  recommendation: "Recommandation",
  risk: "Risque",
  confidence: "Confiance",
  market: "Marché",
  markets: "Marché",
};

const TERM_PRIORITY = [
  "1x2",
  "btts",
  "over",
  "under",
  "confiance",
  "risque",
  "xg",
  "forme",
  "value",
  "cote",
  "modèle",
  "pressing",
  "clean",
];

// Cette fonction transforme une catégorie technique en libellé lisible.
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

// Cette fonction reformule les expressions sensibles pour garder un cadre responsable.
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

  if (term.includes("value")) {
    return "Cette notion aide à repérer un écart potentiel entre une lecture analytique et une cote externe.";
  }

  return "Ce terme aide à mieux interpréter les analyses, prédictions et recommandations affichées dans RubyBets.";
}

// Cette fonction rapproche l’ordre d’affichage du glossaire de la maquette sans modifier les données source.
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

// Cette fonction sélectionne les termes les plus utiles à afficher dans la colonne pédagogique.
function getPopularItems(items: GlossaryItem[]) {
  const preferredTerms = ["confiance", "xg", "over", "value", "forme"];

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

// Ce composant structure le glossaire en liste, détail central et colonne d’aide.
function GlossarySection({ glossary, glossaryStatus }: GlossarySectionProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSlug, setSelectedSlug] = useState("");

  const sortedItems = useMemo(() => sortGlossaryItems(glossary?.items ?? []), [glossary]);

  const filteredItems = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();

    if (!normalizedSearch) {
      return sortedItems;
    }

    return sortedItems.filter((item) => {
      const searchableContent = `${item.term} ${item.category} ${item.definition}`.toLowerCase();
      return searchableContent.includes(normalizedSearch);
    });
  }, [sortedItems, searchTerm]);

  const defaultSelectedItem =
    filteredItems.find((item) => item.term.toLowerCase().includes("1x2")) ??
    filteredItems[0] ??
    sortedItems.find((item) => item.term.toLowerCase().includes("1x2")) ??
    sortedItems[0] ??
    null;

  const selectedItem =
    filteredItems.find((item) => item.slug === selectedSlug) ??
    sortedItems.find((item) => item.slug === selectedSlug) ??
    defaultSelectedItem;

  const totalCount = glossary?.count ?? sortedItems.length;
  const popularItems = getPopularItems(sortedItems);

  return (
    <div className="rb-glossary-v2">
      <header className="rb-glossary-v2__header">
        <div className="rb-glossary-v2__title">
          <span className="rb-glossary-v2__title-icon">□</span>

          <div>
            <h2>Glossaire</h2>
            <p>Comprenez les termes clés de l’analyse sportive avant-match.</p>
          </div>
        </div>

        <label className="rb-glossary-v2__search" htmlFor="rb-glossary-search">
          <span>⌕</span>
          <input
            id="rb-glossary-search"
            type="search"
            value={searchTerm}
            placeholder="Rechercher un terme"
            onChange={(event) => setSearchTerm(event.target.value)}
          />
        </label>
      </header>

      {sortedItems.length > 0 ? (
        <div className="rb-glossary-v2__board">
          <aside className="rb-glossary-v2__index" aria-label="Liste des termes du glossaire">
            <div className="rb-glossary-v2__index-header">
              <strong>Tous les termes</strong>
              <span>{filteredItems.length || totalCount}</span>
            </div>

            {filteredItems.length > 0 ? (
              <div className="rb-glossary-v2__list">
                {filteredItems.map((item) => (
                  <button
                    key={item.slug}
                    type="button"
                    className={
                      selectedItem?.slug === item.slug
                        ? "rb-glossary-v2__term rb-glossary-v2__term--active"
                        : "rb-glossary-v2__term"
                    }
                    onClick={() => setSelectedSlug(item.slug)}
                  >
                    <span className="rb-glossary-v2__term-marker">
                      {getTermMarker(item.term)}
                    </span>

                    <span className="rb-glossary-v2__term-content">
                      <strong>{item.term}</strong>
                      <small>{formatCategory(item.category)}</small>
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rb-glossary-v2__mini-empty">
                <strong>Aucun résultat</strong>
                <p>Essaie un autre terme ou vide la recherche.</p>
              </div>
            )}
          </aside>

          {selectedItem ? (
            <article className="rb-glossary-v2__detail">
              <div className="rb-glossary-v2__detail-top">
                <span className="rb-glossary-v2__detail-marker">
                  {getTermMarker(selectedItem.term)}
                </span>

                <div>
                  <h3>{selectedItem.term}</h3>
                  <p>{formatCategory(selectedItem.category)}</p>
                </div>
              </div>

              <div className="rb-glossary-v2__definition">
                <h4>Définition</h4>
                <p>{getResponsibleDefinition(selectedItem.definition)}</p>
              </div>

              <div className="rb-glossary-v2__chips">
                <span>
                  <strong>1</strong>
                  Lecture analytique
                </span>
                <span>
                  <strong>×</strong>
                  Interprétation prudente
                </span>
                <span>
                  <strong>2</strong>
                  Aucune garantie
                </span>
              </div>

              <div className="rb-glossary-v2__example">
                <h4>Exemple d’utilisation dans RubyBets</h4>
                <p>{getUsageSentence(selectedItem)}</p>

                <div className="rb-glossary-v2__example-card">
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

                <p className="rb-glossary-v2__note">
                  Cette définition aide à comprendre une analyse. Elle ne constitue pas
                  une promesse de résultat sportif et ne permet aucun pari réel.
                </p>
              </div>
            </article>
          ) : (
            <div className="rb-glossary-v2__empty-state">
              <h3>Aucun terme trouvé</h3>
              <p>Aucun terme ne correspond à la recherche actuelle.</p>
            </div>
          )}

          <aside className="rb-glossary-v2__help" aria-label="Aide pédagogique du glossaire">
            <article className="rb-glossary-v2__help-card">
              <h3>Pourquoi un glossaire ?</h3>
              <p>
                Notre objectif est de rendre l’analyse sportive accessible à tous.
                Ce glossaire vous aide à comprendre les indicateurs et concepts utilisés
                dans RubyBets.
              </p>
            </article>

            <article className="rb-glossary-v2__help-card">
              <h3>Termes les plus consultés</h3>

              <div className="rb-glossary-v2__popular-list">
                {popularItems.map((item, index) => (
                  <button
                    key={item.slug}
                    type="button"
                    onClick={() => setSelectedSlug(item.slug)}
                  >
                    <span>{index + 1}</span>
                    <strong>{item.term}</strong>
                  </button>
                ))}
              </div>
            </article>

            <article className="rb-glossary-v2__help-card">
              <h3>Cadre responsable</h3>
              <p>
                {glossaryStatus}. RubyBets est une aide à la décision avant-match :
                aucun pari réel, aucune promesse de résultat sportif.
              </p>
            </article>
          </aside>
        </div>
      ) : (
        <div className="rb-glossary-v2__empty-state">
          <h3>Aucun terme disponible pour le moment</h3>
          <p>Le glossaire sera affiché dès que les définitions seront disponibles.</p>
        </div>
      )}

      <p className="rb-glossary-v2__footer-note">
        Outil d’aide à la décision. Les analyses proposées ne constituent pas un conseil
        en investissement ou un pari.
      </p>
    </div>
  );
}

export default GlossarySection;

// Schéma de communication du fichier :
// GlossarySection.tsx
// ├── reçoit glossary et glossaryStatus depuis GlossaryScreen.tsx
// ├── utilise GlossaryResponse et GlossaryItem depuis models/rubybets.ts
// ├── affiche les termes reçus sans modifier les appels API
// └── est stylisé par App.css avec les classes rb-glossary-v2-*
