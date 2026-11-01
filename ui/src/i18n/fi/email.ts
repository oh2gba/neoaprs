// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { email as source } from "@/i18n/en/email";
import type { Message } from "@/i18n/message";

export const email: Record<keyof typeof source, Message> = {
  "email.compose": "Kirjoita sähköposti",
  "email.to": "Vastaanottaja {address}",
  "email.from": "Lähettäjä {address}",
  "email.checked": "Sähköposti tarkistettu",

  "email.none": "Ei vielä sähköpostia.",
  "email.list": "Sähköposti",
  "email.delete": "Poista: {title}",

  "email.check": "Tarkista sähköposti",
  "email.checking": "Tarkistus on jo käynnissä",
  "email.about": "Tietoa sähköpostista",
  "email.about_gateway": "Sähköposti kulkee Internet-yhdyskäytävän EMAIL-2 kautta, joten viestin tilana voi näkyä {unconfirmed}, vaikka se on perillä.",
  "email.about_check": "{check} pyytää yhdyskäytävältä sinulle säilyttämät viestit (24 tuntia).",

  "email.field.to": "Vastaanottaja",
  "email.field.address": "Sähköpostiosoite",
  "email.field.text": "Teksti",
  "email.to_tip": "Osoite, johon viesti lähetetään. Aiemmin käytetyt osoitteet näkyvät kirjoittaessasi.",
  "email.text_tip": "Viestin sisältö. Laskuri näyttää, montako merkkiä viestissä on vielä jäljellä.",
  "email.used_before": "Aiemmin käytetyt",
  "email.forget": "Unohda {address}",
  "email.send": "Lähetä",

  "email.state.waiting": "Odottaa radiota",
  "email.state.sending": "Lähetetään ({attempt}/{max})",
  "email.state.delivered": "Toimitettu",
  "email.state.rejected": "Hylätty",
  "email.state.cancelled": "Peruttu",
  "email.state.unconfirmed": "Ei vahvistettu",
  "email.not_confirmed": "lähetetty, ei vahvistettu: yhdyskäytävän kuittaus tulee luoksesi vain iGaten kautta, joten viesti on voinut mennä perille",

  "email.date_time": "{day}. {month} {time}",
} as const;
