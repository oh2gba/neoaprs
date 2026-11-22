"""Default alert command for each platform.

Title, sender and text reach the command in NEOAPRS_TITLE, NEOAPRS_FROM and NEOAPRS_TEXT, never
in the command line. Linux and macOS use a shell line; Windows a PowerShell script on stdin.
"""
import sys

# Escape & < > so that notification servers do not render a station's text as markup.
_MARKUP = r"sed 's/&/\&amp;/g;s/</\&lt;/g;s/>/\&gt;/g'"
LINUX_ALERT_COMMAND = (f"""t=$(printf '%s' "$NEOAPRS_TITLE" | {_MARKUP}); b=$(printf '%s' "$NEOAPRS_TEXT" | {_MARKUP}); """
                       '(notify-send -- "$t" "$b" 2>/dev/null || kdialog --title "$t" --passivepopup "$b" 10); paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga')
# The title and the text are read from the environment, never embedded in the script.
WINDOWS_ALERT_COMMAND = ("$null=[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];$null=[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime];"
                         "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);$t=$x.GetElementsByTagName('text');"
                         "$t.Item(0).InnerText=$env:NEOAPRS_TITLE;$t.Item(1).InnerText=$env:NEOAPRS_TEXT;"
                         "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show([Windows.UI.Notifications.ToastNotification]::new($x));"
                         "[System.Media.SystemSounds]::Asterisk.Play()")
DEFAULT_ALERT_COMMAND = WINDOWS_ALERT_COMMAND if sys.platform == "win32" else LINUX_ALERT_COMMAND
