// The lists the daemon owns and the page shows, written from the daemon's own constants by scripts/gen-protocol.py: never edited by hand.

/** The version of the messages (PROTOCOL of neoaprs/web/hubwire.py): a `hello` of another number means the page is out of date. */
export const PROTOCOL = 1;

/** The topics of the hub, in the order the daemon tells them (TopicValues of neoaprs/web/protocol.py). */
export const TOPIC_NAMES = ["stations", "packets", "tnc", "config", "station_prefs", "messages", "bulletins", "map"] as const;

/** Every command the page may send (the `cmd` of the Command union). */
export const COMMAND_NAMES = ["alert_test", "beacon_now", "bulletin_delete", "clear_station_attempts", "clear_station_path", "clear_station_timeout", "conversation_delete", "forget_station", "list_ports", "map_cancel", "map_estimate", "map_fetch", "message_cancel", "message_delete", "message_retry", "overheard_delete", "ping", "send_message", "set_config", "set_station_attempts", "set_station_path", "set_station_rf_only", "set_station_timeout", "status", "subscribe", "tnc_reconnect", "unsubscribe", "weather_series"] as const;

/** Every message the daemon sends (the `type` of the Message union). */
export const MESSAGE_TYPES = ["alert_result", "error", "hello", "patch", "pong", "ports", "state", "status", "weather_series"] as const;

/** The keys of the settings, in the order of the settings form (SETTINGS of neoaprs/config.py). */
export const CONFIG_KEYS = ["tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port", "serial/last_port", "serial/pattern", "serial/skip", "tnc/check_sec", "station/call", "station/lat", "station/lon", "station/symbol_table", "station/symbol_code", "station/comment", "station/status", "beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction", "log/keep_days", "web/bind", "web/port", "web/allowed_hosts", "beacon/interval_min", "beacon/path", "beacon/destination", "beacon/compressed", "beacon/dao", "messages/attempts", "messages/alert", "messages/alert_command", "status/rigctld", "status/interval_min", "status/template", "map/hide_after_min", "map/radius_km", "map/maxzoom", "map/source"] as const;

/** The TNC profiles, in the order the settings form offers them (PROFILES of neoaprs/tncprofile.py): how each is reached (`serial` or `tcp`), its speed and whether the daemon can ask it if it is there. */
export const TNC_PROFILES = [{"key": "kenwood-tnc2", "name": "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2", "transport": "serial", "baud": 9600, "probe": true}, {"key": "kenwood-d710", "name": "Kenwood TM-D710 / TH-D72", "transport": "serial", "baud": 9600, "probe": true}, {"key": "kantronics", "name": "Kantronics KPC-3+", "transport": "serial", "baud": 9600, "probe": true}, {"key": "kiss", "name": "KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75\u2026)", "transport": "serial", "baud": 9600, "probe": false}, {"key": "kiss-tcp", "name": "KISS over TCP (Direwolf, soundmodem)", "transport": "tcp", "baud": null, "probe": false}] as const;

/** What the parser makes of a packet (KINDS of neoaprs/packetcodec.py). */
export const PACKET_KINDS = ["position", "message", "object", "item", "status", "other", "undecoded"] as const;

/** A station, or an object or an item that a station reports (neoaprs/web/stationwire.py). */
export const STATION_KINDS = ["station", "object", "item"] as const;

/** The states of the TNC (Source.State of neoaprs/source.py). */
export const TNC_STATES = ["stopped", "connecting", "connected", "waiting", "silent"] as const;

/** The states of a message (State of neoaprs/message.py). */
export const MESSAGE_STATES = ["sending", "acked", "rejected", "failed", "unconfirmed", "cancelled", "received", "overheard"] as const;

/** How many bytes of UTF-8 the text of a message may have (MAX_TEXT of neoaprs/aprsmessage.py). */
export const MESSAGE_TEXT_MAX = 67;

/** How many times a message is transmitted before it has failed when the setting messages/attempts is not changed (DEFAULT_ATTEMPTS of neoaprs/message.py). */
export const MESSAGE_ATTEMPTS_DEFAULT = 6;

/** The most the setting messages/attempts may be (MAX_ATTEMPTS of neoaprs/message.py). */
export const MESSAGE_ATTEMPTS_MAX = 10;

/** How many positions of a station's track the daemon keeps (TRACK_MAX of neoaprs/stationbook.py). */
export const TRACK_MAX = 50;

/** How many packets the topic `packets` holds (PACKETS_KEPT of neoaprs/web/topics.py). */
export const PACKETS_KEPT = 200;

/** How many lines of the TNC the topic `tnc` holds (LINES_MAX of neoaprs/web/views.py). */
export const TNC_LINES_MAX = 100;

/** The least time between two patches of the topic `tnc` (TNC_EVERY_SEC of neoaprs/web/topics.py). */
export const TNC_EVERY_SEC = 0.25;

/** The kinds of a row of the message board (Kind of neoaprs/bulletin.py). */
export const BULLETIN_KINDS = ["announcement", "bulletin", "group", "nws"] as const;

/** How many bytes of UTF-8 the setting station/status may have (MAX_STATUS of neoaprs/config.py). */
export const STATUS_MAX = 55;

/** How long the comment of a position packet may be (MAX_COMMENT of neoaprs/config.py). */
export const COMMENT_MAX = 43;

/** The characters a symbol table can be: the primary, the alternate and the overlays (SYMBOL_TABLES of neoaprs/config.py). */
export const SYMBOL_TABLES = "/\\ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
