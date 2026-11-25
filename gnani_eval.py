#!/usr/bin/env python3
"""
Gnani.ai take-home — evaluation of Prisma (ASR) and Timbre (TTS).

Every step caches to disk, so re-running never re-spends API credits.

    python gnani_eval.py smoke-test     # 3 API calls: checks key, TTS and both STT models
    python gnani_eval.py prepare-asr    # FLEURS clips + noisy / telephony / long variants + own recordings
    python gnani_eval.py run-asr        # Prisma v2.5 and v3.0 -> cache/asr/
    python gnani_eval.py score-asr      # WER/CER, category tables, plots, error analysis -> results/
    python gnani_eval.py run-tts        # Timbre v2.5 and v3.0, REST + SSE latency probes -> cache/tts*/
    python gnani_eval.py score-tts      # intelligibility (Whisper), UTMOS, prosody, latency/RTF -> results/
    python gnani_eval.py all            # everything in order

Set the key first:  export GNANI_API_KEY=...
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# =============================================================================
# 1. CONFIG
# =============================================================================
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ASR_DIR = DATA_DIR / "asr"
OWN_DIR = DATA_DIR / "own_recordings"
CACHE_DIR = ROOT / "cache"
RESULTS_DIR = ROOT / "results"
MANIFEST = ASR_DIR / "manifest.csv"
OWN_MANIFEST = OWN_DIR / "manifest_own.csv"
TTS_SENTENCES = DATA_DIR / "tts_sentences.csv"
LISTENING_FILLED = DATA_DIR / "tts_listening_filled.csv"

BASE_URL = "https://api.vachana.ai"
STT_URL = f"{BASE_URL}/stt/v3"
TTS_URL = f"{BASE_URL}/api/v1/tts/inference"
TTS_SSE_URL = f"{BASE_URL}/api/v1/tts/sse"

SR = 16000
ASR_MODELS = ["prisma-v2.5", "prisma-v3.0"]
TTS_MODELS = ["timbre-v2.5", "timbre-v3.0"]

# FLEURS (test split): language -> (config name, clean clips, extra clips for babble/long)
# FLEURS has no Indian-English config, only en_us: Indian-accented English coverage
# instead comes from the own recordings (see README Limitations).
FLEURS = {
    "en-IN": ("en_us", 12, 12),
    "hi-IN": ("hi_in", 10, 0),
    "ta-IN": ("ta_in", 10, 12),
}
NOISY_LANGS = ["en-IN", "ta-IN"]   # languages that get noisy + telephony variants
N_NOISY = 6                        # base clips per language for noise / telephony
SNRS_DB = [10, 5, 0]               # babble SNR levels
BABBLE_TALKERS = 4

# One fixed voice per language for v2.5 (voices are language-specific there).
# One voice for every language on v3.0 (all v3.0 voices speak all languages):
# keeps speaker identity constant, so language differences are not voice differences.
TTS_VOICES = {
    "timbre-v2.5": {"en-IN": "Kaveri", "hi-IN": "Nalini", "ta-IN": "Vedika", "hi-en": "Poorvi"},
    "timbre-v3.0": {"en-IN": "Sunaina", "hi-IN": "Sunaina", "ta-IN": "Sunaina", "hi-en": "Sunaina"},
}
SSE_RUNS = 3
NON_CACHEABLE = {401, 402, 403, 429}   # never freeze auth / credit / rate-limit failures into the cache
FATAL = {401: "invalid or missing API key", 402: "out of credits", 403: "key lacks scope for this service"}

MANIFEST_FIELDS = ["clip_id", "path", "language", "category", "subcategory", "snr_db", "base_id",
                   "source", "reference", "lang_hint_v3", "format_v3", "expected_entities",
                   "keyterms", "duration_s"]


# =============================================================================
# 2. SMALL HELPERS
# =============================================================================
def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def p50(x):
    x = [v for v in x if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(np.percentile(x, 50)) if x else float("nan")


def p95(x):
    x = [v for v in x if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return float(np.percentile(x, 95)) if x else float("nan")


def md_table(df, floatfmt=".3f"):
    if df is None or len(df) == 0:
        return "_(no rows)_\n"
    return df.to_markdown(index=False, floatfmt=floatfmt) + "\n"


# =============================================================================
# 3. API CLIENT (sequential, retry with backoff, disk cache)
# =============================================================================
def _headers(json_body=False):
    key = os.environ.get("GNANI_API_KEY")
    if not key:
        sys.exit("Set GNANI_API_KEY first (export GNANI_API_KEY=...).")
    h = {"X-API-Key-ID": key}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _request(method, url, max_tries=6, **kw):
    """One HTTP call with retry on 429 / 5xx / network errors.
    The account allows one active request at a time, so we never parallelise."""
    import requests
    last_err = None
    for attempt in range(max_tries):
        t0 = time.perf_counter()
        try:
            r = requests.request(method, url, timeout=120, **kw)
        except requests.RequestException as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
            continue
        dt = time.perf_counter() - t0
        if r.status_code in (429, 500, 502, 503, 504) and attempt < max_tries - 1:
            time.sleep(min(2 ** attempt, 30))
            continue
        return r, dt
    raise RuntimeError(f"Request failed after {max_tries} tries: {last_err}")


def _check_fatal(status):
    if status in FATAL:
        sys.exit(f"Stopping: HTTP {status} — {FATAL[status]}.")


def cached_json(path, fn):
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out = fn()
    _check_fatal(out.get("status"))
    if out.get("status") not in NON_CACHEABLE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def prisma_transcribe(wav_path, model, language_code, fmt, extra=None):
    import soundfile as sf
    data = {"language_code": language_code, "format": fmt}
    if model != "prisma-v2.5":          # v2.5 is the default: leave `model` out
        data["model"] = model
    data.update(extra or {})
    audio = Path(wav_path).read_bytes()  # bytes, so a retry re-sends the full file
    r, dt = _request("POST", STT_URL, headers=_headers(),
                     files={"audio_file": (Path(wav_path).name, audio, "audio/wav")}, data=data)
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:500]}
    return {"status": r.status_code, "body": body, "client_latency_s": dt, "request": data,
            "audio_duration_s": sf.info(str(wav_path)).duration}


def tts_payload(text, model, language, voice):
    # container=raw gives headerless 16-bit PCM: we write the WAV header ourselves,
    # so duration measurement never depends on how the server fills the header.
    return {"text": text, "voice": voice, "model": model, "language": language, "speed": 1.0,
            "audio_config": {"sample_rate": SR, "num_channels": 1, "sample_width": 2,
                             "encoding": "linear_pcm", "container": "raw"}}


def pcm_to_wav(audio_bytes, path):
    import soundfile as sf
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio_bytes[:4] == b"RIFF":              # server sent a WAV anyway
        path.write_bytes(audio_bytes)
    else:
        n = len(audio_bytes) // 2 * 2
        y = np.frombuffer(audio_bytes[:n], dtype="<i2").astype(np.float32) / 32768.0
        sf.write(str(path), y, SR, subtype="PCM_16")
    return sf.info(str(path)).duration


def timbre_rest(payload):
    r, dt = _request("POST", TTS_URL, headers=_headers(True), json=payload)
    ctype = r.headers.get("content-type", "")
    if r.status_code == 200 and "application/json" not in ctype:
        return {"status": 200, "client_latency_s": dt, "bytes": len(r.content), "content_type": ctype}, r.content
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:500]}
    return {"status": r.status_code, "client_latency_s": dt, "error": body}, None


def consume_sse(lines, t0):
    """Parse an SSE stream of `event:` / `data:` lines.
    Returns (time_to_first_audio_s, pcm_bytes, error_or_None)."""
    ttfa, pcm, event, err = None, bytearray(), None, None
    for raw in lines:
        if not raw:
            continue
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            event = line[6:].strip()
            continue
        if not line.startswith("data:"):
            continue
        try:
            d = json.loads(line[5:].strip())
        except ValueError:
            continue
        if event == "error":
            err = d
            break
        audio = d.get("audio") or ""
        if audio:
            if ttfa is None:
                ttfa = time.perf_counter() - t0
            pcm += base64.b64decode(audio)
        if d.get("is_final") or event == "complete":
            break
    return ttfa, bytes(pcm), err


def timbre_sse(payload, max_tries=6):
    import requests
    for attempt in range(max_tries):
        t0 = time.perf_counter()
        try:
            with requests.post(TTS_SSE_URL, headers=_headers(True), json=payload,
                               stream=True, timeout=120) as r:
                if r.status_code in (429, 500, 502, 503, 504) and attempt < max_tries - 1:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                if r.status_code != 200:
                    return {"status": r.status_code, "error": r.text[:300]}
                ttfa, pcm, err = consume_sse(r.iter_lines(), t0)
        except requests.RequestException as e:
            if attempt == max_tries - 1:
                return {"status": -1, "error": str(e)}
            time.sleep(min(2 ** attempt, 30))
            continue
        total = time.perf_counter() - t0
        dur = len(pcm) / 2 / SR
        return {"status": 200, "ttfa_s": ttfa, "total_s": total, "audio_s": dur,
                "rtf": total / dur if dur else None, "error": err}
    return {"status": 429, "error": "rate limited"}


# =============================================================================
# 4. TEXT NORMALISATION (applied identically to reference and hypothesis)
# =============================================================================
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)
_CURRENCY_WORD = {"en": "rupees", "hi": "रुपये", "ta": "ரூபாய்"}
_PERCENT_WORD = {"en": "percent", "hi": "प्रतिशत", "ta": "சதவீதம்"}
_DIGIT_WORDS = "zero one two three four five six seven eight nine".split()


def lang2(code):
    return code.split("-")[0].lower()        # "en-IN" -> "en", "hi-en" -> "hi"


def _en_number(n):
    from num2words import num2words
    s = num2words(n, lang="en_IN")
    s = re.sub(r"[-,]", " ", s)
    return re.sub(r"\band\b", " ", s)          # "one hundred and five" == "one hundred five"


def expand_numbers_en(t):
    from num2words import num2words
    t = re.sub(r"\b(\d+)(st|nd|rd|th)\b",
               lambda m: num2words(int(m.group(1)), to="ordinal").replace("-", " "), t)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b",
               lambda m: _en_number(int(m.group(1))) +
               ("" if int(m.group(2)) == 0 else " " + _en_number(int(m.group(2)))), t)

    def repl(m):
        s = m.group(0)
        if "," in s:                                   # 1,25,000 -> cardinal
            return " " + _en_number(int(s.replace(",", ""))) + " "
        if "." in s:                                   # 3.5 -> three point five
            a, b = s.split(".")
            return f" {_en_number(int(a))} point {' '.join(_DIGIT_WORDS[int(c)] for c in b)} "
        if len(s) >= 5:                                # long digit strings are IDs / phones
            return " " + " ".join(_DIGIT_WORDS[int(c)] for c in s) + " "
        if len(s) == 4 and 1900 <= int(s) <= 2099:     # years
            return " " + num2words(int(s), to="year").replace("-", " ") + " "
        return " " + _en_number(int(s)) + " "

    return re.sub(r"\d+(?:,\d+)*(?:\.\d+)?", repl, t)


def strip_punct(t):
    # keep letters (L), combining marks (M: Indic vowel signs) and numbers (N)
    return "".join(ch if (unicodedata.category(ch)[0] in "LMN" or ch.isspace()) else " " for ch in t)


_EN_ABBR = {"dr": "doctor", "mr": "mister", "mrs": "missus", "ms": "miss", "st": "saint", "rd": "road"}


def join_spelled_letters(t):
    """'k y c' and 'KYC' must compare equal: join runs of single Latin letters."""
    out, run = [], []
    for tok in t.split():
        if len(tok) == 1 and "a" <= tok <= "z":
            run.append(tok)
            continue
        out.append("".join(run) if len(run) > 1 else (run[0] if run else ""))
        out.append(tok)
        run = []
    out.append("".join(run) if len(run) > 1 else (run[0] if run else ""))
    return " ".join(x for x in out if x)


def normalize(text, language):
    """Normalised form used for the headline WER/CER."""
    lg = lang2(language)
    t = unicodedata.normalize("NFC", text or "").translate(_ZERO_WIDTH).lower()
    cur = _CURRENCY_WORD.get(lg, "rupees")
    t = re.sub(r"(?:₹|\brs\.?|\binr)\s*(\d+(?:,\d+)*(?:\.\d+)?)", rf"\1 {cur}", t)
    t = t.replace("%", f" {_PERCENT_WORD.get(lg, 'percent')} ")
    if lg == "en":
        t = t.replace("&", " and ").replace("@", " at ").replace("+", " plus ")
        t = re.sub(r"(?<=[a-z])\.(?=[a-z])", " dot ", t)          # emails / URLs
        t = re.sub(r"(?<=[a-z0-9])/(?=[a-z])", " slash ", t)
        t = re.sub(r"\b([ap])\.?\s?m\b\.?", r"\1 m", t)          # 3:30 PM / p.m.
        t = re.sub(r"\b(" + "|".join(_EN_ABBR) + r")\b\.?", lambda m: _EN_ABBR[m.group(1)], t)
        t = expand_numbers_en(t)
    if lg == "hi":                       # common Hindi spelling variants
        t = t.replace("\u093c", "").replace("\u0901", "\u0902")   # nukta; chandrabindu -> anusvara
    t = re.sub(r"\s+", " ", strip_punct(t)).strip()
    return join_spelled_letters(t) if lg == "en" else t


def normalize_raw(text):
    """Minimal normalisation: what a customer sees out of the box."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


