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
  "bulletins.kind.bulletin": "Tiedote (lähetetään {n} tunnin ajan)",
  "bulletins.kind.announcement": "Ilmoitus (lähetetään {n} päivän ajan)",
  "bulletins.kind.group": "Ryhmätiedote (yhdelle ryhmälle, lähetetään {n} tunnin ajan)",
  "bulletins.letter": "Kirjain",
  "bulletins.number": "Numero",
  "bulletins.group": "Ryhmä",
  "bulletins.group_placeholder": "Nimi",
  "bulletins.text": "Teksti",
  "bulletins.tip.hours": { one: "{n} tunnin", other: "{n} tunnin" },
  "bulletins.tip.days": { one: "{n} päivän", other: "{n} päivän" },
  "bulletins.tip.kind1":
    "Tiedote ja ilmoitus näkyvät jokaisella asemalla, joka ne kuulee. Tiedote on sille, mikä on tärkeää nyt, ja sitä lähetetään {hours} ajan; ilmoitus on sille, mikä pysyy totena, ja sitä lähetetään {days} ajan.",
  "bulletins.tip.kind2": "Ryhmätiedotetta lähetetään {hours} ajan; jokainen asema näyttää sen, ellei sen käyttäjä ole valinnut näytettäväksi muita ryhmiä.",
  "bulletins.tip.id1": "Numero nimeää julkaisun, ilmoituksella kirjain; sen alle tehty uusi julkaisu korvaa sen.",
  "bulletins.tip.id2": "Uusi julkaisu samalla numerolla tai kirjaimella lähettää uuden tekstin alusta.",
  "bulletins.tip.group1":
    "Nimi on osa osoitetta, kuten BLN3HAMS, joten jokainen asema kuulee tiedotteen ja näyttää sen, ellei sen käyttäjä ole valinnut näytettäväksi muita ryhmiä.",
  "bulletins.tip.group2": "NeoAPRS näyttää jokaisen kuulemansa ryhmän tiedotteet kohdassa Ryhmätiedotteet.",
  "bulletins.tip.text1": "Enintään {max} merkkiä, tulostettavia, ei yhtään näistä: {forbidden}.",
  "bulletins.tip.text2": "Se lähtee yhdessä radiopaketissa, jota toistetaan lajin ajan.",
  "bulletins.post": "Julkaise",
  "bulletins.replace": "Korvaa",
} as const;
