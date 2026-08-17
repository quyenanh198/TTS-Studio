"""Unit tests for clone helpers that don't need torch/seed-vc installed."""

from unittest import mock

from app.services import clone


def test_drain_generator_return_value():
    def gen():
        yield (b"mp3", [1, 2])
        return [9, 9, 9]

    assert clone._drain(gen()) == [9, 9, 9]


def test_drain_generator_last_yield():
    def gen():
        yield (b"a", [1])
        yield (b"b", [2, 2])

    assert clone._drain(gen()) == [2, 2]


def test_drain_passthrough():
    assert clone._drain([1, 2, 3]) == [1, 2, 3]


def test_verify_cache_discards_unreadable_repo(tmp_path, monkeypatch):
    """A snapshot file that cannot be opened (dangling symlink / WinError 448 / EINVAL) must get the
    whole repo moved aside so Hugging Face re-downloads it; healthy repos stay."""
    monkeypatch.setattr(clone, "SEEDVC_MODELS_DIR", tmp_path)
    good = tmp_path / "models--good" / "snapshots" / "abc"
    good.mkdir(parents=True)
    (good / "config.yml").write_text("ok")
    bad = tmp_path / "models--Plachta--Seed-VC" / "snapshots" / "def"
    bad.mkdir(parents=True)
    (bad / "config.yml").write_text("x")
    real_open = open

    def flaky_open(f, *a, **k):
        if str(f).endswith("def" + "\\config.yml") or str(f).endswith("def/config.yml"):
            raise OSError(22, "Invalid argument")
        return real_open(f, *a, **k)

    with mock.patch("builtins.open", flaky_open):
        removed = clone._verify_cache()
    assert removed == ["models--Plachta--Seed-VC"]
    assert not (tmp_path / "models--Plachta--Seed-VC").exists()
    assert (good / "config.yml").exists()
    assert not list(tmp_path.glob("*.broken-*"))  # fully deleted when the FS allows it


def test_torch_index_by_driver():
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=None):
        assert clone._torch_index().endswith("/cpu")
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=11.1):
        assert clone._torch_index().endswith("/cpu")
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=11.8):
        assert clone._torch_index().endswith("/cu118")
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=12.8):
        assert clone._torch_index().endswith("/cu126")