# =============================================================================
# 5. METRICS — own implementation (no library scorer)
#    WER = (S + D + I) / N over words, CER = same over characters.
# =============================================================================
def align(ref, hyp):
    """Levenshtein alignment with backtrace.
    Returns counts {S, D, I, H, N} and the list of edit operations."""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i, j] = min(d[i - 1, j - 1] + cost,   # match / substitution
                          d[i - 1, j] + 1,          # deletion
                          d[i, j - 1] + 1)          # insertion
    S = D = I = H = 0
    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] == hyp[j - 1]:
                H += 1
                ops.append(("C", ref[i - 1], hyp[j - 1]))
            else:
                S += 1
                ops.append(("S", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i, j] == d[i - 1, j] + 1:
            D += 1
            ops.append(("D", ref[i - 1], ""))
            i -= 1
        else:
            I += 1
            ops.append(("I", "", hyp[j - 1]))
            j -= 1
    ops.reverse()
    return {"S": S, "D": D, "I": I, "H": H, "N": n}, ops


def error_rate(c):
    if c["N"] == 0:
        return 0.0 if (c["I"] == 0) else 1.0
    return (c["S"] + c["D"] + c["I"]) / c["N"]


def wer_counts(ref_text, hyp_text):
    return align(ref_text.split(), hyp_text.split())


def cer_counts(ref_text, hyp_text):
    return align(list(ref_text), list(hyp_text))[0]


def corpus_rate(df, prefix):
    """Corpus-level rate: total errors / total reference units (not a mean of clip rates,
    which would let a 2-word clip weigh as much as a 40-word clip)."""
    n = df[f"{prefix}_N"].sum()
    e = (df[f"{prefix}_S"] + df[f"{prefix}_D"] + df[f"{prefix}_I"]).sum()
    return float(e / n) if n else float("nan")


# =============================================================================
# 6. AUDIO UTILITIES
# =============================================================================
def load_audio(path, sr=SR):
    import librosa
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    return y.astype(np.float32)


def save_wav(path, y, sr=SR):
    import soundfile as sf
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(y, -1, 1), sr, subtype="PCM_16")


