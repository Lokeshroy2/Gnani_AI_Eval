# Timbre (TTS) — results

Intelligibility = round-trip ASR with an independent model (faster-whisper `medium`) against the expected spoken form; lower is better. UTMOS = predicted naturalness MOS (1–5, trained on English; read Indic scores relatively). RTF = synthesis time / audio duration (<1 is faster than real time).

## Overall

| model       |   items |   intellig_WER |   intellig_CER |   UTMOS |   words_per_s |   REST_latency_p50_s |   REST_RTF_p50 |
|:------------|--------:|---------------:|---------------:|--------:|--------------:|---------------------:|---------------:|
| timbre-v2.5 |      42 |          0.152 |          0.076 |   3.945 |         3.481 |                0.974 |          0.279 |
| timbre-v3.0 |      42 |          0.116 |          0.068 |   4.329 |         2.751 |                1.885 |          0.419 |

## By category and language (raw input)

| model       | category      | language   |   items |   intellig_WER |   intellig_CER |   UTMOS |   words_per_s |   REST_latency_p50_s |   REST_RTF_p50 |
|:------------|:--------------|:-----------|--------:|---------------:|---------------:|--------:|--------------:|---------------------:|---------------:|
| timbre-v2.5 | abbreviations | en-IN      |       3 |          0.088 |          0.030 |   4.088 |         3.478 |                0.870 |          0.259 |
| timbre-v3.0 | abbreviations | en-IN      |       3 |          0.000 |          0.000 |   4.442 |         2.554 |                1.917 |          0.460 |
| timbre-v2.5 | baseline      | en-IN      |       2 |          0.000 |          0.000 |   4.333 |         4.262 |                0.954 |          0.260 |
| timbre-v3.0 | baseline      | en-IN      |       2 |          0.000 |          0.000 |   4.433 |         3.216 |                2.717 |          0.560 |
| timbre-v2.5 | baseline      | hi-IN      |       1 |          0.235 |          0.062 |   4.000 |         3.768 |                1.273 |          0.274 |
| timbre-v3.0 | baseline      | hi-IN      |       1 |          0.176 |          0.050 |   3.470 |         3.279 |                1.925 |          0.365 |
| timbre-v2.5 | baseline      | ta-IN      |       1 |          0.500 |          0.095 |   3.780 |         2.212 |                1.109 |          0.289 |
| timbre-v3.0 | baseline      | ta-IN      |       1 |          0.125 |          0.048 |   4.304 |         1.887 |                1.718 |          0.405 |
| timbre-v2.5 | code_mixed    | hi-en      |       1 |          0.077 |          0.029 |   4.289 |         3.149 |                1.207 |          0.279 |
| timbre-v3.0 | code_mixed    | hi-en      |       1 |          0.077 |          0.029 |   4.340 |         2.902 |                1.906 |          0.418 |
| timbre-v2.5 | code_mixed    | ta-IN      |       1 |          0.125 |          0.034 |   4.024 |         2.381 |                0.923 |          0.262 |
| timbre-v3.0 | code_mixed    | ta-IN      |       1 |          0.125 |          0.034 |   3.844 |         2.174 |                1.553 |          0.413 |
| timbre-v2.5 | heteronyms    | en-IN      |       3 |          0.000 |          0.000 |   4.207 |         4.022 |                0.937 |          0.336 |
| timbre-v3.0 | heteronyms    | en-IN      |       3 |          0.000 |          0.000 |   4.473 |         2.961 |                1.708 |          0.430 |
| timbre-v2.5 | long_form     | en-IN      |       1 |          0.012 |          0.002 |   4.085 |         3.392 |                2.061 |          0.082 |
| timbre-v3.0 | long_form     | en-IN      |       1 |          0.000 |          0.000 |   4.411 |         2.865 |                4.223 |          0.142 |
| timbre-v2.5 | long_form     | hi-IN      |       1 |          0.217 |          0.066 |   3.375 |         3.307 |                2.380 |          0.130 |
| timbre-v3.0 | long_form     | hi-IN      |       1 |          0.233 |          0.120 |   4.272 |         2.648 |                5.953 |          0.260 |
| timbre-v2.5 | long_form     | ta-IN      |       1 |          0.316 |          0.064 |   2.730 |         2.179 |                2.047 |          0.116 |
| timbre-v3.0 | long_form     | ta-IN      |       1 |          0.211 |          0.068 |   4.229 |         1.786 |                7.237 |          0.338 |
| timbre-v2.5 | names         | en-IN      |       2 |          0.100 |          0.014 |   4.026 |         2.838 |                1.039 |          0.281 |
| timbre-v3.0 | names         | en-IN      |       2 |          0.050 |          0.007 |   4.338 |         2.163 |                1.672 |          0.355 |
| timbre-v2.5 | numbers       | en-IN      |       6 |          0.250 |          0.212 |   4.240 |         3.388 |                1.042 |          0.268 |
| timbre-v3.0 | numbers       | en-IN      |       6 |          0.171 |          0.136 |   4.454 |         2.589 |                1.964 |          0.370 |
| timbre-v2.5 | numbers       | hi-IN      |       1 |          0.667 |          0.279 |   3.294 |         3.049 |                0.969 |          0.233 |
| timbre-v3.0 | numbers       | hi-IN      |       1 |          0.583 |          0.262 |   4.162 |         2.287 |                1.864 |          0.348 |
| timbre-v2.5 | numbers       | ta-IN      |       1 |          0.714 |          0.483 |   2.945 |         2.124 |                0.903 |          0.257 |
| timbre-v3.0 | numbers       | ta-IN      |       1 |          0.571 |          0.433 |   4.240 |         1.709 |                1.829 |          0.440 |
| timbre-v2.5 | question      | en-IN      |       2 |          0.000 |          0.000 |   3.835 |         5.148 |                0.661 |          0.417 |
| timbre-v3.0 | question      | en-IN      |       2 |          0.000 |          0.000 |   4.235 |         4.086 |                1.464 |          0.817 |
| timbre-v2.5 | question      | hi-IN      |       1 |          0.000 |          0.000 |   3.608 |         4.755 |                0.811 |          0.507 |
| timbre-v3.0 | question      | hi-IN      |       1 |          0.000 |          0.000 |   3.915 |         4.127 |                1.154 |          0.577 |
| timbre-v2.5 | question      | ta-IN      |       1 |          0.000 |          0.000 |   3.767 |         2.717 |                0.892 |          0.507 |
| timbre-v3.0 | question      | ta-IN      |       1 |          0.000 |          0.000 |   4.400 |         2.315 |                1.108 |          0.462 |
| timbre-v2.5 | special       | en-IN      |       1 |          0.056 |          0.022 |   3.833 |         2.425 |                1.619 |          0.211 |
| timbre-v3.0 | special       | en-IN      |       1 |          0.056 |          0.011 |   4.387 |         2.038 |                3.043 |          0.343 |
| timbre-v2.5 | statement     | en-IN      |       2 |          0.000 |          0.000 |   3.906 |         5.008 |                0.727 |          0.447 |
| timbre-v3.0 | statement     | en-IN      |       2 |          0.000 |          0.000 |   4.457 |         4.272 |                1.084 |          0.538 |
| timbre-v2.5 | statement     | hi-IN      |       1 |          0.000 |          0.000 |   3.765 |         4.167 |                0.654 |          0.408 |
| timbre-v3.0 | statement     | hi-IN      |       1 |          0.000 |          0.000 |   3.993 |         3.676 |                1.314 |          0.747 |
| timbre-v2.5 | statement     | ta-IN      |       1 |          0.000 |          0.000 |   3.670 |         3.049 |                0.802 |          0.502 |
| timbre-v3.0 | statement     | ta-IN      |       1 |          0.000 |          0.000 |   4.305 |         2.273 |                1.005 |          0.524 |

