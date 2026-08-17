"""Unit tests for the F5-TTS Vietnamese engine helpers (no model needed)."""

from pathlib import Path

import pytest

from app.services import f5, ffmpeg, prosody


def test_normalize_vi_lowercases_and_keeps_punctuation():
    assert f5.normalize_vi("  Xin  CHÀO,\nthế giới!  ") == "xin chào, thế giới!"


def test_pick_sample_maps_prosody_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(f5, "PROFILES_DIR", tmp_path)
    pid = "p1"
    f5._save_samples(pid, [  # noqa: SLF001
        {"emotion": "neutral", "wav": "n.wav", "text": "a", "duration": 3.0},
        {"emotion": "sad", "wav": "s.wav", "text": "b", "duration": 3.0},
        {"emotion": "angry", "wav": "g.wav", "text": "c", "duration": 3.0},
    ])
    assert f5.pick_sample(pid, ["sad", "para"])["emotion"] == "sad"
    assert f5.pick_sample(pid, ["trailing"])["emotion"] == "sad"
    assert f5.pick_sample(pid, ["anger"])["emotion"] == "angry"
    # unknown / unavailable emotions fall back to neutral
    assert f5.pick_sample(pid, ["joy"])["emotion"] == "neutral"
    assert f5.pick_sample(pid, None)["emotion"] == "neutral"
    # classify → tags → sample: end-to-end with the prosody planner
    seg = prosody.classify("Cô ấy khóc nức nở suốt đêm.")
    assert f5.pick_sample(pid, seg.tags)["emotion"] == "sad"


def test_pick_sample_requires_samples(tmp_path, monkeypatch):
    monkeypatch.setattr(f5, "PROFILES_DIR", tmp_path)
    with pytest.raises(RuntimeError):
        f5.pick_sample("none", ["sad"])


@pytest.mark.skipif(not ffmpeg.is_available(), reason="ffmpeg not installed")
def test_add_and_remove_sample_with_given_text(tmp_path, monkeypatch):
    monkeypatch.setattr(f5, "PROFILES_DIR", tmp_path)
    src = tmp_path / "src.wav"
    # 4 s of a 220 Hz tone (loud enough to survive silence trimming)
    ffmpeg.run(["-f", "lavfi", "-i", "sine=frequency=220:duration=4", "-ac", "1", "-ar", "16000", str(src)])
    item = f5.add_sample("p2", "happy", src, text="Vui quá đi thôi!")
    assert item["emotion"] == "happy" and item["text"] == "Vui quá đi thôi!"
    assert Path(item["wav"]).exists() and 3.0 <= item["duration"] <= 4.2
    assert [s["emotion"] for s in f5.list_samples("p2")] == ["happy"]
    with pytest.raises(ValueError):
        f5.add_sample("p2", "bogus", src, text="x")
    f5.remove_sample("p2", "happy")
    assert f5.list_samples("p2") == [] and not Path(item["wav"]).exists()
