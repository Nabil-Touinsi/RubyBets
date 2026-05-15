// Ce composant affiche les limites et bonnes pratiques responsables de RubyBets sous forme de cartes pédagogiques.

import type { ResponsibleInfoResponse } from "../models/rubybets";

type ResponsibleInfoSectionProps = {
  responsibleInfo: ResponsibleInfoResponse | null;
  responsibleInfoStatus: string;
};

type ResponsibleCard = {
  number: string;
  icon: string;
  variant: "teal" | "warning";
  title: string;
  intro: string;
  items: string[];
};

// Cette fonction prépare des libellés stables à partir des informations responsables disponibles.
function getResponsibleFacts(responsibleInfo: ResponsibleInfoResponse | null) {
  const summary = responsibleInfo?.summary;

  return {
    realBettingDisabled: summary ? !summary.real_betting_enabled : true,
    liveAnalysisDisabled: summary ? !summary.live_analysis_enabled : true,
    usesRealData: summary?.uses_real_data ?? true,
    guaranteesDisabled: summary ? !summary.guarantees_result : true,
    messageCount: responsibleInfo?.count ?? 0,
  };
}

// Cette fonction construit les 4 cartes pédagogiques de l’écran responsable.
function getResponsibleCards(
  responsibleInfo: ResponsibleInfoResponse | null,
  responsibleInfoStatus: string,
): ResponsibleCard[] {
  const facts = getResponsibleFacts(responsibleInfo);

  return [
    {
      number: "1.",
      icon: "✦",
      variant: "teal",
      title: "Positionnement de RubyBets",
      intro:
        "RubyBets est une aide à la décision avant-match basée sur l’analyse de données et des modèles statistiques.",
      items: [
        facts.realBettingDisabled
          ? "Nous ne sommes pas un opérateur de paris."
          : "Le pari réel ne fait pas partie du cadre responsable RubyBets.",
        "Nous ne prenons aucun pari en votre nom.",
        facts.guaranteesDisabled
          ? "Nous ne garantissons aucun résultat."
          : "Aucun résultat sportif ne doit être présenté comme garanti.",
        "Notre mission : vous fournir des insights pour mieux décider.",
      ],
    },
    {
      number: "2.",
      icon: "△",
      variant: "warning",
      title: "Limites de l’analyse",
      intro:
        "Le football reste un sport imprévisible. Aucune analyse ne peut éliminer totalement l’incertitude.",
      items: [
        "Les données peuvent être incomplètes ou inexactes.",
        "Les modèles reposent sur des probabilités, pas sur des certitudes.",
        "Les recommandations ne sont pas des garanties de gain.",
        "Des événements imprévisibles peuvent influencer le résultat.",
      ],
    },
    {
      number: "3.",
      icon: "○",
      variant: "teal",
      title: "Bonnes pratiques d’utilisation",
      intro:
        "Pour une expérience saine et responsable, adoptez les bonnes pratiques suivantes.",
      items: [
        "Utilisez RubyBets comme un outil d’aide, pas comme une certitude.",
        "Fixez vos propres limites de budget et de temps.",
        "Ne misez jamais plus que ce que vous pouvez vous permettre de perdre.",
        "Évitez de courir après vos pertes.",
        "Faites des pauses régulières et gardez le contrôle de votre pratique.",
      ],
    },
    {
      number: "4.",
      icon: "◎",
      variant: "teal",
      title: "Sources et fiabilité",
      intro:
        "Nos analyses s’appuient sur des données réelles, vérifiées et mises à jour avant chaque match.",
      items: [
        facts.usesRealData
          ? "Données issues de sources fiables et partenaires reconnus."
          : "Les données doivent rester vérifiées avant toute interprétation.",
        `${responsibleInfoStatus}${facts.messageCount ? ` · ${facts.messageCount} messages disponibles.` : "."}`,
        facts.liveAnalysisDisabled
          ? "Analyses réalisées uniquement avant le coup d’envoi."
          : "Le cadre MVP privilégie l’analyse avant-match.",
        "Aucune information en direct n’est prise en compte dans cette V1.",
      ],
    },
  ];
}

// Ce composant rend les cartes responsables sans modifier les données ni les appels API.
function ResponsibleInfoSection({
  responsibleInfo,
  responsibleInfoStatus,
}: ResponsibleInfoSectionProps) {
  const responsibleCards = getResponsibleCards(responsibleInfo, responsibleInfoStatus);

  return (
    <section className="rb-responsible-info--mockup" aria-label="Cadre responsable RubyBets">
      <div className="rb-responsible-card-grid">
        {responsibleCards.map((card) => (
          <article
            key={card.title}
            className={`rb-responsible-card rb-responsible-card--${card.variant}`}
          >
            <div className="rb-responsible-card__icon" aria-hidden="true">
              {card.icon}
            </div>

            <div className="rb-responsible-card__body">
              <header>
                <h3>
                  <span>{card.number}</span> {card.title}
                </h3>
                <p>{card.intro}</p>
              </header>

              <ul>
                {card.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </div>

      <div className="rb-responsible-reminder">
        <span aria-hidden="true">ⓘ</span>
        <p>
          RubyBets ne remplace ni votre jugement ni votre responsabilité. Vous restez seul
          décisionnaire de vos choix.
        </p>
      </div>
    </section>
  );
}

export default ResponsibleInfoSection;

// Schéma de communication du fichier :
// ResponsibleInfoSection.tsx
// ├── reçoit responsibleInfo et responsibleInfoStatus depuis ResponsibleInfoScreen.tsx
// ├── utilise le type ResponsibleInfoResponse depuis models/rubybets.ts
// ├── transforme les données disponibles en cartes pédagogiques responsables
// └── est stylisé par App.css avec les classes rb-responsible-*