## Numbers: raw digits vs pre-spelled input (intelligibility WER)

The Timbre docs recommend sending numbers as words. This measures how much it matters.

| model       | id        |   raw |   spelled |
|:------------|:----------|------:|----------:|
| timbre-v2.5 | en_num_01 | 0.000 |     0.000 |
| timbre-v2.5 | en_num_02 | 0.500 |     0.000 |
| timbre-v2.5 | en_num_03 | 0.000 |     0.000 |
| timbre-v2.5 | en_num_04 | 0.000 |     0.000 |
| timbre-v2.5 | en_num_05 | 0.600 |     0.600 |
| timbre-v2.5 | en_num_06 | 0.400 |     0.000 |
| timbre-v2.5 | hi_num_01 | 0.667 |     0.583 |
| timbre-v2.5 | ta_num_01 | 0.714 |     0.714 |
| timbre-v3.0 | en_num_01 | 0.000 |     0.000 |
| timbre-v3.0 | en_num_02 | 0.500 |     0.214 |
| timbre-v3.0 | en_num_03 | 0.000 |     0.000 |
| timbre-v3.0 | en_num_04 | 0.000 |     0.000 |
| timbre-v3.0 | en_num_05 | 0.600 |     0.600 |
| timbre-v3.0 | en_num_06 | 0.000 |     0.000 |
| timbre-v3.0 | hi_num_01 | 0.583 |     0.333 |
| timbre-v3.0 | ta_num_01 | 0.571 |     0.429 |

