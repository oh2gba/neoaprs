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
  "bulletins.kind_name.bulletin": "Bulletin",
  "bulletins.kind_name.announcement": "Aankondiging",
  "bulletins.kind_name.group": "Groepsbulletin",
  "bulletins.sent_for": "Verzonden gedurende",
  "bulletins.group": "Groep",
  "bulletins.group_placeholder": "Naam",
  "bulletins.text": "Tekst",
  "bulletins.tip.hours": { one: "{n} uur", other: "{n} uur" },
  "bulletins.tip.days": { one: "{n} dag", other: "{n} dagen" },
  "bulletins.tip.kinds1":
    "Een bulletin en een aankondiging worden getoond door elk station dat ze hoort: een bulletin voor wat nu telt, een aankondiging voor wat dagen waar blijft.",
  "bulletins.tip.kinds2":
    "Een groepsbulletin is voor één groep; elk station toont het, tenzij de operator andere groepen koos om te tonen.",
  "bulletins.tip.sent_for": "Hoe lang het bericht wordt herhaald, geteld vanaf het eerste pakket.",
  "bulletins.tip.group1":
    "De naam is deel van het adres, zoals in BLN3HAMS, zodat elk station het bulletin hoort en toont, tenzij de operator andere groepen koos om te tonen.",
  "bulletins.tip.group2": "NeoAPRS toont de bulletins van elke groep die het hoort, onder Groepsberichten.",
  "bulletins.tip.text1": "Tot {max} tekens, afdrukbaar, geen van {forbidden}.",
  "bulletins.tip.text_repeat":
    "Het gaat uit in één radiopakket, herhaald voor de tijd die onder Verzonden gedurende is gekozen.",
  "bulletins.post": "Plaatsen",
} as const;
