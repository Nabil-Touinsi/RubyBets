// Ce composant affiche le glossaire pédagogique utilisé dans RubyBets.

import type { GlossaryResponse } from "../models/rubybets";

type GlossarySectionProps = {
  glossary: GlossaryResponse | null;
};

function GlossarySection({ glossary }: GlossarySectionProps) {
  return (
    <section>
      <h2>Glossaire</h2>

      <p>Définitions pédagogiques des principaux termes utilisés dans RubyBets.</p>

      {glossary && glossary.items.length > 0 ? (
        <div>
          <p>Nombre de termes : {glossary.count}</p>

          {glossary.items.map((item) => (
            <article key={item.slug}>
              <h3>{item.term}</h3>
              <p>Catégorie : {item.category}</p>
              <p>{item.definition}</p>
            </article>
          ))}
        </div>
      ) : (
        <p>Aucun terme disponible pour le moment.</p>
      )}
    </section>
  );
}

export default GlossarySection;