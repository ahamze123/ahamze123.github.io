# Block Buddies as an iPad app (App Store)

The game itself is the website build (`index.html` with `cards/`, `models/`, `music/`), wrapped with
[Capacitor](https://capacitorjs.com) into an iPad app. Nothing here needs a Mac: GitHub's macOS runners build it.

- `make_www.py` makes the app's web files (`app/www`) from the website: it sets `window.BB_APP` (no Home Screen tips,
  a family code for online play) and puts the fonts inside the app.
- `ios_setup.py` sets up the Xcode project that Capacitor makes: iPad only, no status bar, the icon
  (`resources/icon-1024.png`) and the launch screen (`resources/splash-2732.png`).
- `sim_test.sh` tries the app on an iPad simulator and takes pictures; `upload.sh` sends the App Store build to
  App Store Connect (TestFlight). `asc.py` registers the app's bundle ID and checks the app exists in App Store Connect.
- `.github/workflows/ipad-app.yml` runs all of it when `build.json` changes (change `run` to start it again, and
  `version` for a new App Store version). The pictures and logs go to the branch `app-out`.

The upload needs these repository secrets (Settings › Secrets and variables › Actions), from App Store Connect
(Users and Access › Integrations › App Store Connect API, a Team key with **Admin** access):
`ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8` (the whole downloaded .p8 file) and `APPLE_TEAM_ID` (Membership details on
developer.apple.com). The app's bundle ID is `io.github.ahamze123.blockbuddies`.
