# Sparkle Kingdom

Princess Luna's 3D adventure, made for a 5-year-old. **Play:** https://ahamze123.github.io/luna/

Luna walks around a little island kingdom (tap the ground, or hold a finger down to steer; arrow keys or WASD on a computer) and helps five friends get ready for the Sparkle Party. Everything is read aloud, so she doesn't need to read.

1. **Bun-Bun** the bunny: find 5 carrots.
2. **Mimi** the cat: find her lost kitten **Pip** by the red mushrooms and bring her home.
3. **Dot** the baby dragon: walk to the apple tree, it drops 3 apples, take them to Dot.
4. **Stardust** the unicorn: catch 5 fallen stars.
5. Light the 4 lanterns at the castle, then the **Sparkle Party** starts (fireworks, everyone dances).

Each friend asks one easy question before giving a gem for Luna's crown (count the carrots, pick Pip's face, the colour of apples, which one is a star); after two wrong tries the right answer glows. After the party Pip comes along as Luna's pet.

From Block Buddies: the glowing trail and golden arrow that lead the way, trees that turn see-through around Luna, the camera that looks ahead, the Block Buddies songs (from `../music`, with a music box when offline), the most natural voice the tablet has, quiet walking, fireworks for every prize, a picture that gets softer by itself on a slow tablet, and Add to Home Screen (it opens full screen, with its own icon and save).

## Pictures and models

Luna and her friends were drawn by the family in ChatGPT and turned into 3D with Meshy (Meshy runs 14 and 15 in `tools/meshy`): `models/luna.glb` has Luna's skeleton and moves (walk, skip, run, idle, sway, jump, happy jump, wave, cheer, dance); the animals, the castle, cottage, trees, flowers and the things to collect are still models that the game moves. If a model can't load, the game draws a simple stand-in.

`index.html` is the whole game (three.js 0.147 from jsDelivr). Progress is saved on the tablet (`luna-sparkle-kingdom-v1`).
