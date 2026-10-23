"""The default command of the message alert (`messages/alert_command`), one for each system: the line the alert runs (neoaprs/services/alerts.py), with the sender and the text in its environment
(NEOAPRS_FROM, NEOAPRS_TEXT) and never in the line itself. On Linux and macOS it is a shell line; on Windows it is a PowerShell script, which the alert runs as it is (an encoded script, no quoting)."""
import sys

LINUX_ALERT_COMMAND = '(notify-send -- "APRS message from $NEOAPRS_FROM" "$NEOAPRS_TEXT" 2>/dev/null || kdialog --title "APRS message from $NEOAPRS_FROM" --passivepopup "$NEOAPRS_TEXT" 10); paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga'
WINDOWS_ALERT_COMMAND = ("$null=[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];$null=[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime];"
                         "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);$t=$x.GetElementsByTagName('text');"
                         "$t.Item(0).InnerText='APRS message from '+$env:NEOAPRS_FROM;$t.Item(1).InnerText=$env:NEOAPRS_TEXT;"
                         "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show([Windows.UI.Notifications.ToastNotification]::new($x));"
                         "[System.Media.SystemSounds]::Asterisk.Play()")       # PowerShell (the Windows alert runs under it, services/alerts.py); the sender and the text are read from the environment, never part of the script
DEFAULT_ALERT_COMMAND = WINDOWS_ALERT_COMMAND if sys.platform == "win32" else LINUX_ALERT_COMMAND
