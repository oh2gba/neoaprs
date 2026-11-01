// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { bulletins as source } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Record<keyof typeof source, Message> = {
  "bulletins.section.announcement": "Ilmoitukset",
  "bulletins.section.bulletin": "Tiedotteet",
  "bulletins.section.group": "Ryhmätiedotteet",
  "bulletins.section.nws": "Sääpalvelu",

  "bulletins.empty": "Ilmoitustaululla ei ole mitään.",
  "bulletins.about_label": "Tietoa tiedotteista",
  "bulletins.about1": "Tiedote on viesti kaikille, ja se näkyy jokaisen aseman ilmoitustaululla.",
  "bulletins.about2": "Käytä sitä verkkojen ajoille, tapahtumille ja varoituksille.",
  "bulletins.delete_title": "Poista (lopeta lähetys)",
  "bulletins.delete_own": "Poista oma tiedotteemme {slot}",
  "bulletins.delete": "Poista tiedote {slot}, lähettäjä {sender}",
  "bulletins.to": "vastaanottaja",
  "bulletins.ours": "omamme",
  "bulletins.posted": "julkaistu {time}",
  "bulletins.heard_title": "kuultu ensin {first}, viimeksi {last}",
  "bulletins.heard": { "=1": "kuultu kerran, {span} sitten", other: "kuultu {n} kertaa, {span} sitten" },

  "bulletins.post_label": "Julkaise tiedote",
  "bulletins.kind": "Laji",
  "bulletins.kind.bulletin": "Tiedote",
  "bulletins.kind.announcement": "Ilmoitus",
  "bulletins.kind.group": "Ryhmätiedote",
  "bulletins.kinds_help_label": "Mitä lajit ovat",
  "bulletins.kinds_help": "Tiedotteen näkevät kaikki, eikä kukaan kuittaa sitä. Ryhmätiedote on sen nimeä seuraaville asemille.",
  "bulletins.letter": "Kirjain",
  "bulletins.number": "Numero",
  "bulletins.group": "Ryhmä",
  "bulletins.group_placeholder": "Nimi",
  "bulletins.text": "Teksti",
  "bulletins.slot_tip": "Paikka ilmoitustaululla. Uusi julkaisu samaan paikkaan korvaa edellisen.",
  "bulletins.group_tip": "Ryhmä, jolle tiedote on, enintään {max} kirjainta ja numeroa. Nimeä seuraavat asemat näyttävät sen.",
  "bulletins.text_tip": "Tiedotteen sisältö. Laskuri näyttää, montako merkkiä on vielä jäljellä.",
  "bulletins.post": "Julkaise",
} as const;
