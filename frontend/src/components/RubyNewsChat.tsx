// Ce fichier affiche Ruby comme assistant intégré à la sidebar et ouvre une discussion complète à la demande.
// Il résume uniquement les actualités sélectionnées par RubyBets et conserve des états accessibles et responsables.

import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  BookOpenCheck,
  ExternalLink,
  FileCheck2,
  MessageCircleMore,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import rubyAvatar from "../assets/ruby-avatar-context.png";
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
  availableArticlesCount?: number;
  newsContextStatus?: string;
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
    return "à l’instant";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Cette fonction transforme le statut d'une réponse en formulation simple pour l'utilisateur.
function getResponseStatusLabel(response: NewsChatbotResponse) {
  if (response.status === "unavailable") {
    return "Informations insuffisantes";
  }

  if (response.insufficient_data || response.status === "partial") {
    return "Synthèse disponible avec réserves";
  }

  return response.mode === "summary" ? "Synthèse disponible" : "Réponse disponible";
}

// Cette fonction simplifie le statut d'une source sans exposer le vocabulaire technique du backend.
function getSourceStatusLabel(source: NewsChatbotSource) {
  if (source.content_status === "full") {
    return "Article lu";
  }

  if (source.content_status === "partial") {
    return "Extrait utilisé";
  }

  return "Source limitée";
}

// Cette fonction transforme les codes de citation en repères visuels lisibles.
function renderAnswerWithCitations(text: string): ReactNode[] {
  return text.split(/(\[NEWS-\d{2}\])/g).map((part, index) => {
    if (/^\[NEWS-\d{2}\]$/.test(part)) {
      return (
        <span className="rb-detail-context-ruby-citation" key={`${part}-${index}`}>
          {part.replace("NEWS-", "S")}
        </span>
      );
    }

    return <span key={`answer-${index}`}>{part}</span>;
  });
}

// Cette fonction prépare un message d'erreur public selon le problème rencontré.
function getRubyErrorMessage(error: unknown, timedOut: boolean) {
  if (timedOut) {
    return "Ruby a mis trop de temps à répondre. La demande peut être relancée.";
  }

  if (error instanceof RubyNewsChatApiError) {
    if (error.status === 400 || error.status === 422) {
      return "La demande n’est pas valide. Vérifie la question puis réessaie.";
    }

    if (error.status === 404) {
      return "Ce match n’est pas disponible pour Ruby.";
    }

    if (error.status === 429) {
      return "Ruby reçoit beaucoup de demandes. Réessaie dans quelques instants.";
    }

    if (error.status === 502 || error.status === 503) {
      return "Ruby n’a pas pu terminer l’analyse. La demande peut être relancée.";
    }

    return error.message || "Ruby n’a pas pu terminer la demande.";
  }

  if (error instanceof TypeError) {
    return "Le backend RubyBets ne répond pas actuellement.";
  }

  return "Une erreur inattendue a interrompu Ruby.";
}

// Ce composant affiche l'avatar validé de Ruby dans la sidebar et la discussion.
function RubyAvatar({ size = "medium" }: { size?: "small" | "medium" | "large" }) {
  return (
    <img
      className={`rb-detail-context-ruby-avatar rb-detail-context-ruby-avatar--${size}`}
      src={rubyAvatar}
      alt="Ruby, l’assistant d’analyse"
    />
  );
}

// Ce composant affiche un message utilisateur ou une réponse de Ruby.
function RubyMessage({ message }: { message: RubyChatMessage }) {
  return (
    <article
      className={`rb-detail-context-ruby-message rb-detail-context-ruby-message--${message.role}`}
      role="listitem"
    >
      {message.role === "ruby" ? <RubyAvatar size="small" /> : null}
      <div>
        <header>
          <strong>{message.role === "ruby" ? "Ruby" : "Vous"}</strong>
          <span>{formatChatTime(message.createdAt)}</span>
        </header>
        <p>{renderAnswerWithCitations(message.text)}</p>
      </div>
    </article>
  );
}

// Ce composant affiche les sources réellement citées dans la dernière réponse.
function RubySources({ response }: { response: NewsChatbotResponse | null }) {
  const sources = response?.sources ?? [];

  if (!sources.length) {
    return null;
  }

  return (
    <section className="rb-detail-context-ruby-dialog-section" aria-labelledby="ruby-sources-title">
      <div className="rb-detail-context-ruby-dialog-section-heading">
        <h4 id="ruby-sources-title">Sources citées</h4>
        <span>{sources.length}</span>
      </div>

      <div className="rb-detail-context-ruby-source-list" role="list">
        {sources.map((source) => (
          <article className="rb-detail-context-ruby-source" key={source.article_id} role="listitem">
            <div>
              <strong>{source.title}</strong>
              <span>{source.source_name || "Source publique"}</span>
              <small>{getSourceStatusLabel(source)}</small>
            </div>
            <a href={source.url} target="_blank" rel="noopener noreferrer" aria-label={`Ouvrir la source ${source.title}`}>
              <ExternalLink size={15} strokeWidth={1.8} aria-hidden="true" />
            </a>
          </article>
        ))}
      </div>
    </section>
  );
}

