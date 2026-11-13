"""The default command of the alert (`messages/alert_command`), one for each system: the line the alert runs (neoaprs/services/alerts.py) for a message to us and for an alert of a station, with the title, the sender and the text in its environment
(NEOAPRS_TITLE, NEOAPRS_FROM, NEOAPRS_TEXT) and never in the line itself. On Linux and macOS it is a shell line, which hands the title and the text to the notifier with & < > escaped (the variables stay as they are, for a line of the operator's own); on Windows it is a PowerShell script, which the alert gives PowerShell as it is on its standard input (no quoting)."""
import sys

_MARKUP = r"sed 's/&/\&amp;/g;s/</\&lt;/g;s/>/\&gt;/g'"            # & < > as the entities a notification server and kdialog read markup by: what a station wrote is shown as it wrote it, not as bold text, a link or an image
LINUX_ALERT_COMMAND = (f"""t=$(printf '%s' "$NEOAPRS_TITLE" | {_MARKUP}); b=$(printf '%s' "$NEOAPRS_TEXT" | {_MARKUP}); """
                       '(notify-send -- "$t" "$b" 2>/dev/null || kdialog --title "$t" --passivepopup "$b" 10); paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga')
WINDOWS_ALERT_COMMAND = ("$null=[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];$null=[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime];"
                         "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);$t=$x.GetElementsByTagName('text');"
                         "$t.Item(0).InnerText=$env:NEOAPRS_TITLE;$t.Item(1).InnerText=$env:NEOAPRS_TEXT;"
                         "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show([Windows.UI.Notifications.ToastNotification]::new($x));"
                         "[System.Media.SystemSounds]::Asterisk.Play()")       # PowerShell (the Windows alert runs under it, services/alerts.py); the title and the text are read from the environment, never part of the script
DEFAULT_ALERT_COMMAND = WINDOWS_ALERT_COMMAND if sys.platform == "win32" else LINUX_ALERT_COMMAND
