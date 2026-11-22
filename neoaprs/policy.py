"""What the program keeps and for how long: fixed numbers that are not settings."""

# packets, weather observations and stations are kept this long (the weather graphs reach back 7
# days)
LOG_KEEP_DAYS = 7
# packets from APRS-IS are the bulk of what a station with internet stations on keeps (five a
# second at 743 bytes a row with indexes: seven days would be 2 GB on a Raspberry Pi's card, and
# the file has no other bound); two days is what the map and the stations' tracks need
INTERNET_KEEP_DAYS = 2
# seconds of nothing on the line before the keep-alive asks a TNC that can be asked (Kenwood and
# Kantronics profiles) whether the radio is there: a check deafens the TNC for a few seconds, and
# after one quiet minute it kept falling on the next beacon of a station that sends one a minute
TNC_CHECK_SEC = 600
# each quiet period is longer by a random share of it, up to this, so checks never keep step with
# beacons
TNC_CHECK_JITTER = 0.2
# the automatic path of a message follows the way a station's packets reached us only if they came
# that way this recently (minutes) ...
HEARD_PATH_WINDOW_MIN = 60
# ... and at least this many within the window (a single packet is luck)
HEARD_PATH_MIN_PACKETS = 2
# a route of more digipeaters than this is too long a path to repeat
HEARD_PATH_MAX_DIGIPEATERS = 3
# attempts 1 to this many of a message go by the heard path, later ones by `beacon/path`
HEARD_PATH_ATTEMPTS = 2
# a message to a station goes on the radio it was heard on most recently within this many hours, a
# local kind (FM, LoRa) before HF when both heard it (neoaprs/messagerule.py)
MESSAGE_RADIO_RECENT_HOURS = 6

# The ALOHA circle (aprs.org/aloha/ALOHAcir.txt): the radius within which the stations heard fill
# the 1200 baud channel, about 60 packets a minute; the circle ends where they add up to this
ALOHA_PACKETS = 1800
# a station counts when heard this recently (not 30 minutes: that would miss a 30-minute beacon)
ALOHA_WINDOW_MIN = 60
ALOHA_WEIGHT_MOVING = 15  # packets in 30 minutes of a mobile station in motion ...
ALOHA_WEIGHT_MOBILE = 7  # ... of any other mobile station
ALOHA_WEIGHT_WEATHER = 6  # ... of a weather station
ALOHA_WEIGHT_DIGI = 3  # ... of a digipeater
ALOHA_WEIGHT_HOME = 2  # ... of a home station (any other)
# a mobile station faster than this is in motion (a parked GPS drifts a few km/h)
ALOHA_MOVING_KMH = 5.0
ALOHA_EVERY_SEC = 60.0  # the circle is recomputed this often

# a packet heard again within this long with the same source, destination and information is a
# duplicate that a digipeater and an iGate drop (WB2OSZ's digipeater algorithm: 28 to 30 s);
# messages wait longer before resending, and an ack is not repeated within it
DIGI_DUPLICATE_SEC = 30.0

# a GPS fix older than this is not used: a mobile station sends no beacon on it (never the home
# position instead), and the page is told the fix is stale
GPS_STALE_SEC = 120
# our own row on the map follows the GPS at most this often ...
GPS_PLACE_EVERY_SEC = 5.0
# ... and only after we moved at least this far from where it was put
GPS_PLACE_MOVED_M = 10.0
