# Lena Video JSON Production System V1

This package makes validated, versioned JSON the source authority for Lena's
separately governed video lane. V1 compiles one complete eight-second, 720p,
9:16 video specification into a provider-neutral plan and an
execution-disabled Higgsfield request. It has no provider executor, credential,
network, scheduler, publishing, media-generation, or live photo-lane dependency.

Start with `documentation/LENA_VIDEO_JSON_PRODUCTION_SYSTEM_V1.md`. The complete
SpaceX launch example is under `pilots/spacex_launch_001/` and validates with:

```text
C:\Python314\python.exe -B -m tools.lena_video_validate_v1 --video-root pipeline/media_properties/lena/video/pilots/spacex_launch_001 --validate-only
```

Compile it in memory without writing or executing anything with:

```text
C:\Python314\python.exe -B -m tools.lena_video_compile_higgsfield_v1 --video-root pipeline/media_properties/lena/video/pilots/spacex_launch_001 --validate-only
```
