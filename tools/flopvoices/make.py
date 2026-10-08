"""Makes the recorded voices for Flop Island with the Kokoro voice generator (open, runs on the computer, no account, no payment).

Reads tools/flopvoices/lines.json ([{"who": ..., "text": ...}], written by test/v_collect.mjs in the game repo) and writes one small
mp3 per line to $VOICE_OUT/<hash>.mp3, where hash = FNV-1a (32 bit, hex) of the UTF-8 bytes of "who|text" -- the game (src/40b_voice.js)
computes the same name to find the line, so the text in lines.json must be exactly the text the game says.
Lines already made with the same settings are skipped (sig.json remembers the voice, speed, pitch and words each file was made
with), so adding new lines only makes the new ones, and changing a character's voice remakes only that character's lines.
Files of lines that are no longer in lines.json are removed. Every character has a Kokoro voice of their own (CAST below).

Needs: pip install kokoro-onnx soundfile numpy, ffmpeg, and the two model files (kokoro-v1.0.onnx, voices-v1.0.bin) from
https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0  (the workflow .github/workflows/flop-voices.yml does all of it).
"""
import json, os, re, sys, subprocess, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("VOICE_OUT", os.path.join(HERE, "out"))
MODEL = os.environ.get("KOKORO_MODEL", "kokoro-v1.0.onnx"); VOICES = os.environ.get("KOKORO_VOICES", "voices-v1.0.bin")
BITRATE = "48k"

# who: (Kokoro voice, speed, pitch in semitones) -- a little slow, for small children; the pitch makes the little ones squeak and the big ones rumble.
# The names are the speaker keys the game uses (src/98_voice_hooks.js). 27 different Kokoro v1.0 voices for 27 characters.
CAST = {
    # the story and the islanders
    "mayor":        ("af_heart",    0.90,  0.5),   # Mayor Pip, the pup in the top hat: warm, kind, the voice of the story
    "depotBoss":    ("af_nova",     1.00,  4.5),   # Dot the Postie, the duck: squeaky, quick
    "police":       ("am_michael",  0.90, -1.5),   # Officer Bun, a big friendly bear: deep and kind
    "vendor":       ("af_sky",      0.95,  2.5),   # Coco, the juice bunny: sweet and young
    "pizza":        ("bm_fable",    0.95,  0.5),   # Chef Pepe, the jolly pig: a storyteller's flourish
    "farmer":       ("af_sarah",    0.92, -1.0),   # Farmer Fern, the frog: warm and calm
    "foreman":      ("am_onyx",     0.95, -0.5),   # Foreman Rex, the bear in the hard hat: deep, hearty
    "firechief":    ("am_echo",     0.95,  0.5),   # Captain Splash, the pup in the fire helmet: brave
    "guide":        ("bm_george",   0.92, -0.5),   # Guide Gil, the panda explorer: calm, adventurous
    "lifeguard":    ("af_kore",     0.98,  0.5),   # Lifeguard Lu, the kitty: sporty, cheerful
    "official":     ("am_liam",     1.00,  1.0),   # Ace, the fox at the race track: young, quick, cool
    "host":         ("am_puck",     1.00,  3.0),   # Hoppy, the pink bunny with the propeller hat: bouncy game-show host
    "coach":        ("am_eric",     0.98,  0.0),   # Coach Bo, the pup with headphones: encouraging
    "sam":          ("bm_daniel",   1.00,  2.0),   # Sneaky Sam, the fox in the beanie: sheepish
    "grumble":      ("am_fenrir",   0.94, -1.5),   # Boss Grumble, the big grumpy raccoon: gruff but funny, never scary
    "grumbleHappy": ("am_fenrir",   1.02,  0.5),   # ... the same Boss Grumble once he has been invited to the party: lighter, happier
    "jobs":         ("af_jessica",  0.98,  0.0),   # the Job Center
    # Museum Isle
    "curator":      ("bf_emma",     0.88,  0.5),   # Curator Clara, the kitty: gentle, a little posh
    "fisher":       ("bm_lewis",    0.92, -1.0),   # Fishmonger Finn, the bear: hearty
    "tackle":       ("am_santa",    0.95,  0.5),   # the tackle shop: jolly
    # Pine Hills and the shops
    "mabel":        ("bf_isabella", 0.88,  0.0),   # Mabel, the panda of the Furniture Shop (and the houses): cosy
    "waggles":      ("af_nicole",   0.90,  0.0),   # Dr. Waggles, the pup in the Pet Shop: soft and gentle
    "hatshop":      ("bf_alice",    0.95,  0.5),   # the Hat Shop
    "clothes":      ("af_river",    0.95,  1.0),   # Fluff and Stuff
    "carshop":      ("af_aoede",    0.95,  0.0),   # the Car Shop
    # the Space Center, the brawls, and the game itself
    "control":      ("af_alloy",    0.95,  0.0),   # Mission Control: crisp countdown
    "announcer":    ("af_bella",    1.00,  1.0),   # the brawl announcer: bright and hyped
    "narrator":     ("bf_lily",     0.95,  0.0),   # the game (the "Voices are on!" switch); also used for anyone not in this list
}
SAME_VOICE = {"grumbleHappy": "grumble"}   # one character, two moods: the only pair that may share a voice
SAY_AS = {}   # a written text that is read badly -> how to say it (it is replaced before the voice reads it), e.g. {"Hmph": "Humph"}
VERSION = 3   # bump to remake every line

