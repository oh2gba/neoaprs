// The Email tab: the list of mail with the state of each, Check email and its note, and the box to write a mail in.
export const email = {
  "email.compose": "Write an email",
  "email.to": "To {address}",
  "email.from": "From {address}",
  "email.checked": "Checked email",

  "email.none": "No mail yet.",
  "email.list": "Mail",
  "email.delete": "Delete: {title}",

  "email.check": "Check email",
  "email.checking": "Already checking",
  "email.about": "About email",
  "email.about_gateway": "Mail goes through the internet gateway EMAIL-2, so a mail can show {unconfirmed} although it arrived.",
  "email.about_check": "{check} asks the gateway for the mail it kept for you (24 hours).",

  "email.field.to": "To",
  "email.field.address": "Email address",
  "email.field.text": "Text",
  "email.to_tip": "The address the mail goes to. Addresses used before are listed as you type.",
  "email.text_tip": "What the mail says. The counter shows how many characters are left in the message.",
  "email.used_before": "Used before",
  "email.forget": "Forget {address}",
  "email.send": "Send",

  "email.state.waiting": "Waiting for the radio",
  "email.state.sending": "Sending ({attempt} of {max})",
  "email.state.delivered": "Delivered",
  "email.state.rejected": "Rejected",
  "email.state.cancelled": "Cancelled",
  "email.state.unconfirmed": "Not confirmed",
  "email.not_confirmed": "sent, not confirmed: the gateway's ack reaches you only through an iGate, so the mail may well have gone through",

  "email.date_time": "{day} {month} {time}",
} as const;