## Prosody: final pitch movement (semitones; questions should be > statements)

| model       | language   | category   |   final_rise_st |
|:------------|:-----------|:-----------|----------------:|
| timbre-v2.5 | en-IN      | question   |           1.785 |
| timbre-v2.5 | en-IN      | statement  |          -1.721 |
| timbre-v2.5 | hi-IN      | question   |           3.368 |
| timbre-v2.5 | hi-IN      | statement  |           2.496 |
| timbre-v2.5 | ta-IN      | question   |           2.228 |
| timbre-v2.5 | ta-IN      | statement  |         -16.896 |
| timbre-v3.0 | en-IN      | question   |           0.970 |
| timbre-v3.0 | en-IN      | statement  |          -5.503 |
| timbre-v3.0 | hi-IN      | question   |           3.185 |
| timbre-v3.0 | hi-IN      | statement  |           3.518 |
| timbre-v3.0 | ta-IN      | question   |          -0.824 |
| timbre-v3.0 | ta-IN      | statement  |          -7.776 |

## Streaming latency (SSE): time to first audio

| model       |   runs |   TTFA_p50_s |   TTFA_p95_s |   total_p50_s |   RTF_p50 |
|:------------|-------:|-------------:|-------------:|--------------:|----------:|
| timbre-v2.5 |     21 |        0.507 |        0.558 |         0.983 |     0.220 |
| timbre-v3.0 |     21 |        0.478 |        0.589 |         1.882 |     0.368 |

## Flagged for listening

- **timbre-v2.5 · ta_base_01** (baseline) WER 0.50, UTMOS 3.78
  - SENT: வணக்கம், உங்கள் மருத்துவ காப்பீட்டு பாலிசி பற்றி பேச அழைக்கிறேன்.
  - HEARD: வணக்கம் உங்கள் மருத்துவைக் காப்பிட்டு பாலிசி பற்றி பேசாழைக்கிறேன்

- **timbre-v2.5 · en_num_02** (numbers) WER 0.50, UTMOS 4.48
  - SENT: Please call us at 9876543210.
  - HEARD: Please call us at 987-654-3210.

- **timbre-v2.5 · en_num_05** (numbers) WER 0.60, UTMOS 4.37
  - SENT: Your appointment is at 3:30 PM on 2nd December.
  - HEARD: Your appointment is at 3.30 p.m. on 2nd December.

- **timbre-v2.5 · en_num_05__spelled** (numbers) WER 0.60, UTMOS 4.28
  - SENT: your appointment is at three thirty p m on second december
  - HEARD: Your appointment is at 3.30 p.m. on 2nd December.

- **timbre-v2.5 · en_num_06** (numbers) WER 0.40, UTMOS 4.33
  - SENT: Your policy number is SH2026004517.
  - HEARD: Your policy number is SH202 600 4517.

- **timbre-v2.5 · hi_num_01** (numbers) WER 0.67, UTMOS 3.29
  - SENT: आपका प्रीमियम ₹15,000 है और आखिरी तारीख 10 जनवरी है।
  - HEARD: आपका प्रेमियम 15,000 रुपय है और आख्री तारिख 10 जन्वरी है।

- **timbre-v2.5 · hi_num_01__spelled** (numbers) WER 0.58, UTMOS 3.43
  - SENT: आपका प्रीमियम पंद्रह हज़ार रुपये है और आखिरी तारीख दस जनवरी है
  - HEARD: आपका प्रेमियम 15,000 रुपे है और आख्री तारीख 10 जन्वरी है।

