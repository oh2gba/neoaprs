# Network access and the secure connection

## Opening the page from another device

By default the page answers on this computer only. To open it from another device on the same network, such as a laptop or phone at home while the radio and NeoAPRS run on a Raspberry Pi in the shack, tick **Allow access from the network** in the Settings tab, in the Web page group.

It counts at once, with no restart. The page now also listens on every interface (IPv4 and IPv6), on the same port. The group shows:

- the **access key**: three groups of four letters and digits, such as `k7m2-x9pq-4hrt`, made when the switch is first turned on;
- **Open at**: the addresses of this computer on the network, such as `http://192.168.1.20:7303/` and `http://NAME.local:7303/` with the name of the computer.

On the other device open one of the addresses and type the key into the one field of the key screen. The browser keeps the login for a year, so each device asks once. The log says the addresses too, and `neoaprs db get web/key` prints the key on a computer with no screen.

Switching the network off closes the pages that came in by it. On a page opened from another device, the page asks first ("This device will lose the page. Turn off?", Yes or Cancel).

The alert command runs on the NeoAPRS computer, and the page alerts in the browser it is open in ([notifications.md](notifications.md)).

### What is refused

- The page's files are free, because they hold the key screen. The connection that carries the data and the base map answer `401` to a device that has not logged in.
- This computer is never asked for a key. A request that carries `X-Forwarded-For`, `Forwarded` or `X-Real-Ip` came through a proxy and counts as from the network, so a reverse proxy on the Pi gets the key screen too.
- The page answers only to an IP address, `localhost`, the machine's own name (and `name.local`) and the names in the setting `web/allowed_hosts` (comma separated). A name for the machine that is not one of those is refused, and the log says so once with the command that adds it.
- **Wrong keys.** Five in a minute from one address shut that address out for five minutes, even for the right key. The log has every wrong key and the shutting out, and never the key.
- **A new key.** **New key** (it asks twice) makes another and logs every other device out: their open pages are closed and their sessions end at once. The device that pressed it stays in. A key you type yourself (`neoaprs db set web/key abcd-efgh-jkmn`, read when the daemon next starts) works the same. A key of your own must have the same form: three groups of four lowercase letters and digits without `0 1 i l o`.
- **The session** is a cookie (`neoaprs_session`, HttpOnly, SameSite=Strict) that holds an expiry, a random number and a signature of them under the key, not the key. The daemon stores nothing, a session survives a restart and ends with the key.

### Be careful

- **Plain HTTP.** The key is sent once, and the session cookie with every request, in the clear. Use it on a network you trust. Reach the Pi from outside through a VPN, not by opening the port to the internet. Do not forward a port to NeoAPRS in your router.
- Whoever is logged in can change every setting, the alert command (a shell line the computer runs) among them. The key is the only lock, so give it to your own devices only.
- **Windows** asks whether to let NeoAPRS through its firewall the first time the switch is on. Allow it on private networks.

### Another port

The page is on port 7303 (`web/port`, not on the page; `neoaprs db set web/port N`). `--web-port N` takes another one for a single run, and 0 takes a free one at once. A port that is in use moves the page to the first free one of the ten after it, and the log says which (`web page at http://127.0.0.1:PORT/`). When none is free the daemon runs without the page.

## The secure connection (https)

Tick **Secure connection (https)**, with **Allow access from the network**, in the same group. It is off by default. It is what a phone needs for pop-ups and what installing the page as an app needs, apart from `localhost`.

- NeoAPRS makes its own small certificate authority, "NeoAPRS local CA", and a certificate of this computer that it signs. They are made once, in `tls/` of the data folder (readable only by you), and renewed by themselves. The authority lasts ten years and is made only once, so a device that has trusted it stays trusted. The computer's certificate lasts at most 800 days and is made again when it has less than 30 days left, or when the computer has a name or address it does not name.
- The page and its socket are served over TLS on the port after the plain one (7304 for 7303; if that is taken, the next free one of the ten after it). The plain port stays open.
- A device other than this computer that asks the plain port is sent on to the secure one. `localhost` keeps plain http; on the computer itself http is already a secure address for the browser, and the desktop app's window is there.
- If the secure side cannot start, the page says why and the plain port goes on as it was.
- A secure session cookie is marked secure.

Browsers show a warning the first time, because they do not know the authority. You can continue past it, or make the warning go away by installing the authority's certificate on the device. The certificate is the file `NeoAPRS-CA.crt`, downloaded from `/neoaprs-ca.crt` on either port (only the public certificate, never a key). A guide under the switch lists the steps for Android, iPhone and iPad, Windows, macOS, Linux (Chrome) and Firefox, for the device you are on.

## Install the page as an app

The page can be installed so that it opens in a window of its own with an icon. Once opened, its shell opens even while the daemon is away; it then says "daemon offline" and connects when the daemon is back.

A browser installs a page only from a secure address: `http://127.0.0.1:7303/` or `http://localhost:7303/` on the computer that runs NeoAPRS, an `https://` address (the secure connection above, or a reverse proxy in front of the daemon with its host name in `web/allowed_hosts`).

- **On the computer that runs NeoAPRS** (Chrome, Edge, Brave, Opera): open the page, then use the install icon at the end of the address bar, the browser's menu ("Install NeoAPRS…"), or **Install app** in the Settings tab, In this browser, which is there when the browser offers the install. Firefox and Safari on a computer do not install pages. The [desktop app](desktop.md) is a window of its own already.
- **On a phone over plain `http://`** the browser refuses the install, and the page works as before with no message. A phone can still put it on the home screen as a shortcut: Android Chrome, menu, *Add to Home screen*; iPhone Safari, Share, *Add to Home Screen*. It opens in its own window with the NeoAPRS icon, and needs the daemon to be reachable, as the page does in a tab. With the secure connection on and the certificate installed, a phone can install the page.
- **What the browser keeps.** The page's numbered files are kept after their first use. The shell, the manifest, the icons, the symbol sheets and the glyph files are asked of the daemon every time, and a kept copy is shown only when the daemon cannot be reached, so an update is never hidden behind an old page. The data connection, the login, the base map and everything that is not a plain read are never kept. A new release brings a new helper that takes over at once and deletes the old files. To clear it: the browser's site settings, *Clear data* for the address.
