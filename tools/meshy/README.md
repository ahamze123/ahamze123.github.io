# 3D heroes from the family's pictures

`pics/` has a standing picture of every hero (one hero, whole body, plain white background), made from their hero cards.
The GitHub job **Make 3D heroes (Meshy)** (`.github/workflows/meshy.yml`) turns them into 3D models with
[Meshy](https://www.meshy.ai): image to 3D, then a skeleton (rigging) and animations. It runs when `queue.json` changes
on `main`, and it needs the repository secret `MESHY_API_KEY` (Settings › Secrets and variables › Actions).

The results go to the branch `meshy-out`, not to the game: `state.json` (every Meshy task, so nothing is paid twice),
`log.txt`, and per hero `thumb.png`, `model.glb`, `walk.glb`, `run.glb` and `anims.glb`. Models are checked there first,
then put into the game's `models/` folder.

`queue.json`:
- `run`: a number; change it to start the job again.
- `heroes`: the heroes to make (a hero that is already done is skipped).
- `max_credits`: the most this run may spend (about 30 credits a model, 5 a skeleton, 3 an animation).
- `model`, `rig`: Meshy settings. `per`: settings for one hero (for example `{"aya": {"target_polycount": 25000}}`).
- `anims`: `heroes` that get animations, and the library `action_ids` (up to 10).
- `redo`: heroes whose model should be made again (costs credits again).

`glbtool.py` makes the pictures inside a model smaller, keeps only the skeleton and clips, and copies clips from one
model to another (`python3 glbtool.py` for help).
