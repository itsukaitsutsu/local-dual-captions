from bridge.text import clean_transcript, join_japanese, strip_overlap


def test_japanese_shared_boundary():
    assert strip_overlap("日本語を勉強しています。", "勉強しています。そして英語も学びます。",
                         has_audio_overlap=True) == "そして英語も学びます。"


def test_genuinely_repeated_phrase_is_preserved_without_shared_audio():
    phrase = "ありがとうございます。"
    assert strip_overlap(phrase, phrase, has_audio_overlap=False) == phrase


def test_no_fuzzy_deletion():
    assert strip_overlap("この道を進みます。", "この町を見ています。", has_audio_overlap=True) == "この町を見ています。"


def test_whole_duplicate_from_shared_audio():
    assert strip_overlap("本日は晴天です。", "本日は晴天です。", has_audio_overlap=True) == ""


def test_text_cleanup_and_bounded_utterance():
    assert clean_transcript(" <|notimestamps|>  今日は\n 晴れです。 ") == "今日は 晴れです。"
    assert join_japanese("今日は", "晴れです。") == "今日は晴れです。"
    assert len(join_japanese("日" * 300, "本" * 100)) == 320
