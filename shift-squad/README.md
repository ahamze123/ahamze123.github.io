# Shift Squad

Play at https://ahamze123.github.io/shift-squad/

A 3D jobs simulator in the browser. Pick one of eight workplaces from the menu (Corner Shop, Bistro Kitchen, Downtown Office, Auto Garage, Pizza Shop, Flower Shop, Ice Cream Parlor, Pet Salon). Grab what each robot customer asks for, work it at the station in the middle of the floor (scan, cook, label, inspect, bake, wrap, top with sundae toppings or wash), then hand it over. There is no shift timer and no customer timer.

Bonus coins: at your station a bar slides back and forth. Press while it is in the green for a Perfect (back-to-back Perfects pay more, a miss costs nothing). Every station has its own sound: scanner beeps, a sizzling stove, printer chatter, a ratchet and clank. Coins fly up to your total, the end of a shift throws confetti, and you keep your best stars per workplace on the menu cards. In a room the host sets the pace (Relaxed, Normal or Busy), anyone can send emotes (keys 1 to 5 or the smiley button), and the end screen names the top coworker.

The Shop: every shift's coins go into a bank saved on your device. Spend them under **Shop** (main menu or break room). **Upgrades** are a wider green zone, a steadier bar, quick boots and Golden touch (Perfects pay 1 more), plus a **robot dog**: press R (or tap 🐕 Fetch) and it runs to the shelves and brings you what the open orders need, with upgrades for its speed and how many items it carries. Other players see your dog run. **Decorate** lets you buy posters, plants, balloons, a floor rug, string lights and a neon OPEN sign for each workplace; everyone in the room sees what each player switches on. **My robot** (main menu or break room) lets you design your own robot customer: pick its body and screen colours, head shape (Classic, Wide, Tall, Round) and a hat (antenna, handle, propeller, top hat, party hat, crown, cat ears, flower, chef hat or none). It visits your room now and then with your name on it, and everyone in the room sees it. Special customers show up later in a shift: a 👑 VIP orders more and pays double, and a ⚡ speedy customer pays 1.5x if you serve them within 45 seconds (never a penalty if you are slower).

Watch and photos: the 👁 button (or V) lets you orbit the workplace while you take a breather, and 📷 (or P) takes a polaroid photo with your coins, served count and stars that you can save or share.

Main menu: **Host an online game** gives you a room code (and a link) to share, **Play solo** starts a shift right away, and friends enter a code under **Join**. **Settings** (music, song, sound effects, robot voices, graphics, automatic SD on slow phones, full screen, look speed, tips, and on phones a large Use button and vibration) is in the main menu and behind the gear button during a shift.

Music: the Block Buddies songs from this site's `music` folder. Skyline Exploration is packed into the page, and the other three (Gliding Over Green Valleys, Quiet Horizons, Subtle Quests and Flying Capes) stream from `../music/`. Each workplace has its own song on Automatic, or pick one in Settings.

Online play: friends enter the code under Join. Players connect directly to each other (WebRTC through Trystero, using public matchmaking relays), so there is no game server. The host picks the workplace in the lobby. Some strict networks block direct connections.

The whole game is bundled in `index.html`, including the 3D models. Three.js, Trystero and the fonts load from public CDNs.

Full screen: the Full screen button works on desktop, Android and iPad. iPhone browsers do not allow it, so tap Share, then Add to Home Screen, and open Shift Squad from your home screen for a full-screen app.
