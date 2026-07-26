// Ce fichier affiche une infobulle pédagogique reliée au glossaire public de RubyBets.

import { useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { BookOpen, Info } from "lucide-react";
import { createPortal } from "react-dom";
import type { GlossaryItem } from "../models/rubybets";
import { getGlossary } from "../services/api";
import "../styles/GlossaryTooltip.css";

type GlossaryTooltipProps = {
  term: string;
  children?: ReactNode;
  detail?: string | null;
  className?: string;
};

type TooltipPosition = {
  top: number;
  left: number;
  placement: "top" | "bottom";
  ready: boolean;
};

let glossaryItemsCache: GlossaryItem[] | null = null;
let glossaryItemsRequest: Promise<GlossaryItem[]> | null = null;

const GLOSSARY_ALIASES: Record<string, string> = {
  "expected goals xg": "buts attendus xg",
  "xg cadre xgot": "buts attendus cadres xgot",
  "expected assists xa": "passes decisives attendues xa",
  "xg subi": "buts attendus subis xg subi",
  "xgot subi": "buts attendus cadres subis xgot subi",
  "moyenne match": "moyenne par match",
  "points obtenus max": "points obtenus maximum",
  "difference buts": "difference de buts",
  couverture: "couverture des donnees",
  "indicateur s": "indicateur",
  "signaux issus des derniers matchs termines": "signaux recents",
};

// Cette fonction normalise un libellé pour retrouver une définition malgré les accents et la ponctuation.
function normalizeGlossaryText(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/['’]/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

// Cette fonction charge le glossaire une seule fois pour toutes les infobulles de l'application.
function loadGlossaryItems() {
  if (glossaryItemsCache) {
    return Promise.resolve(glossaryItemsCache);
  }

  if (!glossaryItemsRequest) {
    glossaryItemsRequest = getGlossary()
      .then((response) => {
        glossaryItemsCache = response.items;
        return response.items;
      })
      .finally(() => {
        glossaryItemsRequest = null;
      });
  }

  return glossaryItemsRequest;
}

// Cette fonction retrouve l'entrée correspondant au libellé visible ou à son alias pédagogique.
function findGlossaryItem(items: GlossaryItem[], term: string) {
  const normalizedTerm = normalizeGlossaryText(term);
  const lookupTerm = GLOSSARY_ALIASES[normalizedTerm] ?? normalizedTerm;

  return (
    items.find((item) => normalizeGlossaryText(item.term) === lookupTerm) ??
    items.find((item) => normalizeGlossaryText(item.slug) === lookupTerm) ??
    null
  );
}

// Cette fonction calcule la position de l'infobulle sans la laisser sortir de l'écran.
function getTooltipPosition(trigger: HTMLElement, panel: HTMLElement): TooltipPosition {
  const triggerRect = trigger.getBoundingClientRect();
  const panelRect = panel.getBoundingClientRect();
  const viewportPadding = 14;
  const gap = 11;
  const availableAbove = triggerRect.top;
  const availableBelow = window.innerHeight - triggerRect.bottom;
  const placement =
    availableAbove >= panelRect.height + gap || availableAbove > availableBelow
      ? "top"
      : "bottom";
  const desiredLeft = triggerRect.left + triggerRect.width / 2 - panelRect.width / 2;
  const maximumLeft = Math.max(viewportPadding, window.innerWidth - panelRect.width - viewportPadding);
  const left = Math.min(Math.max(desiredLeft, viewportPadding), maximumLeft);
  const top =
    placement === "top"
      ? Math.max(viewportPadding, triggerRect.top - panelRect.height - gap)
      : Math.min(
          window.innerHeight - panelRect.height - viewportPadding,
          triggerRect.bottom + gap,
        );

  return { top, left, placement, ready: true };
}

// Ce composant rend un terme interactif et affiche sa définition au survol, au focus ou au toucher.
function GlossaryTooltip({
  term,
  children,
  detail = null,
  className = "",
}: GlossaryTooltipProps) {
  const tooltipId = useId();
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [definition, setDefinition] = useState<GlossaryItem | null>(() =>
    glossaryItemsCache ? findGlossaryItem(glossaryItemsCache, term) : null,
  );
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">(
    glossaryItemsCache ? "ready" : "idle",
  );
  const [position, setPosition] = useState<TooltipPosition>({
    top: 0,
    left: 0,
    placement: "top",
    ready: false,
  });

  useEffect(() => {
    let isCurrent = true;

    if (glossaryItemsCache) {
      setDefinition(findGlossaryItem(glossaryItemsCache, term));
      setLoadState("ready");
      return () => {
        isCurrent = false;
      };
    }

    setLoadState("loading");
    loadGlossaryItems()
      .then((items) => {
        if (!isCurrent) {
          return;
        }

        setDefinition(findGlossaryItem(items, term));
        setLoadState("ready");
      })
      .catch(() => {
        if (isCurrent) {
          setLoadState("error");
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [term]);

  useEffect(() => {
    if (!isOpen) {
      setPosition((current) => ({ ...current, ready: false }));
      return;
    }

    const updatePosition = () => {
      if (!triggerRef.current || !panelRef.current) {
        return;
      }

      setPosition(getTooltipPosition(triggerRef.current, panelRef.current));
    };

    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [isOpen, definition, loadState, detail]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;

      if (
        triggerRef.current?.contains(target) ||
        panelRef.current?.contains(target)
      ) {
        return;
      }

      setIsOpen(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  useEffect(
    () => () => {
      if (openTimerRef.current) {
        clearTimeout(openTimerRef.current);
      }

      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
      }
    },
    [],
  );

  // Cette fonction programme une ouverture légère pour éviter les activations involontaires.
  const scheduleOpen = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
    }

    openTimerRef.current = setTimeout(() => setIsOpen(true), 130);
  };

  // Cette fonction programme la fermeture après la sortie du pointeur.
  const scheduleClose = () => {
    if (openTimerRef.current) {
      clearTimeout(openTimerRef.current);
    }

    closeTimerRef.current = setTimeout(() => setIsOpen(false), 90);
  };

  const panelStyle = {
    top: position.top,
    left: position.left,
  } as CSSProperties;

  const tooltipPanel = isOpen && typeof document !== "undefined"
    ? createPortal(
        <div
          ref={panelRef}
          id={tooltipId}
          role="tooltip"
          className={`rb-glossary-tooltip-panel rb-glossary-tooltip-panel--${position.placement}${
            position.ready ? " is-ready" : ""
          }`}
          style={panelStyle}
        >
          <div className="rb-glossary-tooltip-panel__heading">
            <span aria-hidden="true">
              <BookOpen size={16} strokeWidth={1.9} />
            </span>
            <strong>{definition?.term ?? term}</strong>
          </div>

          {loadState === "loading" ? (
            <p>Chargement de la définition…</p>
          ) : definition ? (
            <p>{definition.definition}</p>
          ) : (
            <p>Définition momentanément indisponible.</p>
          )}

          {detail ? <small>{detail}</small> : null}

          <div className="rb-glossary-tooltip-panel__footer">
            <Info size={13} strokeWidth={1.9} aria-hidden="true" />
            <span>Définition issue du centre de ressources RubyBets</span>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <span
        ref={triggerRef}
        role="button"
        tabIndex={0}
        className={`rb-glossary-tooltip-trigger ${className}`.trim()}
        aria-describedby={isOpen ? tooltipId : undefined}
        aria-expanded={isOpen}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") {
            scheduleOpen();
          }
        }}
        onPointerLeave={(event) => {
          if (event.pointerType === "mouse") {
            scheduleClose();
          }
        }}
        onFocus={scheduleOpen}
        onBlur={scheduleClose}
        onClick={() => setIsOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setIsOpen((current) => !current);
          }
        }}
      >
        {children ?? term}
      </span>
      {tooltipPanel}
    </>
  );
}

export default GlossaryTooltip;

// Schéma de communication du fichier :
// MatchDetailsScreen.tsx
//   └── GlossaryTooltip.tsx
//         ├── appelle services/api.ts pour GET /api/glossary
//         ├── utilise models/rubybets.ts pour typer les définitions
//         └── applique styles/GlossaryTooltip.css
