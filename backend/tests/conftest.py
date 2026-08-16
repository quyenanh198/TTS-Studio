"""Isolate tests from the real user data dir: point TTS_STUDIO_DATA at a temp folder BEFORE app import."""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="ttsstudio-test-")
os.environ.setdefault("TTS_STUDIO_DATA", _TMP)
