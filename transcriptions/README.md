# Transcription Outputs

Generated on 2026-05-26 with offline `whisper.cpp` using `ggml-large-v3.bin`.

## Counts

- Audio manifest: 209 local audio files
- Wavlake MP3: 145 files, 29.996 hours
- Official Vimeo m4a local partial mirror: 64 files, 13.069 hours
- Total transcribed local audio: 43.064 hours

## Output Folders

- `raw-json/`: original Whisper JSON return files, preserved as generated
- `clean-json/`: parseable UTF-8 JSON normalized from raw JSON
- `text/`: plain text transcripts
- `srt/`: subtitle files
- `logs/`: per-file logs
- `metadata/transcription-summary.json`: machine-readable run summary

## Model

- Engine: `whisper.cpp` / `whisper-cli`
- Model: `models/whisper-cpp/ggml-large-v3.bin`
- SHA256: `64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2`
- Quantization: `ftype=1`, `qntvr=0`; this is the large-v3 F16-style model, not int8/q8/q5/q4
- Language: `zh`
- Beam/best-of: `5/5`
- Main batch: 4 workers, 3 threads per worker

## Quality Notes

All 209 local audio files have `raw-json`, `clean-json`, `txt`, and `srt` outputs. JSON validation passed with replacement decoding, and no text/SRT outputs are empty.

Two previously corrupted official m4a files were redownloaded from the official Vimeo player HLS audio-only source, verified with strict ffmpeg decoding, and re-transcribed:

- `official-vimeo-m4a-partial__010__52931080`: fixed duration 458.987s
- `official-vimeo-m4a-partial__062__9e655304`: fixed duration 1062.912s

Offline audio completeness: Wavlake RSS MP3 is complete locally at 145/145. The official website listed 157 Vimeo URLs, but the local official direct m4a mirror remains partial at 64 files; these 64 local m4a files were included in this transcription run.
