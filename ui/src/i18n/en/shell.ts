// The frame of the page: the header, the tabs and the panel that holds them, the footer, the toasts, the choice of language.
export const shell = {
  "common.dismiss": "Dismiss",

  "header.project_title": "The NeoAPRS project page",
  "header.receive_only": "Receive only",
  "header.receive_only_title":
    "Nothing is transmitted: this station is set to receive only. It is the daemon's setting station/transmit, which is not on this page; neoaprs db set station/transmit true changes it at the next start",
  "header.no_call": "no call set",
  "header.no_call_title": "Nothing is transmitted until a call is set: open the setup",
  "header.unread_open": {
    one: "{n} message not seen yet: open the messages",
    other: "{n} messages not seen yet: open the messages",
  },

  "unread.not_seen": { one: "{n} message not seen yet", other: "{n} messages not seen yet" },
  "unread.new_bulletins": { one: "{n} new bulletin", other: "{n} new bulletins" },

  "tab.messages": "Messages",
  "tab.stations": "Stations",
  "tab.nearby": "Nearby",
  "tab.email": "Email",
  "tab.bulletins": "Bulletins",
  "tab.objects": "Objects",
  "tab.beacon": "Beacon",
  "tab.packets": "Packets",
  "tab.settings": "Settings",
  "tab.more": "More",
  "tab.menu_new": ", {n} new",

  "panel.label": "Details",
  "panel.map": "Map",
  "panel.width": "Panel width",
  "panel.show": "Show the panel",
  "panel.hide": "Hide the panel",
  "panel.show_unseen": "Show the panel, {unseen}",

  "footer.cost": "NeoAPRS uses {cpu} % of one processor core and {mb} MB of memory, running for {span}",
  "footer.cost_no_memory": "NeoAPRS uses {cpu} % of one processor core, running for {span}",
  "footer.update": "Update to {version}",
  "footer.offline": "Daemon offline",
  "footer.connecting": "Connecting…",
  "footer.radio.waiting": "Radio: waiting…",
  "footer.radio.waiting_title": "no word from the TNC yet",
  "footer.radio.silent": "Radio: silent",
  "footer.radio.entering_kiss": "Radio: entering KISS…",
  "footer.radio.searching": "Radio: searching…",
  "footer.radio.not_connected": "Radio: not connected",
  "footer.radio.open_settings": "Open the radio settings",

  "settings.language.label": "Language",
} as const;
