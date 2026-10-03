# Sparkle Kingdom

Princess Luna's 3D adventure, made for a 5-year-old. **Play:** https://ahamze123.github.io/luna/

Luna walks around her kingdom and helps her friends, island by island. Like Block Buddies, she moves only with the pink motion stick on the left (it jumps to wherever a finger touches the left side) and the camera swings round behind her as she walks; dragging on the right side turns the camera, and a tap on Luna or a friend makes them twirl or say hello (arrow keys or WASD and the space bar on a computer). The game waits on its start screen until **Start game** (or **Continue**) is tapped, and **Full screen** fills the screen (on an iPad or iPhone it explains Add to Home Screen instead). Everything is read aloud, so she doesn't need to read.

## The adventure: 28 missions in four lands

A sparkly trail and a golden arrow always lead to the next friend or thing to find, across the rainbow bridges too. Every mission gives a sticker, many end with an easy question (after two wrong tries the right answer glows), and the four parties and the Grand Ball fill the five gems of Luna's crown.

- **Sparkle Kingdom** (the castle island): Bun-Bun's carrots, hide-and-seek with baby Pip, apples for Dot, falling stars for Stardust, watering Bun-Bun's garden, a butterfly game with Pip, Dot's birthday (balloons and a cake), a ride on Stardust through rainbow rings, lost baby bunnies, balls of yarn for Mimi, painted eggs, a flower crown, and the lanterns for the **Sparkle Party**. After the party Pip follows Luna like a pet, and a rainbow bridge opens.
- **Rainbow Beach** with Shelly the turtle and Marina the mermaid: baby turtles to the sea, a pearl hunt, seashells for the nest, a sandcastle that grows with every starfish, and a beach party with umbrellas.
- **Candy Forest** with Honey the bear baker: find the cake ingredients and decorate the cake, lollipops, runaway gingerbread cookies, and a cupcake party.
- **Snowy Hill** with Pingo the penguin: build a snowman, catch fish at the ice pond, sledding down the hill through the flags, little lost penguins, and a snowflake party.
- **The Grand Ball** at the castle with every friend, fireworks and the Rainbow dress.

**After the Grand Ball the game keeps going:** the friends ask for help again and again (carrots, eggs, balloons, stars, yarn, flowers, butterflies, seashells, pearls, starfish, lollipops, cupcakes, cookies, fish, snowballs), hidden in new places every time, each with a counting question, and every two helper missions a new dress (Peach, Ocean, Berry, Sunny, Lime, Violet). If she stands still for half a minute in the middle of a mission, the mission is said again.

After Stardust's ride Luna can ride the unicorn anywhere (Ride / Get off button). The menu (☰) has full screen, music, a photo of the game, the sticker book, a **dance party** (Luna dances, the friends nearby hop along, sparkles and fireworks), the **magic map** to jump between the lands that are open, and Start over (it has to be held down, so a little tap can't wipe the adventure).

## Luna's room

The 🏰 button (or **Go in** at the castle door) opens Luna's room:

- **Dress up**: 17 dresses, crowns, wings, wands and a pearl necklace; she wears them in the game too. Some are surprises won on the adventure.
- **Makeup mirror**: lipstick, cheeks, eye shadow, glitter, four hairstyles (curls, pigtails, bun, braid), hair colours including rainbow, bows, and face stickers.
- **Pip's bath**: scrub the mud with the sponge, rinse the bubbles, dry with the towel.
- **Piano**: play anything, or follow the shining key for Twinkle Twinkle, Mary's little lamb and Row your boat.
- **Painting**: two colouring pages (tap a space to fill it) and a blank page with a brush.
- **Bedtime**: five read-aloud stories with a lullaby, then morning or night time in the kingdom (night has stars and fireflies).
- **Memory game**: turn two cards over and find the pairs of friends, from 6 cards up to 16.
- **Day / night** window, the teddy to hug, the fairy lights, the sticker book and the photo album (photos from the wardrobe, the mirror, the painting easel or the game can be saved to the tablet).

Seven room activities give stickers too (35 stickers in all).

## Pictures and models

Luna and her friends were drawn by the family in ChatGPT and turned into 3D with Meshy (Meshy runs 14 to 18 in `tools/meshy`): `models/luna.glb` has Luna's skeleton and moves (walk, skip, run, jump, wave, cheer, dance, sit, pick up, swim); the friends, the castle, cottage, trees, flowers, beach things and the things to collect are models that the game moves. The room, the dress-up doll, the hairstyles, the dress-up items and the colouring pages are pictures in `img/`. If a model can't load, the game draws a simple stand-in.

`index.html` is the whole game (three.js 0.147 and its model loader are in `lib/`, so it needs no other website). Progress, clothes, makeup and photos are saved on the tablet (`luna-sk-v2`, photos in `luna-sk-photos`); a save from the first version carries over.
