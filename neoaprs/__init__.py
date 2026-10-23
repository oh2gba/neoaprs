"""NeoAPRS: an APRS client daemon with a web page, in pure Python."""

VERSION = "0.4.0"          # the one version of the package: pyproject.toml reads it (hatch), and the wheel, `neoaprs --version` and the log say it
TOCALL = "APZNEO"         # the destination call of every frame we send: APZ is the experimental range of the tocalls, not a setting; the registered one replaces it here (github.com/aprsorg/aprs-deviceid)
PROGRAM = "NeoAPRS"         # what the logs and the service manager see
