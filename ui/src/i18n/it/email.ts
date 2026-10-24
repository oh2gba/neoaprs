import type { email as en } from "@/i18n/en/email";
import type { Message } from "@/i18n/message";

export const email: Readonly<Record<keyof typeof en, Message>> = {
  "email.compose": "Email",
  "email.to": "A {address}",
  "email.from": "Da {address}",
  "email.checked": "Email controllata",

  "email.none": "Ancora nessuna email.",
  "email.list": "Email",
  "email.delete": "Elimina: {title}",

  "email.check": "Controlla email",
  "email.checking": "Controllo già in corso",
  "email.about": "Sulle email",
  "email.about_gateway": "La posta passa dal gateway internet EMAIL-2 tramite un iGate, quindi una email può risultare {unconfirmed} anche se è arrivata.",
  "email.about_check": "{check} chiede al gateway la posta che ha conservato per te (la conserva per 24 ore).",

  "email.field.to": "A",
  "email.field.address": "Indirizzo email",
  "email.field.text": "Testo",
  "email.used_before": "Usati in precedenza",
  "email.forget": "Dimentica {address}",
  "email.send": "Invia",

  "email.state.waiting": "In attesa della radio",
  "email.state.sending": "Invio ({attempt} di {max})",
  "email.state.delivered": "Consegnata",
  "email.state.rejected": "Rifiutata",
  "email.state.cancelled": "Annullata",
  "email.state.unconfirmed": "Non confermata",
  "email.not_confirmed": "inviata, non confermata: la conferma del gateway ti arriva solo tramite un iGate, quindi la email potrebbe essere partita lo stesso",

  "email.date_time": "{day} {month} {time}",
};
