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


def test_torch_index_by_driver():
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=None):
        assert clone._torch_index().endswith("/cpu")
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=11.1):
        assert clone._torch_index().endswith("/cpu")
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=11.8):
        assert clone._torch_index().endswith("/cu118")
    with mock.patch.object(clone, "nvidia_driver_cuda", return_value=12.8):
        assert clone._torch_index().endswith("/cu126")
