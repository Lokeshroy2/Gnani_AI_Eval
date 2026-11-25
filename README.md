# Gnani.ai take-home — Prisma (ASR) & Timbre (TTS) evaluation

One script, `gnani_eval.py`, covers both parts. Every API response is cached under `cache/`,
so re-running any step never spends credits twice, and the scoring steps run offline.

**Use case assumed throughout:** an Indian insurance company deploying inbound/outbound voice bots
(English, Hindi and Tamil callers, phone audio, policy numbers, amounts, code-mixed speech).

## Setup

Python 3.10+. Whisper and UTMOS (the TTS judges) run fine on CPU for a dataset this size; a GPU
just makes `score-tts` faster.

```bash
pip install -r requirements.txt
export GNANI_API_KEY=your_key_here
python gnani_eval.py smoke-test        # 3 API calls — confirms key, TTS and both STT models
```

## Run

```bash
python gnani_eval.py prepare-asr       # build the ASR test set (FLEURS + synthetic + own recordings)
python gnani_eval.py run-asr --dry-run # shows how many API calls will be made
python gnani_eval.py run-asr
python gnani_eval.py score-asr         # -> results/asr_summary.md + CSVs + plots
python gnani_eval.py run-tts
python gnani_eval.py score-tts         # -> results/tts_summary.md + CSVs + listening sheet
```
Options: `run-asr --models prisma-v3.0`, `run-asr --no-lid`, `score-tts --whisper-model medium`,
`score-tts --prisma-judge` (second TTS judge using Prisma, costs credits).

## Own recordings (about 10 minutes)

`data/own_recordings/manifest_own.csv` lists 18 sentences public datasets don't cover:
spoken numbers, Tamil–English code-switching, insurance vocabulary, one-word replies and real
background noise. Record each one on your phone, name the file after its `clip_id`
(e.g. `own_cs_01.m4a`, any format) and drop it in `data/own_recordings/`. Say the sentence exactly
as written in `reference`; if you say it differently, edit `reference` to match what you said.
Missing files are skipped, so the pipeline also runs without them.

## Test design

| Part | Category | Source | Why it matters for a voice bot |
|---|---|---|---|
| ASR | clean read speech (en/hi/ta) | FLEURS test | baseline per language |
| ASR | babble noise at 10 / 5 / 0 dB | FLEURS + other FLEURS speakers mixed in | call-centre / street background |
| ASR | telephony (300–3400 Hz, 8 kHz, µ-law) | synthetic from the same clips | every phone call is narrow-band |
| ASR | long (24–29.5 s) + one clip over 30 s | concatenated FLEURS | REST limit behaviour, truncation |
| ASR | numbers, code-switch, domain terms, short replies, real noise | own recordings | policy numbers, Tanglish, jargon, "yes/no" turns |
| ASR | `format=transcribe` entity check | own number clips | are digits right after ITN? |
| ASR | context hints (`keyterms` / `bias_list`) on vs off | own domain clips | do hints help or hurt? |
| ASR | `indic-auto` language ID (v3.0) | FLEURS clean | caller language unknown upfront |
| TTS | baseline, numbers (raw vs spelled), abbreviations, heteronyms, names, code-mixed, questions vs statements, emails/URLs, long-form | `data/tts_sentences.csv` (34 sentences, en/hi/ta/Hinglish) | the things that break in production prompts |

## Metrics

**ASR.** WER and CER are computed with an own Levenshtein alignment (`align()` in section 5), which
also returns the substitution / deletion / insertion breakdown. Aggregates are corpus-level
(total errors ÷ total reference words), not a mean of per-clip rates. Two views are reported:
`WER_raw` is the transcript exactly as returned, and `WER_norm` applies the same normalisation to
reference and hypothesis (case, punctuation, English numbers → words, Hindi nukta/chandrabindu).
For Hindi and Tamil, CER is the more reliable number. Latency is reported both client-side
(includes upload) and as the server's `processing_time`.

**TTS.** There is no single "quality" number, so four objective, repeatable measures are used:

1. *Intelligibility:* round-trip ASR with an independent model (faster-whisper; default is
   `large-v3`, this run used `--whisper-model medium` for speed — not Prisma, so Prisma's errors
   don't mix into Timbre's score), WER/CER against the expected spoken form.
2. *Naturalness:* UTMOS predicted MOS.
3. *Prosody:* final F0 movement in semitones, questions vs matched statements.
4. *Speed:* REST latency, SSE time-to-first-audio, and RTF (synthesis time ÷ audio duration).

Signal checks (leading/trailing silence, clipping, speaking rate) and a human listening sheet
(`results/tts_listening_sheet.csv` → fill in → save as `data/tts_listening_filled.csv` → re-run
`score-tts`) cover what ASR cannot hear, such as heteronyms and stress.

## Engineering notes (from the docs)

- The account allows **one active request at a time**, so calls are sequential, with backoff on 429/5xx.
- `format` is always sent explicitly: Prisma v3.0's default changes with the language.
- v2.5 `bias_list` silently ignores the **whole list** if one entry isn't a single alphabetic word,
  so phrases are split and cleaned before sending.
- TTS audio is requested as raw 16 kHz PCM and the WAV header is written locally, so durations and
  RTF don't depend on server headers.
- Auth/credit/rate-limit failures are never cached; real 4xx outcomes (e.g. the >30 s clip) are,
  because they are findings.

## Layout

```
gnani_eval.py               all code (config, API client, normalisation, metrics, audio, steps)
data/tts_sentences.csv      TTS test set
data/own_recordings/        own clips + manifest_own.csv
data/asr/manifest.csv       generated ASR test set
cache/                      every API response (committed for reproducibility)
results/                    summaries, CSVs, plots
report.md                   1–2 page write-up
```

## Limitations

Small sample (roughly 100 ASR clips, 34 TTS sentences), so differences of a few WER points are
within noise. Number normalisation is English-only, so Indic number errors are read from CER and
listening. UTMOS was trained on English. Whisper is a weaker judge for Tamil, so the Tamil TTS
scores are relative, not absolute. Latency is measured from one network location. FLEURS has no
Indian-English config (only `en_us`), so the FLEURS-derived en-IN clean/noisy/telephony/long
clips are American-accented English; Indian-accented English is covered only by the own
recordings.