- **timbre-v2.5 · ta_num_01** (numbers) WER 0.71, UTMOS 2.94
  - SENT: உங்கள் பிரீமியம் தொகை ₹12,500 ஆகும்.
  - HEARD: உங்கள் பிரிமியம் தொகை 12,500 ருபாயாகும்

- **timbre-v2.5 · ta_num_01__spelled** (numbers) WER 0.71, UTMOS 3.09
  - SENT: உங்கள் பிரீமியம் தொகை பன்னிரண்டாயிரத்து ஐந்நூறு ரூபாய் ஆகும்
  - HEARD: உங்கள் பெரிமியம் தொகை 12,500 ரூபாயாகும்

- **timbre-v2.5 · ta_long_01** (long_form) WER 0.32, UTMOS 2.73
  - SENT: உங்கள் பாலிசி அடுத்த வாரம் புதுப்பிக்கப்பட வேண்டும். இப்போது பணம் செலுத்தினால், பத்து சதவீத தள்ளுபடி கிடைக்கும். பணம் செலுத்திய பிறகு, பாலிசி நகல் உங்கள் மின்னஞ்சலுக்கு அனுப்பப்படும். ஏதேனும் சந்தேகம் இருந்தால், காலை ஒன்பது மணி முதல் மாலை ஆறு மணி வரை எங்கள் வாடிக்கையாளர் சேவை மையத்தை தொடர்பு கொள்ளலாம்.
  - HEARD: உங்கள் பாலிசி அடுத்த வாரம் புதுப்பிக்கப் பட வேண்டும், இப்போது பணம் செலுத்தினால் பத்து சதவித தள்ளுப்படி கிடைக்கும் பணம் செலுத்திய பிறகு பாலிசி நகல் உங்கள் மின்னஞ்சலுக்கு அனுபப்படும் இதேனும் சந்தேகம் இருந்தால் காலை 9 மணி முதல் மாலை 6 மணி வர எங்கள் வாடிக்கையாளர் சேவை மயத்தை தொடர்புகொள்ளலாம்

- **timbre-v3.0 · en_num_02** (numbers) WER 0.50, UTMOS 4.56
  - SENT: Please call us at 9876543210.
  - HEARD: please call us at 987-654-3210.

- **timbre-v3.0 · en_num_05** (numbers) WER 0.60, UTMOS 4.43
  - SENT: Your appointment is at 3:30 PM on 2nd December.
  - HEARD: Your appointment is at 3.30 p.m. on 2nd December.

- **timbre-v3.0 · en_num_05__spelled** (numbers) WER 0.60, UTMOS 4.53
  - SENT: your appointment is at three thirty p m on second december
  - HEARD: Your appointment is at 3.30 p.m. on 2nd December.

- **timbre-v3.0 · hi_num_01** (numbers) WER 0.58, UTMOS 4.16
  - SENT: आपका प्रीमियम ₹15,000 है और आखिरी तारीख 10 जनवरी है।
  - HEARD: आपका प्रीमियम 15,000 रुपे है और आखरी तारीक 10 जन्वरी है।

- **timbre-v3.0 · hi_num_01__spelled** (numbers) WER 0.33, UTMOS 4.41
  - SENT: आपका प्रीमियम पंद्रह हज़ार रुपये है और आखिरी तारीख दस जनवरी है
  - HEARD: आपका प्रीमियम पंद्रा हजार रुपे है और आखिरी तारीक दस जन्वरी है

- **timbre-v3.0 · ta_num_01** (numbers) WER 0.57, UTMOS 4.24
  - SENT: உங்கள் பிரீமியம் தொகை ₹12,500 ஆகும்.
  - HEARD: உங்கள் பிரிமியம் தோகை 12,500 ரூபாய் ஆகும்.

- **timbre-v3.0 · ta_num_01__spelled** (numbers) WER 0.43, UTMOS 4.03
  - SENT: உங்கள் பிரீமியம் தொகை பன்னிரண்டாயிரத்து ஐந்நூறு ரூபாய் ஆகும்
  - HEARD: உங்கள் பெரிமியம் தொகை 12,500 ரூபாய் ஆகும்


## Failed requests

None.
