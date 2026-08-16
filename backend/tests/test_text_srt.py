"""Unit tests: text chunking, SRT building/parsing, ffmpeg filter construction."""

from app.services import audio, srt, text
from app.services.srt import Cue, Word


def test_normalize_and_sentences():
    raw = "Xin chào!  Đây là câu hai.\r\nCâu ba không kết thúc\n\nĐoạn mới. Câu cuối?"
    sents = text.split_sentences(text.normalize(raw))
    assert sents == ["Xin chào!", "Đây là câu hai.", "Câu ba không kết thúc", "Đoạn mới.", "Câu cuối?"]


def test_chunk_respects_limit():
    sents = ["a" * 100 + "." for _ in range(30)]
    chunks = text.chunk_sentences(sents, max_chars=350)
    assert all(len(c) <= 350 for c in chunks)
    assert "".join(chunks).count("a") == 3000


def test_hard_split_long_sentence():
    s = ("word " * 200).strip()  # 999 chars no terminator
    chunks = text.chunk_sentences([s], max_chars=280)
    assert all(len(c) <= 280 for c in chunks)
    assert " ".join(chunks) == s


def test_safe_filename():
    assert text.safe_filename('Ch: "1" <a>/b\\c?') == "Ch 1 a b c"


def test_srt_roundtrip():
    cues = [Cue(0.0, 1.5, "Hello"), Cue(1.5, 3.25, "World, again")]
    out = srt.to_srt(cues)
    assert "00:00:01,500 --> 00:00:03,250" in out
    back = srt.parse_srt(out)
    assert [c.text for c in back] == ["Hello", "World, again"]
    assert abs(back[1].end - 3.25) < 1e-6


def test_parse_srt_lenient():
    content = "﻿1\r\n00:00:00,000 --> 00:00:01,000\r\n<i>Hi</i>\r\n\r\n00:00:02.000 --> 00:00:03.000\r\nline1\r\nline2\r\n"
    cues = srt.parse_srt(content)
    assert len(cues) == 2 and cues[0].text == "Hi" and cues[1].text == "line1 line2"


def test_words_to_cues_groups_on_punctuation_and_length():
    words = []
    t = 0.0
    for w in "Đây là câu một. Câu hai dài hơn một chút, có dấu phẩy. Cuối!".split():
        words.append(Word(t, t + 0.3, w))
        t += 0.35
    cues = srt.words_to_cues(words, max_chars=40)
    assert cues[0].text == "Đây là câu một."
    assert cues[-1].text.endswith("Cuối!")
    for a, b in zip(cues, cues[1:]):
        assert a.end <= b.start + 1e-9


def test_attach_punctuation():
    text = "Xin chào các bạn. Đây là câu hai, có phẩy!"
    words = [Word(i * 0.3, i * 0.3 + 0.25, w) for i, w in
             enumerate(["Xin", "chào", "các", "bạn", "Đây", "là", "câu", "hai", "có", "phẩy"])]
    out = srt.attach_punctuation(text, words)
    assert [w.text for w in out] == ["Xin", "chào", "các", "bạn.", "Đây", "là", "câu", "hai,", "có", "phẩy!"]
    cues = srt.words_to_cues(out)
    assert [c.text for c in cues] == ["Xin chào các bạn.", "Đây là câu hai, có phẩy!"]


def test_lrc_and_vtt():
    cues = [Cue(61.25, 62.0, "la la")]
    assert srt.to_lrc(cues).strip() == "[01:01.25]la la"
    assert "00:01:01.250 --> 00:01:02.000" in srt.to_vtt(cues)


def test_effects_filter():
    assert audio.effects_filter() is None
    assert audio.effects_filter(rate=1.5) == "atempo=1.5000"
    assert audio.effects_filter(rate=3.0).startswith("atempo=2.0,atempo=1.5000")
    f = audio.effects_filter(rate=1.2, keep_pitch=False, volume=0.8)
    assert f.startswith("asetrate=24000*1.2000,aresample=24000") and f.endswith("volume=0.800")
    assert "asetrate" in audio.effects_filter(pitch_semitones=2)
