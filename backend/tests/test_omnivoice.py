import sys
import types

import pytest

from app.voice import OmniVoiceProvider, SynthesisRequest, VoiceCloneRequest


@pytest.fixture(autouse=True)
def _fake_omnivoice_module(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("omnivoice")
    module.VoiceClonePrompt = type("VoiceClonePrompt", (), {"load": staticmethod(lambda p: p)})
    monkeypatch.setitem(sys.modules, "omnivoice", module)


class _FakePrompt:
    def __init__(self) -> None:
        self.saved: str | None = None

    def save(self, path: str) -> None:
        self.saved = path


class _FakeModel:
    def __init__(self) -> None:
        self.created: list = []
        self.generated: list = []
        self.prompt = _FakePrompt()

    def create_voice_clone_prompt(self, **kwargs) -> _FakePrompt:
        self.created.append(kwargs)
        return self.prompt

    def generate(self, **kwargs):
        self.generated.append(kwargs)

        class _FakeAudio:
            def clip(self, *a):
                return self

            def __mul__(self, other):
                return self

            def astype(self, dtype: str):
                return self

            def tobytes(self):
                return b"PCMDATA"

        return [_FakeAudio()]


@pytest.fixture
def model() -> _FakeModel:
    return _FakeModel()


def _provider(model: _FakeModel) -> OmniVoiceProvider:
    provider = OmniVoiceProvider(device_map="cpu", voice_dir="/tmp/voices-test")
    provider._model = model
    return provider


async def test_create_voice_clones_and_saves_prompt(model: _FakeModel, tmp_path) -> None:
    provider = _provider(model)
    provider._voice_dir = tmp_path
    result = await provider.create_voice(VoiceCloneRequest(name="teacher_a", ref_audio=b"WAVDATA", ref_text="hello"))
    assert result == "teacher_a"
    assert model.created
    assert model.created[0]["ref_text"] == "hello"
    assert model.prompt.saved == str(tmp_path / "teacher_a.pt")


async def test_synthesize_generates_with_saved_prompt(model: _FakeModel, tmp_path) -> None:
    provider = _provider(model)
    provider._voice_dir = tmp_path
    (tmp_path / "teacher_a.pt").write_bytes(b"prompt-bytes")
    chunks = [c async for c in provider.synthesize(SynthesisRequest(text="hi", voice_profile_id="teacher_a"))]
    assert chunks
    assert chunks[0].data == b"PCMDATA"
    assert chunks[0].sample_rate == 24000
    assert model.generated[0]["text"] == "hi"