// Ce composant affiche les limites utiles de la dernière lecture.
function RubyLimits({ response }: { response: NewsChatbotResponse | null }) {
  const defaultLimits = [
    "Certaines informations peuvent être incomplètes ou évoluer avant le match.",
    "Ruby s’appuie uniquement sur les articles publics sélectionnés par RubyBets.",
    "Cette synthèse ne garantit aucun résultat sportif.",
  ];
  const limits = response?.limitations?.length
    ? [...response.limitations, defaultLimits[2]].slice(0, 4)
    : defaultLimits;

  return (
    <section className="rb-detail-context-ruby-dialog-section" aria-labelledby="ruby-limits-title">
      <div className="rb-detail-context-ruby-dialog-section-heading">
        <h4 id="ruby-limits-title">Limites de lecture</h4>
      </div>
      <ul className="rb-detail-context-ruby-limit-list">
        {limits.map((limit) => (
          <li key={limit}>{limit}</li>
        ))}
      </ul>
    </section>
  );
}

// Ce composant affiche les indicateurs compacts de la sidebar Ruby.
function RubyMetrics({
  response,
  availableArticlesCount,
  canAnalyzeNews,
}: {
  response: NewsChatbotResponse | null;
  availableArticlesCount: number;
  canAnalyzeNews: boolean;
}) {
  const metrics = [
    {
      icon: FileCheck2,
      label: "Articles vérifiés",
      value: response?.analyzed_articles_count ?? availableArticlesCount,
    },
    {
      icon: BookOpenCheck,
      label: "Sources citées",
      value: response?.sources.length ?? 0,
    },
    {
      icon: ShieldCheck,
      label: "Contexte objectif",
      value: response ? "Oui" : canAnalyzeNews ? "Prêt" : "En attente",
    },
  ];

  return (
    <div className="rb-detail-context-ruby-metrics">
      {metrics.map((metric) => {
        const MetricIcon = metric.icon;
        return (
          <div key={metric.label}>
            <MetricIcon size={17} strokeWidth={1.7} aria-hidden="true" />
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        );
      })}
    </div>
  );
}