def fit_length(x, n):
    if len(x) < n:
        x = np.tile(x, int(np.ceil(n / len(x))))
    return x[:n]


def mix_at_snr(clean, noise, snr_db):
    noise = fit_length(noise, len(clean))
    ps = np.mean(clean ** 2)
    pn = np.mean(noise ** 2) + 1e-12
    noise = noise * np.sqrt(ps / (pn * 10 ** (snr_db / 10)))
    mix = clean + noise
    peak = np.max(np.abs(mix))
    return (mix * 0.99 / peak if peak > 0.99 else mix).astype(np.float32)


def make_babble(clips, n):
    """Babble noise = several other talkers summed (call-centre style background)."""
    tracks = []
    for k, c in enumerate(clips):
        c = np.roll(fit_length(c, n), k * SR // 3)
        tracks.append(c / (np.sqrt(np.mean(c ** 2)) + 1e-9))
    return (np.sum(tracks, axis=0) / len(tracks)).astype(np.float32)


def telephony(y, sr=SR):
    """Simulate a phone line: 300–3400 Hz band-pass, 8 kHz, G.711 µ-law round trip."""
    from scipy.signal import butter, resample_poly, sosfilt
    sos = butter(6, [300, 3400], btype="band", fs=sr, output="sos")
    y = sosfilt(sos, y)
    y8 = resample_poly(y, 8000, sr)
    y8 = np.clip(y8 / (np.max(np.abs(y8)) + 1e-9) * 0.9, -1, 1)
    mu = 255.0
    enc = np.sign(y8) * np.log1p(mu * np.abs(y8)) / np.log1p(mu)
    q = np.round((enc + 1) / 2 * mu) / mu * 2 - 1           # 8-bit quantisation
    dec = np.sign(q) * np.expm1(np.abs(q) * np.log1p(mu)) / mu
    return dec.astype(np.float32), 8000


def concat_clips(items, min_s, max_s, gap_s=0.4):
    gap = np.zeros(int(gap_s * SR), dtype=np.float32)
    parts, refs, dur = [], [], 0.0
    for it in items:
        d = len(it["audio"]) / SR
        if dur + d > max_s:
            continue
        parts += [it["audio"], gap]
        refs.append(it["reference"])
        dur += d + gap_s
        if dur >= min_s:
            break
    return np.concatenate(parts), " ".join(refs), dur


# =============================================================================
# 7. PREPARE ASR TEST SET
# =============================================================================
def fetch_fleurs(cfg, n):
    import librosa
    from datasets import load_dataset
    ds = load_dataset("google/fleurs", cfg, split="test", streaming=True, trust_remote_code=True)
    out, seen = [], set()
    for ex in ds:
        if ex["id"] in seen:
            continue
        a = ex["audio"]
        y = np.asarray(a["array"], dtype=np.float32)
        sr = a["sampling_rate"]
        if not 3.0 <= len(y) / sr <= 20.0:
            continue
        seen.add(ex["id"])
        if sr != SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        out.append({"fleurs_id": ex["id"], "audio": y, "reference": ex["raw_transcription"]})
        if len(out) >= n:
            break
    return out


def _row(clip_id, path, language, category, reference, **kw):
    import soundfile as sf
    r = {k: "" for k in MANIFEST_FIELDS}
    r.update(clip_id=clip_id, path=str(Path(path).relative_to(ROOT)), language=language,
             category=category, reference=reference,
             duration_s=f"{sf.info(str(path)).duration:.2f}")
    r.update({k: str(v) for k, v in kw.items()})
    return r


def cmd_prepare_asr(args):
    rows = []
    for lang, (cfg, n_clean, n_extra) in FLEURS.items():
        print(f"[FLEURS] {cfg}: fetching {n_clean + n_extra} clips ...")
        pool = fetch_fleurs(cfg, n_clean + n_extra)
        clean, extra = pool[:n_clean], pool[n_clean:]
        tag = lang2(lang)

        for i, it in enumerate(clean):
            cid = f"{tag}_clean_{i:02d}"
            p = ASR_DIR / "clean" / f"{cid}.wav"
            save_wav(p, it["audio"])
            rows.append(_row(cid, p, lang, "clean", it["reference"], source=f"fleurs:{it['fleurs_id']}"))

        if lang not in NOISY_LANGS:
            continue

        babble_src = [e["audio"] for e in extra[:BABBLE_TALKERS]] or [c["audio"] for c in clean[N_NOISY:]]
        for i, it in enumerate(clean[:N_NOISY]):
            base = f"{tag}_clean_{i:02d}"
            babble = make_babble(babble_src, len(it["audio"]))
            for snr in SNRS_DB:
                cid = f"{tag}_babble_snr{snr}_{i:02d}"
                p = ASR_DIR / "noisy" / f"{cid}.wav"
                save_wav(p, mix_at_snr(it["audio"], babble, snr))
                rows.append(_row(cid, p, lang, "noisy_babble", it["reference"], subcategory=f"snr{snr}",
                                 snr_db=snr, base_id=base, source="synthetic"))
            y8, sr8 = telephony(it["audio"])
            cid = f"{tag}_telephony_{i:02d}"
            p = ASR_DIR / "telephony" / f"{cid}.wav"
            save_wav(p, y8, sr8)
            rows.append(_row(cid, p, lang, "telephony", it["reference"], subcategory="8k_mulaw",
                             base_id=base, source="synthetic"))

        # long clips (24–29.5 s, just under the 30 s REST limit) + one over-limit clip
        long_pools = [extra[BABBLE_TALKERS:], clean[N_NOISY:]]
        for k, pool_k in enumerate(long_pools):
            if not pool_k:
                continue
            y, ref, dur = concat_clips(pool_k, 24, 29.5)
            cid = f"{tag}_long_{k:02d}"
            p = ASR_DIR / "long" / f"{cid}.wav"
            save_wav(p, y)
            rows.append(_row(cid, p, lang, "long", ref, subcategory=f"{dur:.0f}s", source="fleurs_concat"))
        if lang == "en-IN":
            y, ref, dur = concat_clips(clean + extra, 34, 45)
            cid = f"{tag}_overlimit_00"
            p = ASR_DIR / "long" / f"{cid}.wav"
            save_wav(p, y)
            rows.append(_row(cid, p, lang, "over_limit", ref, subcategory=f"{dur:.0f}s", source="fleurs_concat"))

    # own recordings (numbers, code-switching, domain terms, short replies, real noise)
    if OWN_MANIFEST.exists():
        found = 0
        for o in read_csv(OWN_MANIFEST):
            cid = o["clip_id"].strip()
            cand = OWN_DIR / o.get("file", "").strip() if o.get("file", "").strip() else None
            if not (cand and cand.exists()):
                hits = sorted(OWN_DIR.glob(f"{cid}.*"))
                hits = [h for h in hits if h.suffix.lower() not in (".csv", ".md", ".txt")]
                cand = hits[0] if hits else None
            if not cand:
                print(f"  [own] missing audio for {cid} — skipped")
                continue
            p = ASR_DIR / "own" / f"{cid}.wav"
            save_wav(p, load_audio(cand))
            rows.append(_row(cid, p, o["language"], o["category"], o["reference"], source="own_recording",
                             lang_hint_v3=o.get("lang_hint_v3", ""), format_v3=o.get("format_v3", ""),
                             expected_entities=o.get("expected_entities", ""), keyterms=o.get("keyterms", "")))
            found += 1
        print(f"[own] {found} recordings added")

    write_csv(MANIFEST, rows, MANIFEST_FIELDS)
    print(f"Manifest: {len(rows)} clips -> {MANIFEST.relative_to(ROOT)}")
    print(Counter((r["category"], r["language"]) for r in rows))


# =============================================================================
# 8. RUN ASR
# =============================================================================
def _keyterm_extra(model, keyterms):
    terms = [t.strip() for t in keyterms.split(",") if t.strip()]
    if model == "prisma-v2.5":
        # v2.5 bias_list: single words, letters only — one bad entry silently drops the
        # whole list, so split phrases and keep alphabetic words only.
        words = sorted({w for t in terms for w in re.split(r"[\s\-]+", t) if w.isalpha()})
        return {"bias_list": json.dumps(words, ensure_ascii=False), "bias_score": "1.0"}
    return {"keyterms": json.dumps(terms, ensure_ascii=False)}


def asr_jobs(models, lid=True):
    jobs = []
    for model in models:
        for r in read_csv(MANIFEST):
            v3 = model != "prisma-v2.5"
            lang = (r["lang_hint_v3"] or r["language"]) if v3 else r["language"]
            fmt = (r["format_v3"] or "verbatim") if v3 else "verbatim"
            jobs.append((model, r, "main", lang, fmt, {}))
            if r["expected_entities"]:
                jobs.append((model, r, "itn", r["language"], "transcribe", {}))
            if r["keyterms"]:
                jobs.append((model, r, "keyterms", lang, fmt, _keyterm_extra(model, r["keyterms"])))
            if v3 and lid and r["category"] == "clean":
                jobs.append((model, r, "lid", "indic-auto", "verbatim", {}))
    return jobs


def cmd_run_asr(args):
    jobs = asr_jobs(args.models, lid=not args.no_lid)
    todo = [j for j in jobs if not (CACHE_DIR / "asr" / j[0] / f"{j[1]['clip_id']}__{j[2]}.json").exists()]
    print(f"{len(jobs)} ASR jobs, {len(todo)} not cached yet (= API calls).")
    if args.dry_run:
        print(Counter((j[0], j[2]) for j in todo))
        return
    for k, (model, r, tag, lang, fmt, extra) in enumerate(todo, 1):
        path = CACHE_DIR / "asr" / model / f"{r['clip_id']}__{tag}.json"
        out = cached_json(path, lambda: prisma_transcribe(ROOT / r["path"], model, lang, fmt, extra))
        body = out.get("body", {})
        msg = body.get("transcript", "") if out["status"] == 200 else body
        print(f"[{k}/{len(todo)}] {model} {r['clip_id']} {tag}: {out['status']} | {str(msg)[:70]}")


# =============================================================================
# 9. SCORE ASR
# =============================================================================
def _clip_record(model, tag, r, c):
    body = c.get("body") or {}
    ok = c.get("status") == 200 and bool(body.get("success"))
    hyp = body.get("transcript", "") if ok else ""
    rec = {"model": model, "tag": tag, "ok": ok, "status": c.get("status"),
           "error": "" if ok else json.dumps(body, ensure_ascii=False)[:160],
           "hypothesis": hyp, "client_latency_s": c.get("client_latency_s"),
           "processing_time_s": body.get("processing_time"), "e2e_latency_s": body.get("end_to_end_latency"),
           "audio_duration_s": c.get("audio_duration_s"),
           "detected_language": body.get("detected_language_code", ""),
           "truncated": bool(body.get("truncated", False)),
           **{k: r[k] for k in ("clip_id", "language", "category", "subcategory", "snr_db", "base_id",
                                "reference", "expected_entities", "keyterms")}}
    if ok:
        ref_n, hyp_n = normalize(r["reference"], r["language"]), normalize(hyp, r["language"])
        w, ops = wer_counts(ref_n, hyp_n)
        ch = cer_counts(ref_n, hyp_n)
        wr, _ = wer_counts(normalize_raw(r["reference"]), normalize_raw(hyp))
        rec.update(ref_norm=ref_n, hyp_norm=hyp_n, wer_norm=error_rate(w), cer_norm=error_rate(ch),
                   wer_raw=error_rate(wr), _ops=ops,
                   **{f"w_{k}": v for k, v in w.items()}, **{f"c_{k}": v for k, v in ch.items()},
                   **{f"r_{k}": v for k, v in wr.items()})
    return rec


def _agg(g):
    n = g["w_N"].sum()
    return {"clips": len(g), "WER_raw": corpus_rate(g, "r"), "WER_norm": corpus_rate(g, "w"),
            "CER_norm": corpus_rate(g, "c"),
            "sub_%": 100 * g["w_S"].sum() / n if n else np.nan,
            "del_%": 100 * g["w_D"].sum() / n if n else np.nan,
            "ins_%": 100 * g["w_I"].sum() / n if n else np.nan,
            "latency_p50_s": p50(g["client_latency_s"].tolist())}


def grouped(df, keys):
    import pandas as pd
    out = []
    for k, g in df.groupby(keys, sort=False):
        k = k if isinstance(k, tuple) else (k,)
        out.append({**dict(zip(keys, k)), **_agg(g)})
    return pd.DataFrame(out)


def _digits_in(text):
    return re.findall(r"\d+", (text or "").replace(",", ""))


def cmd_score_asr(args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    rows = {r["clip_id"]: r for r in read_csv(MANIFEST)}
    recs = []
    for f in sorted((CACHE_DIR / "asr").glob("*/*.json")):
        cid, tag = f.stem.rsplit("__", 1)
        if cid in rows:
            recs.append(_clip_record(f.parent.name, tag, rows[cid], json.loads(f.read_text("utf-8"))))
    if not recs:
        sys.exit("No cached ASR results — run `run-asr` first.")
    df = pd.DataFrame(recs)
    RESULTS_DIR.mkdir(exist_ok=True)
    df.drop(columns=["_ops"], errors="ignore").to_csv(RESULTS_DIR / "asr_per_clip.csv", index=False)

    main = df[(df.tag == "main") & df.ok].copy()
    md = ["# Prisma (ASR) — results\n",
          "WER/CER are corpus-level (total errors / total reference words or characters). "
          "`WER_raw` = transcript as returned; `WER_norm` = after identical normalisation of reference "
          "and hypothesis (case, punctuation, numbers → words for English, Hindi nukta).\n"]

    overall = grouped(main[main.category != "over_limit"], ["model"])
    md += ["## Overall (all categories)\n", md_table(overall)]
    by_cat = grouped(main, ["model", "category", "language"]).sort_values(["category", "language", "model"])
    by_cat.to_csv(RESULTS_DIR / "asr_by_category.csv", index=False)
    md += ["## By category and language\n", md_table(by_cat)]

    # robustness curve: same base clips, clean -> babble SNR 10/5/0 -> telephony
    cond_rows = []
    for (model, lang), g in main.groupby(["model", "language"]):
        bases = set(g.loc[g.base_id != "", "base_id"])
        if not bases:
            continue
        conds = [("clean", g[g.clip_id.isin(bases)])]
        conds += [(f"babble {s} dB", g[(g.category == "noisy_babble") & (g.subcategory == f"snr{s}")]) for s in SNRS_DB]
        conds += [("telephony 8k", g[g.category == "telephony"])]
        for name, sub in conds:
            if len(sub):
                cond_rows.append({"model": model, "language": lang, "condition": name,
                                  "clips": len(sub), "WER_norm": corpus_rate(sub, "w"),
                                  "CER_norm": corpus_rate(sub, "c")})
    cond = pd.DataFrame(cond_rows)
    md += ["## Robustness: same clips, degraded\n", md_table(cond)]
    if len(cond):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for (model, lang), g in cond.groupby(["model", "language"]):
            ax.plot(g["condition"], 100 * g["WER_norm"], marker="o", label=f"{model} · {lang}")
        ax.set_ylabel("WER (%)")
        ax.set_title("Prisma: WER as audio degrades")
        ax.grid(alpha=.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(RESULTS_DIR / "asr_wer_vs_condition.png", dpi=150)
        md.append("![WER vs condition](asr_wer_vs_condition.png)\n")

    cat_model = grouped(main[main.category != "over_limit"], ["category", "model"])
    if len(cat_model):
        piv = cat_model.pivot(index="category", columns="model", values="WER_norm") * 100
        ax = piv.plot.bar(figsize=(9, 4.5), rot=30)
        ax.set_ylabel("WER (%)")
        ax.set_title("Prisma: WER by category")
        ax.grid(axis="y", alpha=.3)
        plt.tight_layout()
        plt.savefig(RESULTS_DIR / "asr_wer_by_category.png", dpi=150)
        md.append("![WER by category](asr_wer_by_category.png)\n")

    # ITN / numbers: are the digits in the formatted transcript right?
    itn = df[(df.tag == "itn") & df.ok].copy()
    if len(itn):
        def ent_hits(row):
            exp = [e.replace(",", "") for e in row.expected_entities.split("|") if e]
            got = _digits_in(row.hypothesis)
            return sum(e in got or e in "".join(got) for e in exp), len(exp)
        itn[["entities_ok", "entities_total"]] = itn.apply(lambda r: pd.Series(ent_hits(r)), axis=1)
        md += ["## Numbers with `format=transcribe` (entity exact match)\n",
               md_table(itn[["model", "clip_id", "expected_entities", "hypothesis", "entities_ok", "entities_total"]]),
               md_table(itn.groupby("model")[["entities_ok", "entities_total"]].sum()
                        .assign(accuracy=lambda d: d.entities_ok / d.entities_total).reset_index())]

    # context: keyterms (v3.0) / bias_list (v2.5) vs no context on the same clip
    kt = df[(df.tag == "keyterms") & df.ok]
    if len(kt):
        kt_rows = []
        for _, k in kt.iterrows():
            base = main[(main.model == k.model) & (main.clip_id == k.clip_id)]
            if base.empty:
                continue
            b = base.iloc[0]
            terms = [normalize(t, k.language) for t in k.keyterms.split(",") if t.strip()]
            recall = lambda h: sum(f" {t} " in f" {h} " for t in terms) / len(terms)
            kt_rows.append({"model": k.model, "clip_id": k.clip_id, "WER_no_context": b.wer_norm,
                            "WER_with_context": k.wer_norm, "term_recall_no_context": recall(b.hyp_norm),
                            "term_recall_with_context": recall(k.hyp_norm)})
        md += ["## Domain terms: with vs without context hints\n", md_table(pd.DataFrame(kt_rows))]

    # language ID with indic-auto (v3.0)
    lid = df[(df.tag == "lid") & df.ok].copy()
    if len(lid):
        lid["lid_correct"] = lid.detected_language == lid.language
        md += ["## Language detection (`indic-auto`, v3.0)\n",
               md_table(lid.groupby("language").agg(clips=("lid_correct", "size"), accuracy=("lid_correct", "mean"),
                                                    WER_norm_auto=("wer_norm", "mean")).reset_index()),
               md_table(lid[~lid.lid_correct][["clip_id", "language", "detected_language", "hypothesis"]])]

    # latency
    lat = []
    for model, g in main.groupby("model"):
        rtf = (g.processing_time_s / g.audio_duration_s).tolist()
        lat.append({"model": model, "calls": len(g),
                    "client_p50_s": p50(g.client_latency_s.tolist()), "client_p95_s": p95(g.client_latency_s.tolist()),
                    "server_proc_p50_s": p50(g.processing_time_s.tolist()),
                    "server_proc_p95_s": p95(g.processing_time_s.tolist()),
                    "server_RTF_p50": p50(rtf)})
    md += ["## Latency (REST, measured from client)\n", md_table(pd.DataFrame(lat))]

    # error analysis
    worst = main[main.w_N >= 3].sort_values("wer_norm", ascending=False).head(12)
    md.append("## Worst clips (normalised)\n")
    for _, w in worst.iterrows():
        md.append(f"- **{w.model} · {w.clip_id}** ({w.category}, {w.language}) WER {w.wer_norm:.2f}\n"
                  f"  - REF: {w.ref_norm}\n  - HYP: {w.hyp_norm}\n")
    for model, g in main.groupby("model"):
        subs, dels, ins = Counter(), Counter(), Counter()
        for ops in g["_ops"]:
            for op, a, b in ops:
                if op == "S":
                    subs[f"{a} → {b}"] += 1
                elif op == "D":
                    dels[a] += 1
                elif op == "I":
                    ins[b] += 1
        md.append(f"\n**{model}** — top substitutions: " + ", ".join(f"`{k}`×{v}" for k, v in subs.most_common(12)))
        md.append(f"\n**{model}** — top deletions: " + ", ".join(f"`{k}`×{v}" for k, v in dels.most_common(8)))
        md.append(f"\n**{model}** — top insertions: " + ", ".join(f"`{k}`×{v}" for k, v in ins.most_common(8)) + "\n")

    fails = df[~df.ok]
    md += ["\n## Failed requests\n",
           md_table(fails[["model", "tag", "clip_id", "category", "status", "error"]]) if len(fails) else "None.\n"]
    trunc = df[df.truncated]
    if len(trunc):
        md += ["## Truncated transcripts\n", md_table(trunc[["model", "clip_id", "category"]])]

    (RESULTS_DIR / "asr_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(overall.to_string(index=False))
    print(f"\nWrote results/asr_summary.md, asr_per_clip.csv, asr_by_category.csv and plots.")


# =============================================================================
# 10. RUN TTS
# =============================================================================
def tts_items():
    items = []
    for s in read_csv(TTS_SENTENCES):
        items.append({**s, "item_id": s["id"], "input_form": "raw", "text_sent": s["text"]})
        if s.get("spelled_variant", "").strip() == "1":
            items.append({**s, "item_id": f"{s['id']}__spelled", "input_form": "spelled",
                          "text_sent": s["expected_spoken"], "latency_probe": ""})
    return items


def cmd_run_tts(args):
    items = tts_items()
    todo = [(m, it) for m in args.models for it in items
            if not (CACHE_DIR / "tts" / m / f"{it['item_id']}.json").exists()]
    probes = [(m, it, k) for m in args.models for it in items if it.get("latency_probe") == "1"
              for k in range(SSE_RUNS)
              if not (CACHE_DIR / "tts_sse" / m / f"{it['item_id']}__run{k}.json").exists()]
    print(f"TTS: {len(todo)} REST calls + {len(probes)} SSE latency calls not cached yet.")
    if args.dry_run:
        return
    for n, (model, it) in enumerate(todo, 1):
        voice = TTS_VOICES[model][it["language"]]
        meta, audio = timbre_rest(tts_payload(it["text_sent"], model, it["language"], voice))
        _check_fatal(meta["status"])
        d = CACHE_DIR / "tts" / model
        if audio:
            meta["audio_duration_s"] = pcm_to_wav(audio, d / f"{it['item_id']}.wav")
        meta.update(voice=voice, text_sent=it["text_sent"])
        if meta["status"] not in NON_CACHEABLE:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{it['item_id']}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[REST {n}/{len(todo)}] {model} {it['item_id']}: {meta['status']} "
              f"{meta.get('audio_duration_s', 0):.1f}s audio in {meta['client_latency_s']:.2f}s")
    for n, (model, it, k) in enumerate(probes, 1):
        voice = TTS_VOICES[model][it["language"]]
        out = timbre_sse(tts_payload(it["text_sent"], model, it["language"], voice))
        _check_fatal(out["status"])
        p = CACHE_DIR / "tts_sse" / model / f"{it['item_id']}__run{k}.json"
        if out["status"] not in NON_CACHEABLE:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[SSE {n}/{len(probes)}] {model} {it['item_id']} run{k}: first audio "
              f"{out.get('ttfa_s')}s, total {out.get('total_s')}s")


# =============================================================================
# 11. SCORE TTS
# =============================================================================
WHISPER_LANG = {"en-IN": "en", "hi-IN": "hi", "ta-IN": "ta", "hi-en": None}   # None = auto (code-mixed)


def _whisper(name):
    import torch
    from faster_whisper import WhisperModel
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    return WhisperModel(name, device=dev, compute_type="float16" if dev == "cuda" else "int8")


def final_pitch_rise_st(y, sr=SR):
    """Semitone change of F0 over the last 15 % of voiced frames vs the rest.
    Questions should rise (positive), statements fall (negative)."""
    import librosa
    yt, _ = librosa.effects.trim(y, top_db=35)
    f0, _, _ = librosa.pyin(yt, fmin=70, fmax=400, sr=sr, frame_length=1024)
    f0 = f0[~np.isnan(f0)]
    if len(f0) < 12:
        return float("nan")
    k = max(3, int(0.15 * len(f0)))
    return float(12 * np.log2(np.mean(f0[-k:]) / np.median(f0[:-k])))


def silence_stats(y, sr=SR):
    import librosa
    _, (a, b) = librosa.effects.trim(y, top_db=40)
    return a / sr, (len(y) - b) / sr, (b - a) / sr


def cmd_score_tts(args):
    import pandas as pd
    import soundfile as sf
    items = tts_items()
    wmodel = _whisper(args.whisper_model)
    try:
        import torch
        utmos = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True)
    except Exception as e:      # keep going without MOS rather than failing the whole run
        print(f"UTMOS unavailable ({e}); continuing without it.")
        utmos = None

    recs = []
    for model in args.models:
        for it in items:
            meta_p = CACHE_DIR / "tts" / model / f"{it['item_id']}.json"
            wav_p = meta_p.with_suffix(".wav")
            if not meta_p.exists():
                continue
            meta = json.loads(meta_p.read_text("utf-8"))
            rec = {"model": model, "item_id": it["item_id"], "id": it["id"], "language": it["language"],
                   "category": it["category"], "input_form": it["input_form"], "text_sent": it["text_sent"],
                   "expected_spoken": it["expected_spoken"], "check_note": it.get("check_note", ""),
                   "status": meta["status"], "rest_latency_s": meta.get("client_latency_s"),
                   "audio_s": meta.get("audio_duration_s")}
            if meta["status"] != 200 or not wav_p.exists():
                rec["error"] = json.dumps(meta.get("error"), ensure_ascii=False)[:160]
                recs.append(rec)
                continue
            y = load_audio(wav_p)

            jp = CACHE_DIR / "tts_judge" / "whisper" / model / f"{it['item_id']}.json"
            if jp.exists():
                j = json.loads(jp.read_text("utf-8"))
            else:
                segs, info = wmodel.transcribe(str(wav_p), language=WHISPER_LANG[it["language"]], beam_size=5,
                                               temperature=0.0, condition_on_previous_text=False)
                j = {"text": " ".join(s.text.strip() for s in segs), "lang": info.language}
                jp.parent.mkdir(parents=True, exist_ok=True)
                jp.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")

            ref_n = normalize(it["expected_spoken"], it["language"])
            hyp_n = normalize(j["text"], it["language"])
            w, _ = wer_counts(ref_n, hyp_n)
            c = cer_counts(ref_n, hyp_n)
            lead, trail, speech = silence_stats(y)
            rec.update(asr_judge_text=j["text"], judge_wer=error_rate(w), judge_cer=error_rate(c),
                       **{f"w_{k}": v for k, v in w.items()}, **{f"c_{k}": v for k, v in c.items()},
                       lead_sil_s=lead, trail_sil_s=trail, speech_s=speech,
                       words_per_s=len(ref_n.split()) / speech if speech else np.nan,
                       clipping_pct=100 * float(np.mean(np.abs(y) > 0.99)),
                       rest_rtf=meta["client_latency_s"] / meta["audio_duration_s"] if meta.get("audio_duration_s") else np.nan)
            if utmos is not None:
                with torch.no_grad():
                    rec["utmos"] = float(utmos(torch.from_numpy(y).unsqueeze(0), SR).item())
            if it["category"] in ("question", "statement"):
                rec["final_rise_st"] = final_pitch_rise_st(y)

            if args.prisma_judge:     # optional second judge: Gnani's own ASR (costs credits)
                lang = {"hi-en": "hi-IN,en-IN"}.get(it["language"], it["language"])
                fmt = "codemix" if it["category"] == "code_mixed" else "verbatim"
                pj = cached_json(CACHE_DIR / "tts_judge" / "prisma" / model / f"{it['item_id']}.json",
                                 lambda: prisma_transcribe(wav_p, "prisma-v3.0", lang, fmt))
                ptxt = (pj.get("body") or {}).get("transcript", "")
                rec["prisma_judge_cer"] = error_rate(cer_counts(ref_n, normalize(ptxt, it["language"])))
            recs.append(rec)

    df = pd.DataFrame(recs)
    if df.empty:
        sys.exit("No cached TTS results — run `run-tts` first.")
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / "tts_per_item.csv", index=False)
    ok = df[df.status == 200].copy()

    def agg(g):
        return {"items": len(g), "intellig_WER": corpus_rate(g, "w"), "intellig_CER": corpus_rate(g, "c"),
                "UTMOS": g["utmos"].mean() if "utmos" in g else np.nan,
                "words_per_s": g["words_per_s"].mean(), "REST_latency_p50_s": p50(g.rest_latency_s.tolist()),
                "REST_RTF_p50": p50(g.rest_rtf.tolist())}

    def table(keys, data):
        out = []
        for k, g in data.groupby(keys, sort=False):
            k = k if isinstance(k, tuple) else (k,)
            out.append({**dict(zip(keys, k)), **agg(g)})
        return pd.DataFrame(out)

    md = ["# Timbre (TTS) — results\n",
          "Intelligibility = round-trip ASR with an independent model (faster-whisper "
          f"`{args.whisper_model}`) against the expected spoken form; lower is better. "
          "UTMOS = predicted naturalness MOS (1–5, trained on English; read Indic scores relatively). "
          "RTF = synthesis time / audio duration (<1 is faster than real time).\n"]
    overall = table(["model"], ok)
    md += ["## Overall\n", md_table(overall)]
    by_cat = table(["model", "category", "language"], ok[ok.input_form == "raw"]).sort_values(["category", "language", "model"])
    by_cat.to_csv(RESULTS_DIR / "tts_by_category.csv", index=False)
    md += ["## By category and language (raw input)\n", md_table(by_cat)]

    sp = ok[ok.id.isin(ok.loc[ok.input_form == "spelled", "id"])]
    if len(sp):
        piv = sp.pivot_table(index=["model", "id"], columns="input_form", values="judge_wer").reset_index()
        md += ["## Numbers: raw digits vs pre-spelled input (intelligibility WER)\n",
               "The Timbre docs recommend sending numbers as words. This measures how much it matters.\n",
               md_table(piv)]

    if "final_rise_st" in ok:
        pr = ok[ok.category.isin(["question", "statement"])]
        md += ["## Prosody: final pitch movement (semitones; questions should be > statements)\n",
               md_table(pr.groupby(["model", "language", "category"])["final_rise_st"].mean().reset_index())]

    sse_rows = []
    for model in args.models:
        runs = [json.loads(p.read_text("utf-8")) for p in sorted((CACHE_DIR / "tts_sse" / model).glob("*.json"))]
        runs = [r for r in runs if r.get("status") == 200 and r.get("ttfa_s")]
        if runs:
            sse_rows.append({"model": model, "runs": len(runs),
                             "TTFA_p50_s": p50([r["ttfa_s"] for r in runs]),
                             "TTFA_p95_s": p95([r["ttfa_s"] for r in runs]),
                             "total_p50_s": p50([r["total_s"] for r in runs]),
                             "RTF_p50": p50([r["rtf"] for r in runs])})
    md += ["## Streaming latency (SSE): time to first audio\n", md_table(pd.DataFrame(sse_rows))]

    if "prisma_judge_cer" in ok:
        both = ok.dropna(subset=["prisma_judge_cer", "judge_cer"])
        if len(both) > 3:
            md.append(f"Judge agreement (Pearson r of per-item CER, Whisper vs Prisma): "
                      f"{np.corrcoef(both.judge_cer, both.prisma_judge_cer)[0, 1]:.2f}\n")

    flags = ok[(ok.judge_wer > 0.3) | (ok.get("utmos", pd.Series(5, index=ok.index)) < 3.0) |
               (ok.lead_sil_s > 1.0) | (ok.trail_sil_s > 1.5) | (ok.clipping_pct > 0.1)]
    md.append("## Flagged for listening\n")
    for _, f in flags.iterrows():
        md.append(f"- **{f.model} · {f.item_id}** ({f.category}) WER {f.judge_wer:.2f}"
                  f"{'' if 'utmos' not in f else f', UTMOS {f.utmos:.2f}'}\n"
                  f"  - SENT: {f.text_sent}\n  - HEARD: {f.asr_judge_text}\n")
    errs = df[df.status != 200]
    md += ["\n## Failed requests\n",
           md_table(errs[["model", "item_id", "language", "status", "error"]]) if len(errs) else "None.\n"]

    sheet = ok[["model", "item_id", "category", "language", "text_sent", "check_note"]].copy()
    for col in ["naturalness_1to5", "pronunciation_correct_yn", "notes"]:
        sheet[col] = ""
    sheet.to_csv(RESULTS_DIR / "tts_listening_sheet.csv", index=False)
    if LISTENING_FILLED.exists():
        lf = pd.read_csv(LISTENING_FILLED)
        lf["pron_ok"] = lf.pronunciation_correct_yn.astype(str).str.lower().str.startswith("y")
        md += ["## Human listening check\n",
               md_table(lf.groupby(["model", "category"]).agg(items=("pron_ok", "size"),
                        naturalness=("naturalness_1to5", "mean"), pronunciation_ok=("pron_ok", "mean")).reset_index())]
        if "utmos" in ok:
            m = ok.merge(lf, on=["model", "item_id"]).dropna(subset=["utmos", "naturalness_1to5"])
            if len(m) > 3:
                md.append(f"UTMOS vs human naturalness, Pearson r = {np.corrcoef(m.utmos, m.naturalness_1to5)[0, 1]:.2f}\n")

    (RESULTS_DIR / "tts_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(overall.to_string(index=False))
    print("\nWrote results/tts_summary.md, tts_per_item.csv, tts_by_category.csv, tts_listening_sheet.csv")


# =============================================================================
# 12. SMOKE TEST + CLI
# =============================================================================
def cmd_smoke(args):
    out = CACHE_DIR / "smoke"
    text = "Hello, this is a quick test of the Gnani speech API."
    meta, audio = timbre_rest(tts_payload(text, "timbre-v3.0", "en-IN", TTS_VOICES["timbre-v3.0"]["en-IN"]))
    print("TTS:", meta)
    if not audio:
        sys.exit("TTS failed — check the key and the error above.")
    dur = pcm_to_wav(audio, out / "tts.wav")
    print(f"  -> {dur:.2f}s of audio written to cache/smoke/tts.wav")
    for model in ASR_MODELS:
        res = prisma_transcribe(out / "tts.wav", model, "en-IN", "verbatim")
        print(f"STT {model}: status {res['status']} | {res['body'].get('transcript', res['body'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke-test")
    sub.add_parser("prepare-asr")
    p = sub.add_parser("run-asr")
    p.add_argument("--models", nargs="+", default=ASR_MODELS)
    p.add_argument("--no-lid", action="store_true", help="skip the indic-auto language-ID runs")
    p.add_argument("--dry-run", action="store_true", help="only count the API calls")
    sub.add_parser("score-asr")
    p = sub.add_parser("run-tts")
    p.add_argument("--models", nargs="+", default=TTS_MODELS)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("score-tts")
    p.add_argument("--models", nargs="+", default=TTS_MODELS)
    p.add_argument("--whisper-model", default="large-v3")
    p.add_argument("--prisma-judge", action="store_true", help="also judge TTS with Prisma v3.0 (costs credits)")
    p = sub.add_parser("all")
    p.add_argument("--whisper-model", default="large-v3")
    args = ap.parse_args()

    if args.cmd == "all":
        args.models, args.no_lid, args.dry_run, args.prisma_judge = ASR_MODELS, False, False, False
        cmd_prepare_asr(args)
        cmd_run_asr(args)
        cmd_score_asr(args)
        args.models = TTS_MODELS
        cmd_run_tts(args)
        cmd_score_tts(args)
        return
    {"smoke-test": cmd_smoke, "prepare-asr": cmd_prepare_asr, "run-asr": cmd_run_asr,
     "score-asr": cmd_score_asr, "run-tts": cmd_run_tts, "score-tts": cmd_score_tts}[args.cmd](args)


if __name__ == "__main__":
    main()
