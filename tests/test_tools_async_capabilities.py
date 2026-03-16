from poor_cli.sandbox import ToolCapability
from poor_cli.tools_async import ToolRegistryAsync


def test_builtin_tool_declarations_include_capability_metadata():
    registry = ToolRegistryAsync()
    declarations = {tool["name"]: tool for tool in registry.get_tool_declarations()}

    write_file = declarations["write_file"]["x-poor-cli"]
    bash = declarations["bash"]["x-poor-cli"]

    assert write_file["capabilities"] == [ToolCapability.FILESYSTEM_WRITE.value]
    assert write_file["mutating"] is True
    assert bash["capabilities"] == [ToolCapability.PROCESS_EXECUTE.value]
    assert bash["mutating"] is False


def test_external_tools_default_to_process_capability():
    registry = ToolRegistryAsync()

    async def _noop():
        return None

    registry.register_external_tool(
        "demo_external",
        _noop,
        {"name": "demo_external", "description": "Demo", "parameters": {"type": "OBJECT"}},
    )

    assert registry.get_tool_capabilities("demo_external") == [
        ToolCapability.PROCESS_EXECUTE.value
    ]
