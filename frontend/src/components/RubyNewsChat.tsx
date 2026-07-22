// Ce fichier affiche Ruby, l'assistant amovible qui résume les actualités d'un match et répond aux questions de l'utilisateur.

import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import rubyAvatar from "../assets/ruby-avatar.jpg";
import type {
  NewsChatbotRequest,
  NewsChatbotResponse,
  NewsChatbotSource,
} from "../models/rubybets";
import {
  askRubyAboutMatchNews,
  RubyNewsChatApiError,
} from "../services/api";

type RubyNewsChatProps = {
  matchId: number;
  isVisible: boolean;
};

type RubyChatMessage = {
  id: string;
  role: "user" | "ruby";
  text: string;
  createdAt: string;
  response: NewsChatbotResponse | null;
};

const RUBY_REQUEST_TIMEOUT_MS = 6 * 60 * 1000;

// Cette fonction crée un identifiant local simple pour l'historique de la session.
function createMessageId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Cette fonction transforme une date en heure courte pour les messages du chat.
function formatChatTime(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "à l'instant";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Cette fonction transforme le statut d'une réponse en formulation simple pour l'utilisateur.
function getResponseStatusLabel(response: NewsChatbotResponse) {
  if (response.status === "unavailable") {
    return "Pas assez d'informations";
  }

  if (response.insufficient_data) {
    return "Informations limitées";
  }

  if (response.status === "partial") {
    return "Résumé disponible avec quelques limites";
  }

  return response.mode === "summary" ? "Résumé prêt" : "Réponse prête";
}

// Cette fonction simplifie le statut d'une source sans exposer le vocabulaire technique du backend.
function getSourceStatusLabel(source: NewsChatbotSource) {
  if (source.content_status === "full") {
    return "Source complète";
  }

  if (source.content_status === "partial") {
    return "Info partielle";
  }

  return "Source limitée";
}

// Cette fonction choisit une classe visuelle cohérente avec le statut simplifié d'une source.
function getSourceStatusClass(source: NewsChatbotSource) {
  return source.content_status === "full"
    ? "rb-ruby-source-status--complete"
    : "rb-ruby-source-status--partial";
}

// Cette fonction transforme les codes [NEWS-xx] en repères visuels sans masquer le texte original.
function renderAnswerWithCitations(text: string): ReactNode[] {
  return text.split(/(\[NEWS-\d{2}\])/g).map((part, index) => {
    if (/^\[NEWS-\d{2}\]$/.test(part)) {
      return (
        <span className="rb-ruby-citation" key={`${part}-${index}`}>
          {part}
        </span>
      );
    }

    return <span key={`answer-${index}`}>{part}</span>;
  });
}

// Cette fonction prépare un message d'erreur simple selon la réponse HTTP ou le problème réseau rencontré.
function getRubyErrorMessage(error: unknown, timedOut: boolean) {
  if (timedOut) {
    return "Ruby a mis trop de temps à répondre. Tu peux relancer la demande.";
  }

  if (error instanceof RubyNewsChatApiError) {
    if (error.status === 400 || error.status === 422) {
      return "La demande n'est pas valide. Vérifie ta question puis réessaie.";
    }

    if (error.status === 404) {
      return "Ce match n'est pas disponible pour Ruby.";
    }

    if (error.status === 429) {
      return "Ruby reçoit beaucoup de demandes. Réessaie dans quelques instants.";
    }

    if (error.status === 502 || error.status === 503) {
      return "Ruby n'a pas pu terminer sa réponse. Tu peux relancer.";
    }

    return error.message || "Ruby n'a pas pu terminer la demande.";
  }

  if (error instanceof TypeError) {
    return "Le backend RubyBets ne répond pas actuellement.";
  }

  return "Une erreur inattendue a interrompu Ruby. Tu peux relancer.";
}

// Ce composant affiche l'avatar de Ruby dans le lanceur et dans les messages du chat.
function RubyAvatar({ size = "medium" }: { size?: "small" | "medium" | "large" }) {
  return (
    <img
      className={`rb-ruby-avatar rb-ruby-avatar--${size}`}
      src={rubyAvatar}
      alt="Ruby, l'assistant match"
    />
  );
}

// Ce composant affiche un message utilisateur ou une réponse de Ruby dans l'historique local.
function RubyMessage({ message }: { message: RubyChatMessage }) {
  return (
    <div
      className={`rb-ruby-message rb-ruby-message--${message.role}`}
      role="listitem"
    >
      {message.role === "ruby" ? <RubyAvatar size="small" /> : null}
      <div className="rb-ruby-message-content">
        <div className="rb-ruby-message-meta">
          <strong>{message.role === "ruby" ? "Ruby" : "Vous"}</strong>
          <span>{formatChatTime(message.createdAt)}</span>
        </div>
        <p>{renderAnswerWithCitations(message.text)}</p>
      </div>
    </div>
  );
}

// Ce composant affiche les sources réellement citées dans la dernière réponse de Ruby.
function RubySources({ response }: { response: NewsChatbotResponse | null }) {
  const sources = response?.sources ?? [];

  if (!sources.length) {
    return null;
  }

  return (
    <div className="rb-ruby-section rb-ruby-sources" role="region" aria-label="Sources citées">
      <div className="rb-ruby-section-header">
        <h4>Sources citées</h4>
        <span>{sources.length} source{sources.length > 1 ? "s" : ""}</span>
      </div>

      <div className="rb-ruby-source-list" role="list">
        {sources.map((source) => (
          <div className="rb-ruby-source" key={source.article_id} role="listitem">
            <div>
              <strong>{source.article_id}</strong>
              <p>{source.title}</p>
              {source.source_name ? <small>{source.source_name}</small> : null}
            </div>
            <div className="rb-ruby-source-actions">
              <span
                className={`rb-ruby-source-status ${getSourceStatusClass(source)}`}
              >
                {getSourceStatusLabel(source)}
              </span>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Ouvrir ↗
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Ce composant présente un état court lorsque Ruby ne dispose d'aucune réponse sourcée.
function RubyUnavailableNotice({ response }: { response: NewsChatbotResponse | null }) {
  if (!response || (response.status !== "unavailable" && response.sources.length)) {
    return null;
  }

  return (
    <div className="rb-ruby-unavailable" role="status">
      <strong>Pas assez d'informations fiables</strong>
      <p>{response.answer}</p>
    </div>
  );
}


// Ce composant affiche les limites utiles avec un vocabulaire simple et responsable.
function RubyLimits({ response }: { response: NewsChatbotResponse | null }) {
  const defaultLimits = [
    "Certaines informations peuvent être incomplètes ou manquer de contexte.",
    "Les nouvelles importantes peuvent apparaître après le résumé.",
    "Ruby utilise uniquement les actualités déjà fournies par RubyBets.",
  ];
  const limits = response?.limitations?.length
    ? [...response.limitations, defaultLimits[2]].slice(0, 4)
    : defaultLimits;

  return (
    <div className="rb-ruby-section rb-ruby-limits" role="region" aria-label="Quelques limites">
      <h4>Quelques limites</h4>
      <div className="rb-ruby-limit-list" role="list">
        {limits.map((limit) => (
          <div className="rb-ruby-limit-item" role="listitem" key={limit}>
            {limit}
          </div>
        ))}
      </div>
    </div>
  );
}

// Ce composant affiche les informations simples de la dernière lecture réalisée par Ruby.
function RubySummaryMeta({ response }: { response: NewsChatbotResponse }) {
  return (
    <div className="rb-ruby-summary-meta">
      <span>{response.analyzed_articles_count} article{response.analyzed_articles_count > 1 ? "s" : ""} lu{response.analyzed_articles_count > 1 ? "s" : ""}</span>
      <span>{response.sources.length} source{response.sources.length > 1 ? "s" : ""} citée{response.sources.length > 1 ? "s" : ""}</span>
      {response.cached ? <span>Informations déjà préparées</span> : null}
    </div>
  );
}

// Ce composant affiche Ruby sous forme de bouton rond fermé ou de panneau de discussion ouvert.
function RubyNewsChat({ matchId, isVisible }: RubyNewsChatProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<RubyChatMessage[]>([]);
  const [latestResponse, setLatestResponse] = useState<NewsChatbotResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMode, setLoadingMode] = useState<"summary" | "question" | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const requestAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  // Cet effet permet d'éviter une mise à jour d'état après la fermeture complète de la fiche match.
  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      requestAbortRef.current?.abort();
    };
  }, []);

  // Cette fonction appelle le backend avec un délai adapté au traitement long des actualités.
  async function runRubyRequest(request: NewsChatbotRequest) {
    if (isLoading) {
      return;
    }

    const controller = new AbortController();
    let timedOut = false;
    requestAbortRef.current = controller;
    setIsLoading(true);
    setLoadingMode(request.mode);
    setErrorMessage("");

    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, RUBY_REQUEST_TIMEOUT_MS);

    try {
      const response = await askRubyAboutMatchNews(
        matchId,
        request,
        controller.signal
      );

      if (!mountedRef.current) {
        return;
      }

      const rubyMessage: RubyChatMessage = {
        id: createMessageId(),
        role: "ruby",
        text: response.answer,
        createdAt: response.generated_at,
        response,
      };

      setLatestResponse(response);

      if (response.status !== "unavailable" && response.sources.length > 0) {
        setMessages((currentMessages) => [...currentMessages, rubyMessage]);
      }
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }

      if (error instanceof DOMException && error.name === "AbortError" && !timedOut) {
        return;
      }

      setErrorMessage(getRubyErrorMessage(error, timedOut));
    } finally {
      window.clearTimeout(timeoutId);

      if (mountedRef.current) {
        setIsLoading(false);
        setLoadingMode(null);
      }

      if (requestAbortRef.current === controller) {
        requestAbortRef.current = null;
      }
    }
  }

  // Cette fonction lance la synthèse générale des actualités du match.
  function handleSummaryRequest() {
    void runRubyRequest({ mode: "summary" });
  }

  // Cette fonction valide puis envoie une question libre à Ruby.
  function handleQuestionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuestion = question.trim().replace(/\s+/g, " ");

    if (cleanQuestion.length < 3) {
      setErrorMessage("Écris une question d'au moins 3 caractères.");
      return;
    }

    if (cleanQuestion.length > 500) {
      setErrorMessage("Ta question doit rester sous 500 caractères.");
      return;
    }

    const userMessage: RubyChatMessage = {
      id: createMessageId(),
      role: "user",
      text: cleanQuestion,
      createdAt: new Date().toISOString(),
      response: null,
    };

    setMessages((currentMessages) => [...currentMessages, userMessage]);
    setQuestion("");
    void runRubyRequest({ mode: "question", question: cleanQuestion });
  }

  // Cette fonction efface uniquement la conversation locale du match en cours.
  function handleResetConversation() {
    if (isLoading) {
      return;
    }

    setQuestion("");
    setMessages([]);
    setLatestResponse(null);
    setErrorMessage("");
  }

  if (!isVisible) {
    return null;
  }

  if (typeof document === "undefined") {
    return null;
  }

  const rubyContent = !isOpen ? (
    <div className="rb-ruby-launcher-wrap">
      <button
        className="rb-ruby-launcher"
        type="button"
        onClick={() => setIsOpen(true)}
        title="Ouvrir Ruby"
        aria-label="Ouvrir Ruby, l'assistant match"
      >
        <RubyAvatar size="large" />
        <span className="rb-ruby-launcher-dot" aria-hidden="true" />
      </button>
    </div>
  ) : (
    <aside
      className="rb-ruby-panel"
      role="dialog"
      aria-modal="false"
      aria-label="Discussion avec Ruby"
    >
      <header className="rb-ruby-header">
        <div className="rb-ruby-title">
          <RubyAvatar size="medium" />
          <div>
            <h3>Ruby</h3>
            <p>Assistant match</p>
          </div>
        </div>
        <button
          className="rb-ruby-minimize"
          type="button"
          onClick={() => setIsOpen(false)}
          aria-label="Réduire Ruby"
          title="Réduire Ruby"
        >
          —
        </button>
      </header>

      <div className="rb-ruby-body">
        <div className="rb-ruby-intro">
          <RubyAvatar size="small" />
          <div>
            <strong>Salut ! Je suis Ruby 🐶</strong>
            <p>
              Je résume l'actualité du match et réponds simplement à tes questions.
            </p>
            <button
              type="button"
              onClick={handleSummaryRequest}
              disabled={isLoading}
            >
              {isLoading && loadingMode === "summary"
                ? "Résumé en cours…"
                : "Lancer le résumé"}
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="rb-ruby-loading" aria-live="polite">
            <span className="rb-ruby-spinner" aria-hidden="true" />
            <div>
              <strong>Ruby lit les actualités du match.</strong>
              <p>
                Cela peut prendre quelques minutes. Tu peux continuer à consulter la fiche.
              </p>
            </div>
          </div>
        ) : null}

        {errorMessage ? (
          <div className="rb-ruby-error" role="alert">
            <strong>Ruby n'a pas terminé.</strong>
            <p>{errorMessage}</p>
          </div>
        ) : null}

        {latestResponse ? (
          <div className="rb-ruby-status-card">
            <div>
              <span>Dernière lecture</span>
              <strong>{getResponseStatusLabel(latestResponse)}</strong>
            </div>
            <RubySummaryMeta response={latestResponse} />
          </div>
        ) : null}

        <RubyUnavailableNotice response={latestResponse} />

        <div className="rb-ruby-history" aria-live="polite" role="list">
          {messages.length ? (
            messages.map((message) => (
              <RubyMessage key={message.id} message={message} />
            ))
          ) : (
            <div className="rb-ruby-empty-history">
              <span>✦</span>
              <p>
                Lance le résumé ou pose une question pour commencer la discussion.
              </p>
            </div>
          )}
        </div>

        <RubySources response={latestResponse} />
        <RubyLimits response={latestResponse} />
      </div>

      <footer className="rb-ruby-footer">
        <div className="rb-ruby-footer-actions">
          <button
            type="button"
            onClick={handleResetConversation}
            disabled={isLoading || (!messages.length && !latestResponse)}
          >
            Réinitialiser
          </button>
          <button type="button" onClick={() => setIsOpen(false)}>
            Fermer la discussion
          </button>
        </div>

        <form className="rb-ruby-question-form" onSubmit={handleQuestionSubmit}>
          <label className="rb-sr-only" htmlFor={`ruby-question-${matchId}`}>
            Poser une question à Ruby
          </label>
          <textarea
            id={`ruby-question-${matchId}`}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Pose ta question sur le match…"
            maxLength={500}
            rows={2}
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || question.trim().length < 3}
            aria-label="Envoyer la question à Ruby"
          >
            ➤
          </button>
        </form>
      </footer>
    </aside>
  );

  return createPortal(
    <div className="rb-ruby-portal" data-ruby-portal="true">
      {rubyContent}
    </div>,
    document.body
  );
}

export default RubyNewsChat;

// Schéma de communication :
// MatchDetailsScreen.tsx -> RubyNewsChat.tsx
//     ↓ utilise ruby-avatar.jpg et les types NewsChatbot* de models/rubybets.ts
//     ↓ appelle askRubyAboutMatchNews() dans services/api.ts
//     ↓ POST /api/matches/{match_id}/news-chat -> backend RubyBets
//     ↓ createPortal() rend le tiroir dans document.body pour l’isoler du CSS de la fiche match
