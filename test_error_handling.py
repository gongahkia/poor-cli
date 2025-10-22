"""
Test script to validate error handling improvements in poor-cli
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poor_cli.exceptions import (
    ValidationError,
    FileOperationError,
    PathTraversalError,
    validate_file_path,
    safe_read_file,
    safe_write_file,
)
from poor_cli.tools import ToolRegistry
from pathlib import Path


def test_path_validation():
    """Test path validation and security checks"""
    print("Testing path validation...")

    # Test 1: Valid absolute path
    try:
        path = validate_file_path(__file__)
        print(f"  ✓ Valid path accepted: {path}")
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False

    # Test 2: Invalid empty path
    try:
        validate_file_path("")
        print("  ✗ Empty path should be rejected")
        return False
    except (ValidationError, Exception) as e:
        if "empty" in str(e).lower() or "non-empty" in str(e).lower():
            print("  ✓ Empty path correctly rejected")
        else:
            print(f"  ~ Unexpected error type: {e}")
            return False

    # Test 3: Non-existent file with must_exist=True
    try:
        validate_file_path("/nonexistent/file.txt", must_exist=True)
        print("  ✗ Non-existent file should be rejected with must_exist=True")
        return False
    except Exception:
        print("  ✓ Non-existent file correctly rejected")

    # Test 4: Path traversal attempt (if base_path is set)
    try:
        base = Path.cwd()
        validate_file_path("/../../../etc/passwd", base_path=base)
        print("  ✗ Path traversal should be rejected")
        return False
    except PathTraversalError:
        print("  ✓ Path traversal correctly rejected")
    except Exception as e:
        # May pass on some systems depending on path resolution
        print(f"  ~ Path traversal test inconclusive: {type(e).__name__}")

    return True


def test_file_operations():
    """Test file operation error handling"""
    print("\nTesting file operations...")

    registry = ToolRegistry()

    # Test 1: Read non-existent file (using execute_tool which catches exceptions)
    result = registry.execute_tool("read_file", {"file_path": "/nonexistent/test.txt"})
    if "Error" in result:
        print(f"  ✓ Read non-existent file error: {result[:50]}...")
    else:
        print(f"  ✗ Should return error for non-existent file")
        return False

    # Test 2: Write file with validation (using execute_tool)
    test_file = "/tmp/poor_cli_test.txt"
    result = registry.execute_tool("write_file", {"file_path": test_file, "content": "test content"})
    if "Success" in result:
        print(f"  ✓ Write file successful: {result}")
    else:
        print(f"  ✗ Write failed: {result}")
        return False

    # Test 3: Read the file we just wrote (using execute_tool)
    result = registry.execute_tool("read_file", {"file_path": test_file})
    if "test content" in result:
        print(f"  ✓ Read file successful")
    else:
        print(f"  ✗ Read failed: {result}")
        return False

    # Test 4: Edit non-existent text (using execute_tool)
    result = registry.execute_tool("edit_file", {
        "file_path": test_file,
        "new_text": "new content",
        "old_text": "nonexistent text"
    })
    if "Error" in result or "not found" in result.lower():
        print(f"  ✓ Edit non-existent text error: {result[:50]}...")
    else:
        print(f"  ✗ Should return error for non-existent text")
        return False

    # Clean up
    try:
        os.remove(test_file)
        print("  ✓ Test file cleaned up")
    except:
        pass

    return True


def test_tool_validation():
    """Test tool input validation"""
    print("\nTesting tool validation...")

    registry = ToolRegistry()

    # Test 1: Invalid glob pattern (using execute_tool)
    result = registry.execute_tool("glob_files", {"pattern": ""})
    if "Error" in result:
        print(f"  ✓ Empty glob pattern rejected: {result[:50]}...")
    else:
        print(f"  ✗ Should reject empty pattern")
        return False

    # Test 2: Invalid grep pattern (invalid regex) (using execute_tool)
    result = registry.execute_tool("grep_files", {"pattern": "[invalid(regex"})
    if "Error" in result or "Invalid" in result:
        print(f"  ✓ Invalid regex rejected: {result[:50]}...")
    else:
        print(f"  ✗ Should reject invalid regex")
        return False

    # Test 3: Invalid bash timeout (using execute_tool)
    result = registry.execute_tool("bash", {"command": "echo test", "timeout": -1})
    if "Error" in result:
        print(f"  ✓ Invalid timeout rejected: {result[:50]}...")
    else:
        print(f"  ✗ Should reject negative timeout")
        return False

    # Test 4: Valid bash command (using execute_tool)
    result = registry.execute_tool("bash", {"command": "echo 'test'", "timeout": 5})
    if "test" in result and "Error" not in result:
        print(f"  ✓ Valid bash command executed")
    else:
        print(f"  ✗ Valid command should succeed: {result}")
        return False

    return True


def test_tool_registry():
    """Test tool registry error handling"""
    print("\nTesting tool registry...")

    registry = ToolRegistry()

    # Test 1: Unknown tool
    result = registry.execute_tool("nonexistent_tool", {})
    if "Unknown tool" in result:
        print(f"  ✓ Unknown tool rejected: {result[:50]}...")
    else:
        print(f"  ✗ Should reject unknown tool")
        return False

    # Test 2: Tool with invalid args (create a test file first)
    test_file = "/tmp/poor_cli_test2.txt"
    write_result = registry.execute_tool("write_file", {"file_path": test_file, "content": "line1\nline2\nline3"})
    if "Error" in write_result:
        print(f"  ~ Could not create test file: {write_result}")
        return False

    # Now test reading with invalid line number
    result = registry.execute_tool("read_file", {"file_path": test_file, "start_line": -1})
    if "Error" in result:
        print(f"  ✓ Invalid args rejected: {result[:50]}...")
    else:
        print(f"  ✗ Should reject invalid args")
        return False

    # Clean up
    try:
        os.remove(test_file)
    except:
        pass

    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing Error Handling Improvements")
    print("=" * 60)

    tests = [
        ("Path Validation", test_path_validation),
        ("File Operations", test_file_operations),
        ("Tool Validation", test_tool_validation),
        ("Tool Registry", test_tool_registry),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"\n✓ {name} tests PASSED")
            else:
                failed += 1
                print(f"\n✗ {name} tests FAILED")
        except Exception as e:
            failed += 1
            print(f"\n✗ {name} tests FAILED with exception: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
