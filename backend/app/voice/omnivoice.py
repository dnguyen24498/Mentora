import asyncio
import os
import tempfile

from collections.abc import AsyncIterator
from pathlib import Path

from app.voice.models import AudioChunk, SynthesisRequest, VoiceCloneRequest
from app.voice.provider import VoiceProvider


class OmniVoiceProvider(VoiceProvider):
    """Wraps the official OmniVoice library (k2-fsa/OmniVoice).

    OmniVoice is a Python library, not a REST service, so this provider imports
    it lazily and keeps the heavy model cached. Voice clones are saved as
    reusable prompts so a teacher's voice is encoded once and reused later.
    """

    name = "omnivoice"

    def __init__(
        self,
        model_id: str = "k2-fsa/OmniVoice",
        device_map: str = "cpu",
        dtype: str | None = None,
        voice_dir: str | Path = ".voices",
    ) -> None:
        self._model_id = model_id
        self._device_map = device_map
        self._dtype = dtype
        self._voice_dir = Path(voice_dir)
        self._model = None

    def _load_model(self):
        if self._model is None:
            from omnivoice import OmniVoice
            import torch

            kwargs: dict = {"device_map": self._device_map}
            if self._dtype:
                kwargs["dtype"] = getattr(torch, self._dtype)
            self._model = OmniVoice.from_pretrained(self._model_id, **kwargs)
        return self._model

    async def create_voice(self, request: VoiceCloneRequest) -> str:
        model = self._load_model()
        self._voice_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(request.ref_audio)
            tmp_path = f.name
        try:
            def _clone():
                kwargs = {"ref_audio": tmp_path}
                if request.ref_text:
                    kwargs["ref_text"] = request.ref_text
                return model.create_voice_clone_prompt(**kwargs)

            prompt = await asyncio.to_thread(_clone)
            prompt.save(str(self._voice_dir / f"{request.name}.pt"))
        finally:
            os.unlink(tmp_path)
        return request.name

    async def synthesize(self, request: SynthesisRequest) -> AsyncIterator[AudioChunk]:
        model = self._load_model()
        prompt_path = self._voice_dir / f"{request.voice_profile_id}.pt"

        def _generate():
            kwargs = {"text": request.text}
            if prompt_path.exists():
                from omnivoice import VoiceClonePrompt

                kwargs["voice_clone_prompt"] = VoiceClonePrompt.load(str(prompt_path))
            if request.speaking_speed:
                kwargs["speed"] = request.speaking_speed
            return model.generate(**kwargs)

        audio = await asyncio.to_thread(_generate)
        pcm = (audio[0].clip(-1.0, 1.0) * 32767).astype("int16").tobytes()
        yield AudioChunk(data=pcm, sample_rate=24000, format="pcm16", sequence=0)
