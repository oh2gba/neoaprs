// The map: its notes, its credits, the menu of a right-click on it, the bar of its replay, the bar that asks for a place on it.
export const map = {
  "map.label": "Map of the stations",
  "map.zoom_in": "Zoom in",
  "map.zoom_out": "Zoom out",
  "map.download": "Download",
  "map.note.no_basemap": "No base map",
  "map.note.no_detail": "No detailed map",
  "map.note.no_engine": "The map could not be loaded",
  "map.note.unreadable": "The map file cannot be read",
  "map.follow_me": "Follow my position",
  "map.aloha": "ALOHA circle: {km} km",

  "map.credits.hide": "Hide the credits",
  "map.credits.show": "Map and symbol credits",
  "map.credits.symbols": "APRS symbols: aprs.fi set by Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",
  "map.credits.devices": "Device names: APRS device identification list by Hessu, OH7LZB (github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.menu_label": "Map",
  "map.menu.copy_position": "Copy position {place}",
  "map.menu.copy_locator": "Copy locator {locator}",
  "map.menu.stats": "Statistics",
  "map.menu.replay": "Replay",

  "map.replay.label": "Replay of the map",
  "map.replay.play": "Play",
  "map.replay.pause": "Pause",
  "map.replay.time": "Time of the replay",
  "map.replay.speed": "Speed",
  "map.replay.speed_n": "{n}×",
  "map.replay.span": "Span",
  "map.replay.when_paused": "{what}: can be changed while paused",
  "map.replay.close": "Close the replay",
  "map.replay.none": "No positions were heard in the last {span}",

  "map.pick.tap": "Tap the place on the map",
  "map.pick.cancel": "Cancel",
} as const;
