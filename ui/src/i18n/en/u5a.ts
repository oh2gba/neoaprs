// The words of the radio a message goes on (package U5a of the radio round: Messages, Email and the station panel). A radio's name stands in the two forms of the plan only: the name and a colon, or after a noun that
// carries the grammar ("on radio {name}"). The integration (I5) moves these into the area files and removes the doubles of the shared words (`radio.*`).
export const u5a = {
  "radio.automatic": "Automatic",
  "radio.not_connected": "{name}: not connected",
  "radio.heard_on": "Heard on radio {name}",
  "route.radio": "Radio",
  "route.radio_auto": "Automatic: {name}",
  "route.no_path": "{name}: no path",
  "messages.radio_title": "Messages to this station go on radio {name}",
  "chain.sent_on": "sent {time} on radio {name}",
  "email.radio_title": "Email goes on radio {name}",
} as const;
