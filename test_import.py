"""
Simple test to verify imports work correctly
"""

def test_imports():
    """Test that all modules can be imported"""
    try:
        from poor_cli import gemini_client
        from poor_cli import tools
        from poor_cli import repl
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_tool_registry():
    """Test that tool registry initializes correctly"""
    try:
        from poor_cli.tools import ToolRegistry

        registry = ToolRegistry()
        tools = registry.get_tool_declarations()

        print(f"✓ Tool registry initialized with {len(tools)} tools")

        # Check all expected tools are present
        expected_tools = ['read_file', 'write_file', 'edit_file', 'glob_files', 'grep_files', 'bash']
        tool_names = [tool['name'] for tool in tools]

        for expected in expected_tools:
            if expected in tool_names:
                print(f"  ✓ {expected}")
            else:
                print(f"  ✗ {expected} missing")
                return False

        return True
    except Exception as e:
        print(f"✗ Tool registry test failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing poor-cli structure...\n")

    success = True
    success = test_imports() and success
    print()
    success = test_tool_registry() and success

    print("\n" + ("="*50))
    if success:
        print("✓ All tests passed!")
        print("\nTo run poor-cli:")
        print("1. Set GEMINI_API_KEY in .env file")
        print("2. Run: ./run.sh or python -m poor_cli")
    else:
        print("✗ Some tests failed")
    print("="*50)
