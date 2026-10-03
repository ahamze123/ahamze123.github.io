"""Makes the recorded voices for Sparkle Kingdom (luna/) with the Kokoro voice generator (open, runs on the computer, no account).

Reads tools/voices/lines.json ([{"who": ..., "text": ...}]) and writes one small mp3 per line to $VOICE_OUT/<hash>.mp3, where
hash = FNV-1a (32 bit, hex) of "who|text" -- the game computes the same name to find the line. Lines already made are skipped,
so adding new lines only makes the new ones. Each friend has their own voice (CAST below).
"""
import json, os, sys, subprocess, time
import numpy as np
from kokoro_onnx import Kokoro

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("VOICE_OUT", os.path.join(HERE, "out"))
MODEL = os.environ.get("KOKORO_MODEL", "kokoro-v1.0.onnx"); VOICES = os.environ.get("KOKORO_VOICES", "voices-v1.0.bin")
# who: (Kokoro voice, speed, pitch in semitones)
CAST = {
    "narrator": ("af_heart", 0.95, 0.0), "story": ("af_heart", 0.86, 0.0), "luna": ("af_bella", 1.0, 1.5),
    "bunny": ("am_puck", 1.05, 2.5), "mimi": ("bf_emma", 0.95, 0.0), "pip": ("af_sky", 1.05, 3.5), "dot": ("am_echo", 1.0, 3.0),
    "stardust": ("af_nova", 0.95, 0.5), "shelly": ("bf_isabella", 0.88, 0.0), "marina": ("af_aoede", 1.0, 1.0),
    "honey": ("af_sarah", 0.95, -0.5), "pingo": ("am_fenrir", 1.05, 4.0),
}
def vhash(s):
    h = 0x811c9dc5
    for x in s.encode("utf-8"):
        h ^= x; h = (h * 0x01000193) & 0xffffffff
    return "%08x" % h
def main():
    lines = json.load(open(os.path.join(HERE, "lines.json")))
    os.makedirs(OUT, exist_ok=True)
    k = Kokoro(MODEL, VOICES)
    made = skipped = failed = 0; t0 = time.time(); index = {}
    for n, it in enumerate(lines):
        who = it["who"] if it["who"] in CAST else "narrator"; text = it["text"].strip()
        h = vhash(who + "|" + text); path = os.path.join(OUT, h + ".mp3")
        index[h] = who + "|" + text
        if os.path.exists(path) and os.path.getsize(path) > 500: skipped += 1; continue
        voice, speed, pitch = CAST[who]
        try:
            samples, sr = k.create(text, voice=voice, speed=speed, lang="en-us")
            a = np.asarray(samples, dtype=np.float32)
            # trim the quiet ends, keep a little breath, and make every line equally loud
            loud = np.where(np.abs(a) > 0.012)[0]
            if len(loud): a = a[max(0, loud[0] - int(0.04 * sr)): min(len(a), loud[-1] + int(0.12 * sr))]
            rms = float(np.sqrt(np.mean(a * a))) or 1e-4
            a = a * min(0.12 / rms, 0.95 / (float(np.max(np.abs(a))) or 1))
            af = []
            if abs(pitch) > 0.01:
                f = 2 ** (pitch / 12.0)
                af.append("asetrate=%d,aresample=%d,atempo=%.5f" % (round(sr * f), sr, 1 / f))
            cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0"]
            if af: cmd += ["-af", ",".join(af)]
            cmd += ["-c:a", "libmp3lame", "-b:a", "40k", "-ar", "24000", "-ac", "1", path]
            subprocess.run(cmd, input=a.astype(np.float32).tobytes(), check=True)
            made += 1
        except Exception as e:
            failed += 1; print("FAILED", who, repr(text), e, flush=True)
        if (n + 1) % 50 == 0: print("%d/%d lines, %.0fs" % (n + 1, len(lines), time.time() - t0), flush=True)
    json.dump(index, open(os.path.join(OUT, "index.json"), "w"), indent=0, ensure_ascii=False, sort_keys=True)
    print("made %d, already there %d, failed %d, in %.0fs" % (made, skipped, failed, time.time() - t0))
    if failed and not made: sys.exit(1)
if __name__ == "__main__":
    main()
