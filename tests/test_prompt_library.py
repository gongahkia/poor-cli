from poor_cli.prompt_library import PromptLibrary


def test_prompt_library_save_load_list_delete(tmp_path):
    lib = PromptLibrary(tmp_path)

    lib.save("example", "hello world")
    assert lib.load("example") == "hello world"
    assert lib.list_all() == ["example"]

    lib.delete("example")
    assert lib.list_all() == []
