# Getting help

When something does not work, NeoAPRS can collect what it knows into one file, which you e-mail to the project with a few words. The file is made on your computer and goes nowhere by itself: you can open it and read every part before you send it.

Send it to **neoaprs@oh2gba.eu**. It helps most to say:

- what you did,
- what you expected,
- what happened instead,
- and roughly when (the time lets the developer find it in the log).

## From the page

Open the **Settings** tab and scroll down to the group **Help**, above About. Press **Download logs**. The button reads "Collecting…" while the file is made, and your browser then saves a zip like any download, in its download folder. The (i) beside the button says what the file holds.

Under the button the page says "Saved" and the name of the file, which holds your call and the time in UTC. The address **neoaprs@oh2gba.eu** in the line above the button is a link that opens your mail program with a subject that starts with "NeoAPRS" and its version, and a form to fill in: what you did, what you expected, what happened and when; once the file is saved, the form also reminds you to attach it. Attach the file yourself; a page cannot do that for you. Without a mail program, send the file from any other.

If the button cannot make the file, it says why:

- **No access:** this device is not let in. Reload the page and enter the access key ([network.md](network.md)).
- **Another file is being made:** the daemon makes one at a time. Try again in a minute.
- **The daemon could not be reached:** use the command below.

The page also tells the daemon when it fails itself, and the file carries those errors.

## Without a working page

If the page does not open, or the daemon does not run, the file can be made without it:

- `neoaprs support` makes the file on your Desktop and says where it put it. `--out FOLDER` puts it in another folder, and `--show` shows the file in your file manager when it is made ([commands.md](commands.md)).
- On Windows, the Start menu has an entry **NeoAPRS support logs**, which does the same.
- In the desktop app, the tray icon's menu has **Collect support logs**.

A file made this way is made from the data folder alone, so it lacks what only the page and the running daemon can tell: `page.json` and `page-errors.json` (the facts of the browser and its errors) and `state.json` (the live state). The page's download, which the daemon makes, has them.

## What is in the file

The zip holds plain text files. `README.txt` inside it says the same as here. Open `summary.txt` first.

| file | what it has |
|---|---|
| `README.txt` | what the file is and what to do with it |
| `summary.txt` | one screen: the version, the system, the station, the radio, the GPS, the web page, the database, and the warnings and errors of the log, each message once with how many times and when last |
| `logs/` | the log of the program, the rotated ones too, the log of the desktop app when there is one, and on Linux what the system's journal has of the service |
| `settings.json` | every setting with its value; the access key is only said to be set |
| `state.json` | what the running daemon knows now: the radio, the GPS, the beacon, the base map, the update, the serial ports and who holds them |
| `doctor.txt` | the checks of `neoaprs doctor` ([commands.md](commands.md#neoaprs-doctor)) |
| `database.txt` | the version of the database, the number of rows in each table, the sizes of the files and whether the file is sound |
| `packets.txt` | the last packets heard and sent, and the last ones that could not be decoded |
| `page.json` | what the page told about itself: its build, the browser, the language, the size of the window, whether it is installed as an app, and whether the connection to the daemon is up |
| `page-errors.json` | the errors the page met and told the daemon about |

## What is not in the file

- **The access key.** It lets a device on your network into the page, and it is taken out of every file.
- **The key of the secure connection.** It is a secret, and nothing is wrong in it that the log does not say.
- **Your messages as the program keeps them,** and **the database file itself.** They are yours, and a fault is found without them. `database.txt` says what is in the database.
- **The base map.** It is large and a fault is not in it.

Know what is in it before you send it. The log and `packets.txt` have the packets heard and sent, which on APRS are public, with the texts of messages to and from other stations and their calls. The log also has the addresses of the devices that opened the page, and `settings.json` the position your beacon sends.

## Feedback

Feedback and ideas: [GitHub issues](https://github.com/oh2gba/neoaprs/issues) (preferred) or <neoaprs@oh2gba.eu>. The page says it too, at the end of Settings → About.

## Other ways

Bugs and ideas can also go to the issues above. The checklist of `neoaprs doctor` and the usual causes of a silent radio are in [commands.md](commands.md#when-something-does-not-work).