// Ce composant affiche Ruby dans la sidebar et gère la discussion complète en portail.
function RubyNewsChat({
  matchId,
  isVisible,
  availableArticlesCount = 0,
  newsContextStatus = "idle",
}: RubyNewsChatProps) {
  const [isConversationOpen, setIsConversationOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<RubyChatMessage[]>([]);
  const [latestResponse, setLatestResponse] = useState<NewsChatbotResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMode, setLoadingMode] = useState<"summary" | "question" | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const requestAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const openConversationButtonRef = useRef<HTMLButtonElement | null>(null);
  const closeConversationButtonRef = useRef<HTMLButtonElement | null>(null);
  const questionInputRef = useRef<HTMLTextAreaElement | null>(null);
  const canAnalyzeNews =
    availableArticlesCount > 0 &&
    ["available", "partial", "success"].includes(newsContextStatus);
  const canUseRuby = canAnalyzeNews || Boolean(latestResponse);

  // Cet effet annule toute requête lorsque la fiche est démontée.
  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      requestAbortRef.current?.abort();
    };
  }, []);

  // Cet effet interrompt Ruby lorsque l'utilisateur quitte l'onglet Contexte.
  useEffect(() => {
    if (!isVisible) {
      requestAbortRef.current?.abort();
      setIsConversationOpen(false);
    }
  }, [isVisible]);

  // Cet effet gère la touche Échap et le focus du tiroir de discussion.
  useEffect(() => {
    if (!isConversationOpen) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.setTimeout(() => closeConversationButtonRef.current?.focus(), 0);

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsConversationOpen(false);
        window.setTimeout(() => openConversationButtonRef.current?.focus(), 0);
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isConversationOpen]);

  // Cette fonction appelle le backend avec un délai adapté au traitement des actualités.
  async function runRubyRequest(
    request: NewsChatbotRequest,
    pendingUserMessageId?: string
  ) {
    if (isLoading) {
      return;
    }

    if (!canAnalyzeNews) {
      setErrorMessage(
        newsContextStatus === "loading"
          ? "La recherche des actualités doit se terminer avant l’analyse."
          : "Aucune actualité exploitable n’est disponible pour Ruby."
      );
      return;
    }

    const controller = new AbortController();
    let timedOut = false;
    requestAbortRef.current?.abort();
    requestAbortRef.current = controller;
    setIsLoading(true);
    setLoadingMode(request.mode);
    setErrorMessage("");

    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, RUBY_REQUEST_TIMEOUT_MS);

    try {
      const response = await askRubyAboutMatchNews(matchId, request, controller.signal);

      if (!mountedRef.current || controller.signal.aborted) {
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
      setMessages((currentMessages) => [...currentMessages, rubyMessage]);
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }

      if (error instanceof DOMException && error.name === "AbortError" && !timedOut) {
        return;
      }

      if (pendingUserMessageId) {
        setMessages((currentMessages) =>
          currentMessages.filter((message) => message.id !== pendingUserMessageId)
        );
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
      setErrorMessage("Écris une question d’au moins 3 caractères.");
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
    void runRubyRequest(
      { mode: "question", question: cleanQuestion },
      userMessage.id
    );
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

  // Cette fonction ouvre la discussion complète puis place le focus dans son en-tête.
  function handleOpenConversation() {
    setIsConversationOpen(true);
  }

  // Cette fonction ferme la discussion et restitue le focus au bouton d'ouverture.
  function handleCloseConversation() {
    setIsConversationOpen(false);
    window.setTimeout(() => openConversationButtonRef.current?.focus(), 0);
  }

  if (!isVisible) {
    return null;
  }

  const hasResponse = Boolean(latestResponse);
  const contextPending = ["idle", "loading"].includes(newsContextStatus);
  const contextUnavailable = ["error", "empty", "unavailable"].includes(
    newsContextStatus
  );
  const sidebarStatusTitle = isLoading
    ? "Analyse des actualités en cours"
    : errorMessage
      ? "Ruby n’a pas terminé"
      : hasResponse
        ? getResponseStatusLabel(latestResponse as NewsChatbotResponse)
        : contextPending
          ? "Sources en cours de préparation"
          : contextUnavailable
            ? "Aucune source exploitable"
            : "Synthèse non générée";
  const sidebarStatusText = isLoading
    ? "Ruby lit les sources pertinentes. La fiche reste utilisable pendant le traitement."
    : errorMessage
      ? errorMessage
      : latestResponse
        ? latestResponse.answer
        : contextPending
          ? "La synthèse sera disponible après la recherche des actualités du match."
          : contextUnavailable
            ? "Ruby ne peut pas produire de synthèse sans actualité suffisamment pertinente."
            : "Aucune synthèse n’a encore été produite pour ce match.";

  const drawer =
    isConversationOpen && typeof document !== "undefined"
      ? createPortal(
          <div className="rb-detail-context-ruby-dialog-layer">
            <button
              className="rb-detail-context-ruby-dialog-backdrop"
              type="button"
              onClick={handleCloseConversation}
              aria-label="Fermer la discussion Ruby"
            />
            <aside
              className="rb-detail-context-ruby-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby={`ruby-dialog-title-${matchId}`}
            >
              <header className="rb-detail-context-ruby-dialog-header">
                <div>
                  <RubyAvatar size="small" />
                  <div>
                    <p>Assistant d’analyse</p>
                    <h3 id={`ruby-dialog-title-${matchId}`}>Discussion avec Ruby</h3>
                  </div>
                </div>
                <button
                  ref={closeConversationButtonRef}
                  type="button"
                  onClick={handleCloseConversation}
                  aria-label="Fermer la discussion"
                >
                  <X size={20} aria-hidden="true" />
                </button>
              </header>

              <div className="rb-detail-context-ruby-dialog-body">
                {isLoading ? (
                  <div className="rb-detail-context-ruby-dialog-loading" aria-live="polite">
                    <span aria-hidden="true" />
                    <div>
                      <strong>Ruby analyse les sources.</strong>
                      <p>Le traitement peut durer quelques dizaines de secondes.</p>
                    </div>
                  </div>
                ) : null}

                {errorMessage ? (
                  <div className="rb-detail-context-ruby-dialog-error" role="alert">
                    <strong>Analyse interrompue</strong>
                    <p>{errorMessage}</p>
                  </div>
                ) : null}

                <div className="rb-detail-context-ruby-history" role="list" aria-live="polite">
                  {messages.length ? (
                    messages.map((message) => (
                      <RubyMessage key={message.id} message={message} />
                    ))
                  ) : (
                    <div className="rb-detail-context-ruby-empty-history">
                      <Sparkles size={24} strokeWidth={1.6} aria-hidden="true" />
                      <strong>Commence la discussion</strong>
                      <p>Lance la synthèse ou pose une question précise sur le contexte du match.</p>
                    </div>
                  )}
                </div>

                <RubySources response={latestResponse} />
                <RubyLimits response={latestResponse} />
              </div>

              <footer className="rb-detail-context-ruby-dialog-footer">
                <div>
                  <button
                    type="button"
                    onClick={handleResetConversation}
                    disabled={isLoading || (!messages.length && !latestResponse)}
                  >
                    <RotateCcw size={15} aria-hidden="true" />
                    Réinitialiser
                  </button>
                  <span>{question.length}/500</span>
                </div>

                <form onSubmit={handleQuestionSubmit}>
                  <label className="rb-sr-only" htmlFor={`ruby-question-${matchId}`}>
                    Poser une question à Ruby
                  </label>
                  <textarea
                    ref={questionInputRef}
                    id={`ruby-question-${matchId}`}
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="Pose une question sur les actualités du match…"
                    maxLength={500}
                    rows={3}
                    disabled={isLoading || !canUseRuby}
                  />
                  <button
                    type="submit"
                    disabled={isLoading || !canUseRuby || question.trim().length < 3}
                    aria-label="Envoyer la question à Ruby"
                  >
                    <Send size={18} aria-hidden="true" />
                  </button>
                </form>
              </footer>
            </aside>
          </div>,
          document.body
        )
      : null;

  return (
    <>
      <section className="rb-detail-context-ruby-card" aria-labelledby={`ruby-card-title-${matchId}`}>
        <header className="rb-detail-context-ruby-card-header">
          <div>
            <span>Ruby</span>
            <small>Beta</small>
          </div>
          <span className="rb-detail-context-ruby-online">En ligne</span>
        </header>

        <div className="rb-detail-context-ruby-intro">
          <RubyAvatar size="large" />
          <h2 id={`ruby-card-title-${matchId}`}>Votre assistant d’analyse</h2>
          <p>
            Ruby analyse les actualités pertinentes pour fournir une synthèse claire et factuelle du contexte avant-match.
          </p>
        </div>

        <div className={`rb-detail-context-ruby-status${isLoading ? " is-loading" : ""}${errorMessage ? " is-error" : ""}`}>
          <div className="rb-detail-context-ruby-status-title">
            <span aria-hidden="true" />
            <strong>{sidebarStatusTitle}</strong>
          </div>
          <p className={latestResponse ? "rb-detail-context-ruby-status-answer" : ""}>
            {latestResponse ? renderAnswerWithCitations(sidebarStatusText) : sidebarStatusText}
          </p>
          <button
            type="button"
            onClick={handleSummaryRequest}
            disabled={isLoading || !canAnalyzeNews}
          >
            <Sparkles size={17} strokeWidth={1.8} aria-hidden="true" />
            {isLoading && loadingMode === "summary"
              ? "Analyse en cours…"
              : latestResponse
                ? "Actualiser la synthèse"
                : canAnalyzeNews
                  ? "Analyser les actualités"
                  : "En attente des actualités"}
          </button>
          <small>
            {newsContextStatus === "loading"
              ? "Recherche des sources en cours"
              : "Génération généralement comprise entre 30 et 60 secondes"}
          </small>
        </div>

        <RubyMetrics
          response={latestResponse}
          availableArticlesCount={availableArticlesCount}
          canAnalyzeNews={canAnalyzeNews}
        />

        <button
          ref={openConversationButtonRef}
          className="rb-detail-context-ruby-open-dialog"
          type="button"
          onClick={handleOpenConversation}
        >
          <MessageCircleMore size={18} strokeWidth={1.8} aria-hidden="true" />
          Ouvrir la discussion complète
        </button>

        <div className="rb-detail-context-ruby-responsible-note">
          <ShieldCheck size={18} strokeWidth={1.7} aria-hidden="true" />
          <p>
            Les informations proviennent de sources publiques et peuvent être partielles. Ruby n’offre aucune garantie de résultat sportif.
          </p>
        </div>
      </section>

      {drawer}
    </>
  );
}

export default RubyNewsChat;

// Schéma de communication :
// MatchDetailsScreen.tsx -> RubyNewsChat.tsx
// ├── utilise assets/ruby-avatar-context.png validé depuis la maquette Contexte
// ├── appelle askRubyAboutMatchNews() dans services/api.ts
// ├── POST /api/matches/{match_id}/news-chat -> backend RubyBets
// └── utilise uniquement les classes rb-detail-context-ruby-* de styles/MatchDetailsScreen.css
