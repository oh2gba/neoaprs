// The words of the package U4 of the radio round (the tags, the header, the lists, the statistics with any number of radios), kept apart until the integration I5 puts them in the files of their areas. A radio's
// name stands in two forms only, so that no language has to inflect it: the name and a colon ("{name}: {when}"), or after a noun that carries the grammar ("Heard on radio {name}").
export const u4 = {
  "radio.heard_on": "Heard on radio {name}",
  "radio.heard_at": "{name}: {when}",
  "radio.state": "{name}: {state}",
  "radio.more": "+{n}",
  "pill.radio_named": "{radio}",
  "pill.radios": "Radios",
  "pill.radios_waiting": "Radios: waiting…",
  "pill.radios_trouble": { one: "Radios: {n} not connected", other: "Radios: {n} not connected" },
  "packets.came_by.radio": "heard on radio {name}",
} as const;
