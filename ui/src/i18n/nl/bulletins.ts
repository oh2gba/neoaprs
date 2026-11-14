// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { bulletins as source } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Record<keyof typeof source, Message> = {
  "bulletins.section.announcement": "Aankondigingen",
  "bulletins.section.bulletin": "Bulletins",
  "bulletins.section.group": "Groepsberichten",
  "bulletins.section.nws": "Weerdienst",

  "bulletins.empty": "Niets op het bord.",
  "bulletins.about_label": "Over bulletins",
  "bulletins.about1": "Een bulletin is een bericht aan iedereen, te zien op het bord van elk station.",
  "bulletins.about2": "Gebruik het voor de tijden van ronden, voor evenementen en waarschuwingen.",
  "bulletins.delete_title": "Verwijderen (niet meer verzenden)",
  "bulletins.delete_own": "Ons bulletin {slot} verwijderen",
  "bulletins.delete": "Bulletin {slot} van {sender} verwijderen",
  "bulletins.to": "aan",
  "bulletins.ours": "van ons",
  "bulletins.posted": "geplaatst op {time}",
  "bulletins.heard_title": "voor het eerst gehoord op {first}, het laatst op {last}",
  "bulletins.heard": { "=1": "één keer gehoord, {span} geleden", other: "{n} keer gehoord, {span} geleden" },

  "bulletins.post_label": "Bulletin plaatsen",
  "bulletins.kind": "Soort",
  "bulletins.kind.bulletin": "Bulletin",
  "bulletins.kind.announcement": "Aankondiging",
  "bulletins.kind.group": "Groepsbulletin",
  "bulletins.kinds_help_label": "Wat de soorten betekenen",
  "bulletins.kinds_help": "Iedereen ziet een bulletin en niemand bevestigt het. Een groepsbulletin is voor de stations die de groepsnaam volgen.",
  "bulletins.letter": "Letter",
  "bulletins.number": "Nummer",
  "bulletins.group": "Groep",
  "bulletins.group_placeholder": "Naam",
  "bulletins.text": "Tekst",
  "bulletins.slot_tip": "De plek op het bord. Een nieuw bulletin op dezelfde plek vervangt het vorige.",
  "bulletins.group_tip": "De groep waarvoor het bulletin bedoeld is, maximaal {max} letters en cijfers. Stations die de naam volgen, tonen het.",
  "bulletins.text_tip": "Wat er in het bulletin staat. De teller toont hoeveel tekens er nog over zijn.",
  "bulletins.post": "Plaatsen",
} as const;