def vhash(s):
    h = 0x811c9dc5
    for x in s.encode("utf-8"):
        h ^= x; h = (h * 0x01000193) & 0xffffffff
    return "%08x" % h

def spoken(text):
    for a, b in SAY_AS.items(): text = text.replace(a, b)
    return text

def check_cast():
    assert vhash("") == "811c9dc5" and vhash("a") == "e40c292c", "the hash is not FNV-1a"
    names = np.load(VOICES, allow_pickle=False).files
    bad = sorted({v for v, _, _ in CAST.values()} - set(names))
    if bad: sys.exit("not in %s: %s" % (VOICES, ", ".join(bad)))
    own = [v for w, (v, _, _) in CAST.items() if w not in SAME_VOICE]
    dup = sorted({v for v in own if own.count(v) > 1})
    if dup: sys.exit("voices used by two characters: " + ", ".join(dup))

def main():
    from kokoro_onnx import Kokoro
    lines = json.load(open(os.path.join(HERE, "lines.json"), encoding="utf-8"))
    check_cast()
    os.makedirs(OUT, exist_ok=True)
    k = Kokoro(MODEL, VOICES)
    made = skipped = failed = 0; t0 = time.time(); index = {}; warned = set(); gb_ok = True
    sig_path = os.path.join(OUT, "sig.json")
    sigs = json.load(open(sig_path)) if os.path.exists(sig_path) else {}
    for n, it in enumerate(lines):
        who = it["who"]; text = it["text"].strip()
        if who not in CAST and who not in warned: warned.add(who); print("WARNING: no voice for", who, "-> using the narrator's", flush=True)
        voice, speed, pitch = CAST.get(who, CAST["narrator"])
        h = vhash(who + "|" + text); path = os.path.join(OUT, h + ".mp3")
        assert index.get(h, who + "|" + text) == who + "|" + text, "two lines have the same hash: %s" % h
        index[h] = who + "|" + text
        say = spoken(text); sig = "%s|%s|%s|%d|%s" % (voice, speed, pitch, VERSION, say)
        if os.path.exists(path) and os.path.getsize(path) > 500 and sigs.get(h) == sig: skipped += 1; continue
        try:
            lang = "en-gb" if voice[0] == "b" and gb_ok else "en-us"   # (British voices speak with British sounds)
            try:
                samples, sr = k.create(say, voice=voice, speed=speed, lang=lang)
            except Exception as e:
                if lang != "en-gb": raise
                gb_ok = False; print("en-gb not accepted (%r), British voices use en-us" % e, flush=True)
                samples, sr = k.create(say, voice=voice, speed=speed, lang="en-us")
            a = np.asarray(samples, dtype=np.float32).reshape(-1)
            # trim the quiet ends, keep a little breath, and make every line equally loud
            loud = np.where(np.abs(a) > 0.012)[0]
            if len(loud): a = a[max(0, loud[0] - int(0.04 * sr)): min(len(a), loud[-1] + int(0.12 * sr))]
            if len(a) < int(0.1 * sr) or not len(loud): raise ValueError("the voice made no sound")
            rms = float(np.sqrt(np.mean(a * a))) or 1e-4
            a = a * min(0.12 / rms, 0.95 / (float(np.max(np.abs(a))) or 1))
            fi, fo = int(0.006 * sr), int(0.04 * sr)   # (no clicks at the ends)
            if len(a) > fi + fo: a[:fi] *= np.linspace(0, 1, fi, dtype=np.float32); a[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
            af = []
            if abs(pitch) > 0.01:
                f = 2 ** (pitch / 12.0)
                af.append("asetrate=%d,aresample=%d,atempo=%.5f" % (round(sr * f), sr, 1 / f))
            tmp = path + ".part.mp3"
            cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0"]
            if af: cmd += ["-af", ",".join(af)]
            cmd += ["-c:a", "libmp3lame", "-b:a", BITRATE, "-ar", "24000", "-ac", "1", tmp]
            subprocess.run(cmd, input=a.astype(np.float32).tobytes(), check=True)
            os.replace(tmp, path)
            sigs[h] = sig; made += 1
        except Exception as e:
            failed += 1; print("FAILED", who, repr(text), e, flush=True)
        if (n + 1) % 25 == 0:
            print("%d/%d lines, %.0fs" % (n + 1, len(lines), time.time() - t0), flush=True)
            json.dump(sigs, open(sig_path, "w"), indent=0, sort_keys=True)   # kept as it goes, in case the run stops
    # lines that are gone (a text was changed) leave no old files behind
    gone = 0
    for f in os.listdir(OUT):
        m = re.fullmatch(r"([0-9a-f]{8})\.mp3", f)
        if m and m.group(1) not in index: os.remove(os.path.join(OUT, f)); sigs.pop(m.group(1), None); gone += 1
    json.dump(index, open(os.path.join(OUT, "index.json"), "w"), indent=0, ensure_ascii=False, sort_keys=True)
    json.dump({h: s for h, s in sigs.items() if h in index}, open(sig_path, "w"), indent=0, sort_keys=True)
    size = sum(os.path.getsize(os.path.join(OUT, h + ".mp3")) for h in index if os.path.exists(os.path.join(OUT, h + ".mp3")))
    print("made %d, already there %d, failed %d, removed %d old, %d files %.1f MB, in %.0fs" % (made, skipped, failed, gone, len(index) - failed, size / 1e6, time.time() - t0))
    if failed: sys.exit(1)

if __name__ == "__main__":
    main()
