"""What the program keeps and for how long: fixed numbers that are not settings."""

LOG_KEEP_DAYS = 7                    # packets, weather observations and stations are kept this long (the weather graphs reach back 7 days)
TNC_CHECK_SEC = 600                  # seconds of nothing at all on the line before the keep-alive asks a TNC that can be asked (the Kenwood and Kantronics profiles) whether the radio is there: a check deafens the TNC for a few seconds, and after one quiet minute it fell again and again on the next beacon of a station that sends one a minute
TNC_CHECK_JITTER = 0.2               # each quiet period is longer by a random part of it, up to this share, so that the checks never keep step with a station's beacons
HEARD_PATH_WINDOW_MIN = 60           # the automatic path of a message goes by the way a station's packets reached us only if they came that way this recently (minutes)
HEARD_PATH_MIN_PACKETS = 2           # ... and at least this many came that way within the window (a single packet is luck)
HEARD_PATH_MAX_DIGIPEATERS = 3       # a route of more digipeaters than this is not sent by (heard that way, but too long a path to repeat)
HEARD_PATH_ATTEMPTS = 2              # attempts 1 to this many of a message go by the heard path, the later ones by `beacon/path`

# The ALOHA circle (Bob Bruninga WB4APR, "The ALOHA Circle", aprs.org/aloha/ALOHAcir.txt, 7 Nov 2011, and aprs.org/aloha.html): the radius round our station within which the stations heard on RF fill the 1200 baud channel.
ALOHA_PACKETS = 1800                 # the load that fills the channel: about 60 packets a minute, 1800 in 30 minutes; the circle ends at the station where the stations nearer than it add up to this
ALOHA_WINDOW_MIN = 60                # a station counts when it was heard this recently (the text counts the stations of the last cycle of 30 minutes; a home station that beacons every 30 minutes would be missed by exactly that)
ALOHA_WEIGHT_MOVING = 15             # packets in 30 minutes of a mobile station in motion ...
ALOHA_WEIGHT_MOBILE = 7              # ... of any other mobile station
ALOHA_WEIGHT_WEATHER = 6             # ... of a weather station
ALOHA_WEIGHT_DIGI = 3                # ... of a digipeater
ALOHA_WEIGHT_HOME = 2                # ... of a home station (any other)
ALOHA_MOVING_KMH = 5.0               # a mobile station reporting more than this speed is in motion (ours: the text says only "in motion", and a parked GPS drifts a few km/h)
ALOHA_EVERY_SEC = 60.0               # the circle is worked out again this often (the text: every 30 minutes)
