"""What the program keeps and for how long: fixed numbers that are not settings."""

LOG_KEEP_DAYS = 7                    # packets, weather observations and stations are kept this long (the weather graphs reach back 7 days)
HIDE_AFTER_MIN = 180                 # a station whose last position is older than this leaves the map (the page hides it; the table keeps it)
TNC_CHECK_SEC = 60                   # seconds of nothing at all on the line before the keep-alive asks a TNC that can be asked (the Kenwood and Kantronics profiles) whether the radio is there
HEARD_PATH_WINDOW_MIN = 60           # the automatic path of a message goes by the way a station's packets reached us only if they came that way this recently (minutes)
HEARD_PATH_MIN_PACKETS = 2           # ... and at least this many came that way within the window (a single packet is luck)
HEARD_PATH_MAX_DIGIPEATERS = 3       # a route of more digipeaters than this is not sent by (heard that way, but too long a path to repeat)
HEARD_PATH_ATTEMPTS = 2              # attempts 1 to this many of a message go by the heard path, the later ones by `beacon/path`
