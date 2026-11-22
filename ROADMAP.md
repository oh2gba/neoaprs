# Roadmap

What is planned.

- A registered tocall in place of `APZNEO` (requested: github.com/aprsorg/aprs-deviceid/issues/427)
- The FM radio type "Sound card" on a Mac too. Windows and Linux have it since 0.20.0; on a Mac, Direwolf built from the pinned source in the macOS app as Mercury is, so that a radio with a sound-card interface needs nothing else installed there either.
- The suggested frequencies in the Mercury radio's box aligned as on the project page: the bands right-aligned and the decimal points one under another.
- Installing the page on a phone as an app made easy. The page is a PWA already (the manifest, the service worker, the icons), but a phone installs it only over the secure connection, which is off by default, and with NeoAPRS's certificate installed on the phone, three steps that nobody finds; over plain http a phone gets only a shortcut on the home screen. The Settings tab has Install app where the browser offers it; what is planned is one guided way there from the phone itself: the secure connection, the certificate for that phone, the install.
- The desktop window by one toolkit on every system: pywebview on Linux and macOS too (WebKitGTK and WKWebView, the system's own web views), as on Windows, in place of Qt and its web engine, which is a whole Chromium inside the AppImage and the macOS app. A trial first, since the map (MapLibre, WebGL) must draw as well in WebKitGTK as in Chromium; where it does not, Linux opens the browser and keeps the tray icon.
- The Windows installer and the macOS app signed by a publisher's certificate, so that Windows and macOS stop warning when NeoAPRS is installed. It waits until it can be done without cost: the owner pays for nothing, and a free programme for open source would need his application. (Updates are signed already, by the project's own key, at no cost: that is another thing.)
