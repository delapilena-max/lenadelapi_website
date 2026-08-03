# Lena ElevenLabs Voice Layer v1

Updated: 2026-08-02

## Decision

ElevenLabs is Lena's canonical generated-voice provider for the governed video lane. Voice is generated before video so every shot can be timed and lip-synced to the exact approved audio and alignment evidence.

## Production order

1. Author a `lena_video_prompt_v1` JSON specification.
2. Compile one deterministic ElevenLabs voice packet per spoken shot.
3. Generate and preserve the audio plus timestamp alignment.
4. Bind the resulting audio SHA-256 and alignment artifact into the later video handoff.
5. Generate the visual shot around that exact audio.
6. Run identity, voice, lip-sync, continuity, disclosure, and platform QA before queueing.

## Canonical surfaces

- `pipeline/schemas/lena_video_prompt_v1.schema.json`
- `pipeline/voice/lena_elevenlabs_voice_contract_v1.py`
- `tools/lena_compile_video_voice_manifest_v1.py`
- `pipeline/voice/lena_elevenlabs_executor_v1.py`
- `pipeline/examples/lena_video_prompt_v1.example.json`

## Secret and identity handling

The repository stores only environment-variable names:

- `ELEVENLABS_API_KEY`
- `ELEVENLABS_LENA_VOICE_ID`

The actual API key and Lena voice ID must remain in the canonical machine-local secret source. They must never be committed, printed, copied into JSON packets, or written into result manifests.

## Safety and activation

- Executor default is dry-run.
- `--live` is required for a provider call.
- One packet produces at most one provider request.
- Live execution fails closed unless both environment bindings exist.
- Alignment timestamps are mandatory for spoken shots.
- This addition does not activate video generation, queueing, publishing, or scheduling.
- A paid ElevenLabs proof and the permanent Lena voice selection still require explicit operator authorization.

## Quality intent

The canonical profile favors recognizable, natural delivery rather than exaggerated performance. Stability, similarity, style, speaker boost, speed, pronunciation, and pacing remain explicit structured settings so they can be tested and revised without changing the script or silently changing Lena's identity.
