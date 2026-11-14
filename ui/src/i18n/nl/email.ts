// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { email as source } from "@/i18n/en/email";
import type { Message } from "@/i18n/message";

export const email: Record<keyof typeof source, Message> = {
  "email.compose": "E-mail schrijven",
  "email.to": "Aan {address}",
  "email.from": "Van {address}",
  "email.checked": "E-mail opgehaald",

  "email.none": "Nog geen e-mail.",
  "email.list": "E-mail",
  "email.delete": "Verwijderen: {title}",

  "email.check": "E-mail ophalen",
  "email.checking": "Ophalen loopt al",
  "email.about": "Over e-mail",
  "email.about_gateway": "E-mail gaat via de internetgateway EMAIL-2. Daarom kan er bij een mail {unconfirmed} staan, terwijl hij wel is aangekomen.",
  "email.about_check": "{check} vraagt de gateway om de mail die hij voor je bewaart (24 uur).",

  "email.field.to": "Aan",
  "email.field.address": "E-mailadres",
  "email.field.text": "Tekst",
  "email.to_tip": "Het adres waar de mail naartoe gaat. Eerder gebruikte adressen verschijnen terwijl je typt.",
  "email.text_tip": "Wat er in de mail staat. De teller toont hoeveel tekens er in het bericht nog over zijn.",
  "email.used_before": "Eerder gebruikt",
  "email.forget": "{address} vergeten",
  "email.send": "Verzenden",
  "email.fm_off": "E-mail gaat via de FM-set, en die staat uit",

  "email.state.waiting": "Wacht op de set",
  "email.state.sending": "Verzenden ({attempt} van {max})",
  "email.state.delivered": "Afgeleverd",
  "email.state.rejected": "Geweigerd",
  "email.state.cancelled": "Geannuleerd",
  "email.state.unconfirmed": "Niet bevestigd",
  "email.state.too_long_for_radio": "Te lang voor de set",
  "email.not_confirmed": "verzonden, niet bevestigd: de ack van de gateway bereikt je alleen via een iGate, dus de mail kan best zijn aangekomen",

  "email.date_time": "{day} {month} {time}",
} as const;
