from slugify import slugify


def test_slugify_replaces_spaces() -> None:
    assert slugify("Hello Poor CLI") == "hello-poor-cli"
