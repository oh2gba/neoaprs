"""What the program keeps and for how long: fixed numbers that are not settings."""

LOG_KEEP_DAYS = 7                    # packets, weather observations and stations are kept this long (the weather graphs reach back 7 days)
MAX_HIDE_AFTER_MIN = 10080           # a week: the longest a station may stay on the map after its last position (the longest own timeout of a station)
HIDE_AFTER_MIN = 180                 # a station whose last position is older than this leaves the map (the page hides it; the table keeps it); a station can have a timeout of its own, 0 for never
TNC_CHECK_SEC = 60                   # seconds of nothing at all on the line before the keep-alive asks a TNC that can be asked (the Kenwood and Kantronics profiles) whether the radio is there
