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
  "bulletins.kind.bulletin": "Bulletin (wordt {n} uur lang verzonden)",
  "bulletins.kind.announcement": {
    one: "Aankondiging (wordt {n} dag lang verzonden)",
    other: "Aankondiging (wordt {n} dagen lang verzonden)",
  },
  "bulletins.kind.group": "Groepsbulletin (aan één groep, wordt {n} uur lang verzonden)",
  "bulletins.letter": "Letter",
  "bulletins.number": "Nummer",
  "bulletins.group": "Groep",
  "bulletins.group_placeholder": "Naam",
  "bulletins.text": "Tekst",
  "bulletins.tip.hours": { one: "{n} uur", other: "{n} uur" },
  "bulletins.tip.days": { one: "{n} dag", other: "{n} dagen" },
  "bulletins.tip.kind1":
    "Een bulletin en een aankondiging worden getoond door elk station dat ze hoort. Een bulletin is voor wat nu telt en wordt {hours} lang verzonden; een aankondiging is voor wat blijft gelden en wordt {days} lang verzonden.",
  "bulletins.tip.kind2":
    "Een groepsbulletin wordt {hours} lang verzonden; elk station toont het, tenzij de operator andere groepen koos om te tonen.",
  "bulletins.tip.id1":
    "Het nummer is de naam van het bericht, bij een aankondiging een letter; een nieuw bericht eronder vervangt het.",
  "bulletins.tip.id2":
    "Opnieuw plaatsen onder hetzelfde nummer of dezelfde letter verzendt de nieuwe tekst vanaf het begin.",
  "bulletins.tip.group1":
    "De naam is deel van het adres, zoals in BLN3HAMS, zodat elk station het bulletin hoort en toont, tenzij de operator andere groepen koos om te tonen.",
  "bulletins.tip.group2": "NeoAPRS toont de bulletins van elke groep die het hoort, onder Groepsberichten.",
  "bulletins.tip.text1": "Tot {max} tekens, afdrukbaar, geen van {forbidden}.",
  "bulletins.tip.text2": "Het gaat uit in één radiopakket, herhaald voor de duur van de soort.",
  "bulletins.post": "Plaatsen",
  "bulletins.replace": "Vervangen",
} as const;
