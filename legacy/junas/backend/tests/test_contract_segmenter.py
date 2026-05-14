from data.parsers.contract_segmenter import segment_contract, split_sentences


def test_segment_contract_splits_numbered_sections() -> None:
    text = (
        "SECTION 1. DEFINITIONS. This section defines terms used in the agreement.\n\n"
        "SECTION 2. GOVERNING LAW. This agreement is governed by New York law.\n\n"
        "SECTION 3. TERMINATION. Either party may terminate upon written notice."
    )
    segments = segment_contract(text)
    assert len(segments) == 3
    assert segments[0]["text"].startswith("SECTION 1.")
    assert segments[1]["text"].startswith("SECTION 2.")
    assert segments[2]["text"].startswith("SECTION 3.")


def test_segment_contract_falls_back_to_double_newline_split() -> None:
    text = "Alpha clause content here.\n\nBeta clause content here.\n\nGamma clause."
    segments = segment_contract(text)
    assert len(segments) == 3
    assert segments[0]["text"].startswith("Alpha")
    assert segments[1]["text"].startswith("Beta")


def test_split_sentences_handles_english_and_chinese_punctuation() -> None:
    text = (
        "By using the service, you agree to these terms. We may terminate your account at any time. "
        "继续使用即表示同意本协议。我们可以随时修改条款。"
    )
    sentences = split_sentences(text, min_length=5)
    assert len(sentences) >= 4
    assert any("agree to these terms" in sentence for sentence in sentences)
    assert any("继续使用即表示同意本协议" in sentence for sentence in sentences)
