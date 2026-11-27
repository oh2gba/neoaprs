"""NeoAPRS: an APRS client daemon with a web page, in pure Python."""

VERSION = "0.26.0"
# The destination call of every frame we send. APZ is the experimental range; a registered tocall
# is requested (github.com/aprsorg/aprs-deviceid/issues/427).
TOCALL = "APZNEO"
PROGRAM = "NeoAPRS"  # what the logs and the service manager see
