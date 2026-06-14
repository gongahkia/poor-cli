from counter import count_lines


def test_counts_final_line_without_newline() -> None:
    assert count_lines("one\ntwo") == 2
