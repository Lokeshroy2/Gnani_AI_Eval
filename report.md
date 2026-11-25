# Prisma & Timbre evaluation — summary
**Lokesh · AI Solutions Engineer take-home · Gnani.ai**

## 1. Context and what "good" means

Use case: an Indian insurance company's voice bot, callers in English, Hindi and Tamil, over phone
audio. "Good" ASR = low WER on what the bot *acts on* (policy numbers, amounts, intents, jargon like
TPA/AYUSH/sum-insured), robust on 8 kHz + real noise, low latency. "Good" TTS = numbers/IDs read
correctly, natural enough not to annoy callers, fast first-audio for a live call.

## 2. Test design

FLEURS (clean, babble 10/5/0 dB, telephony 8 kHz, long/over-limit clips) covers en/hi/ta read speech
reproducibly from a public dataset. 18 own recordings (my voice) cover what FLEURS can't: policy
numbers, Tanglish code-switching, insurance vocabulary, one-word replies, real background noise. TTS
uses 34 sentences × 2 models (baseline, numbers raw/spelled, abbreviations, heteronyms, names,
code-mixed, Q vs statement, long-form) — 103 ASR clips and 84 TTS items scored in total.

## 3. Methodology

WER/CER: own Levenshtein alignment (not a library scorer), corpus-level aggregation, raw vs
normalised (case/punctuation/number-words) views reported separately. TTS: round-trip intelligibility
via an independent ASR judge (faster-whisper, not Prisma, so Prisma's own errors don't contaminate
the score), UTMOS naturalness, F0 prosody, latency/RTF, plus a targeted human listening pass (19 of
84 items, chosen from what the metrics flagged as risky) to catch what ASR/UTMOS can't hear.

## 4. Prisma (ASR) results

| model       | WER_norm | CER_norm | latency_p50_s |
|:------------|---------:|---------:|--------------:|
| prisma-v2.5 |    0.302 |    0.217 |         0.637 |
| prisma-v3.0 |    0.264 |    0.159 |         0.781 |

- **Tanglish code-switching is the clearest gap.** On 3 Tamil/English clips, v2.5 (plain `ta-IN`)
  scored WER **0.65** (substituting English words with Tamil phonetic guesses); v3.0
  (`format=codemix`) scored WER **0.20**. Insurance callers code-switch constantly — v2.5 has no
  real answer for it.
- **v2.5 silently truncates long English audio.** On 24–29.5s clips (under the 30s limit), v2.5 WER
  jumped to **0.85** (almost pure deletions — transcript just stops mid-sentence), vs v3.0's 0.06 on
  the same clips, with **no error returned either way**. Tamil long clips didn't show this gap, so
  it looks specific to English/v2.5 — worse than a clean failure, since nothing signals it happened.
- **Noise: telephony is fine, babble is brutal, for both models.** 8 kHz telephony barely moves WER.
  Babble at 5 dB roughly triples it; at 0 dB English WER hits ~1.0 for both models. The biggest
  real-world accuracy risk is a noisy room on the caller's end, not the phone network.
- **Numbers/ITN: 100% entity accuracy** (5/5, both models) with `format=transcribe` — policy
  numbers, mobile numbers, amounts, dates all extracted correctly.
- **Context hints (`keyterms`/`bias_list`) help only on genuinely ambiguous terms** — 2 of 5 domain
  clips improved a lot, the other 3 showed no change. Also: v2.5's `bias_list` silently drops the
  *entire list* if one entry isn't a single alphabetic word — test carefully before deploy.
- **Tamil one-word replies are a real risk.** English short replies were perfect, but the Tamil "no"
  clip came back as the word repeated 3× from *both* models (100% insertion) — a bot doing exact
  yes/no matching in Tamil would break on this.
- `indic-auto` language ID (v3.0) was 100% accurate across en/hi/ta — reliable for routing when the
  caller's language isn't known upfront. Full tables: `results/asr_summary.md`.

## 5. Timbre (TTS) results

| model       | intellig_WER | UTMOS | REST_latency_p50_s | RTF_p50 |
|:------------|-------------:|------:|--------------------:|--------:|
| timbre-v2.5 |        0.152 | 3.945 |                0.974 |   0.279 |
| timbre-v3.0 |        0.116 | 4.329 |                1.885 |   0.419 |

- **v3.0 sounds better and is more intelligible; v2.5 generates ~2× faster end-to-end** — but in
  **streaming (SSE) mode the gap mostly disappears**: time-to-first-audio is comparable (v2.5 0.507s
  vs v3.0 0.478s p50). Play via SSE and the quality upgrade is close to free on perceived latency.
- **Pre-spelling numbers measurably helps**, especially for v2.5 (phone number WER 0.50→0.00
  spelled; alphanumeric policy ID 0.40→0.00 spelled). Always pre-normalise numbers to words before
  TTS — it never hurt, often helped a lot.
- **Abbreviations, heteronyms, names and code-mixed output are all solid** (WER near 0 across the
  board) — not a concern for this use case.
- **Tamil prosody is the one real TTS defect found.** v2.5's Tamil *statement* clip pitch-drops
  **-16.9 semitones** at the end, far beyond any other clip — listening confirmed **it sounds
  unfinished**. Separately, neither model reliably produces a rising pitch on Tamil *questions*. For
  Tamil yes/no prompts, don't rely on pitch alone — script an explicit question word.

Full tables: `results/tts_summary.md`. Listening notes: `data/tts_listening_filled.csv`.

## 6. Recommendation

**ASR — deploy prisma-v3.0.** v2.5's latency edge isn't worth it once Tanglish, the long-clip
truncation bug, and keyterms are in scope — all things this customer will hit. Use `format=codemix`
or `indic-auto` where the caller's language/code-switching isn't predictable, `format=transcribe` on
any number/ID-capturing turn. Test `keyterms` against the real product vocabulary (gains are
per-term, not guaranteed), and put noise suppression in front of the API — babble past ~5 dB SNR is
the single biggest accuracy risk. For Tamil yes/no turns, don't exact-match the transcript.

**TTS — deploy timbre-v3.0 via SSE streaming**, not REST, to get the quality upgrade at near-zero
perceived-latency cost. Pre-normalise numbers/IDs to words before every call. Avoid relying on
pitch alone for Tamil questions. Before go-live: re-test the Tamil "trails off" statement issue
against the customer's actual IVR scripts — it's the one finding that looks like a genuine bug, not
scoring noise.

**Before go-live, also:** run the customer's real IVR scripts (not this generic set) through the
pipeline; test with real call-centre noise; record own-voice clips from more than one
speaker/accent (this set is single-speaker — me); extend the listening pass beyond the flagged
subset; validate `keyterms`/`bias_list` end-to-end against the real jargon list.

## 7. Limitations

Small sample (~103 ASR clips, 84 TTS items) — differences of a few WER points are within noise.
Number-normalisation in scoring is English-only, so Indic number errors are read from CER/listening,
not WER. UTMOS (English-trained) and Whisper (weaker on Tamil) make Tamil TTS scores relative, not
absolute. Latency measured from one network location. FLEURS has no Indian-English config (only
`en_us`), so FLEURS-derived en-IN clips are American-accented; Indian-accented English coverage
comes only from the 18 own recordings, which are single-speaker. The listening pass covered 19 of 84
TTS items (the ones metrics flagged), not the full set.
