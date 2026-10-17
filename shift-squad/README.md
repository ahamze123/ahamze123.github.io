# Shift Squad

Play at https://ahamze123.github.io/shift-squad/

A 3D jobs simulator in the browser. Pick one of four workplaces from the menu (Corner Shop, Bistro Kitchen, Downtown Office, Auto Garage). Grab what each robot customer asks for, work it at the station in the middle of the floor (scan, cook, label or inspect), then hand it over. There is no shift timer and no customer timer.

Main menu: **Host an online game** gives you a room code (and a link) to share, **Play solo** starts a shift right away, and friends enter a code under **Join**. **Settings** (music, song, sound effects, robot voices, graphics, full screen, look speed, tips) is in the main menu and behind the gear button during a shift.

Music: the Block Buddies songs from this site's `music` folder. Skyline Exploration is packed into the page, and the other three (Gliding Over Green Valleys, Quiet Horizons, Subtle Quests and Flying Capes) stream from `../music/`. Each workplace has its own song on Automatic, or pick one in Settings.

Online play: friends enter the code under Join. Players connect directly to each other (WebRTC through Trystero, using public matchmaking relays), so there is no game server. The host picks the workplace in the lobby. Some strict networks block direct connections.

The whole game is bundled in `index.html`, including the 3D models. Three.js, Trystero and the fonts load from public CDNs.

Full screen: the Full screen button works on desktop, Android and iPad. iPhone browsers do not allow it, so tap Share, then Add to Home Screen, and open Shift Squad from your home screen for a full-screen app.
