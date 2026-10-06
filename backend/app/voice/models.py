from pydantic import BaseModel, Field


class VoiceProfile(BaseModel):
    voice_profile_id: str
    language: str = "en"
    style: str = "friendly_beginner"
    speaking_speed: float = Field(default=1.0, ge=0.5, le=2.0)


class VoiceCloneRequest(BaseModel):
    name: str
    ref_audio: bytes
    ref_text: str | None = None


class SynthesisRequest(BaseModel):
    text: str
    voice_profile_id: str
    language: str | None = None
    speaking_speed: float | None = None


class AudioChunk(BaseModel):
    """One streamed piece of synthesized audio (PCM bytes by default)."""

    data: bytes
    sample_rate: int = 24000
    format: str = "pcm16"
    sequence: int = 0
