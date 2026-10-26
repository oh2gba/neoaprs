"""The units APRS writes on the air (knots, statute miles, feet, inches, degrees Fahrenheit) against the metric ones the program keeps (km/h, km, metres, millimetres, degrees Celsius): the factors, each written once.

Pure code, like the rest of the foundation."""

KNOT_KMH = 1.852                      # a knot in km/h: the speed of a position report, an object and a storm
NAUTICAL_MILE_KM = 1.852              # a nautical mile in km: the radii of a storm
MILE_KM = 1.609344                    # a statute mile in km: the range of PHG and RNG, the radius of a query's footprint, and a mile an hour in km/h (the wind of a weather report, SmartBeaconing's slope)
FOOT_M = 0.3048                       # a foot in metres: the altitude `/A=`, the height of PHG
INCH_MM = 25.4                        # an inch in millimetres: the snow of a weather report (the rain is in hundredths of an inch, 0.254 mm each)
MS_KMH = 3.6                          # a metre a second in km/h: the speed gpsd reports


def fahrenheit_to_celsius(degrees_f: float) -> float:
    return (degrees_f - 32) * 5 / 9
