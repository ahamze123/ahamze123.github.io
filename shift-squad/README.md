# Shift Squad

Play at https://ahamze123.github.io/shift-squad/

A 3D jobs simulator in the browser. Pick one of four workplaces from the menu (Corner Shop, Bistro Kitchen, Downtown Office, Auto Garage). Grab what each robot customer asks for, work it at the station in the middle of the floor (scan, cook, label or inspect), then hand it over. There is no shift timer and no customer timer.

Online play: start a shift to get a room code (or a link), and friends enter it under Join. Players connect directly to each other (WebRTC through Trystero, using public matchmaking relays), so there is no game server. The host picks the workplace in the lobby. Some strict networks block direct connections.

The whole game is bundled in `index.html`, including the 3D models. Three.js, Trystero and the fonts load from public CDNs.

Full screen: the Full screen button works on desktop, Android and iPad. iPhone browsers do not allow it, so tap Share, then Add to Home Screen, and open Shift Squad from your home screen for a full-screen app.
