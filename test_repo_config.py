"""
Test script for repo config and history functionality
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poor_cli.repo_config import RepoConfig, get_repo_config


def test_repo_config():
    """Test RepoConfig functionality"""
    print("=" * 60)
    print("Testing RepoConfig Functionality")
    print("=" * 60)

    # Test 1: Initialize repo config
    print("\n1. Initializing RepoConfig...")
    repo_config = RepoConfig()
    config_dir = repo_config.config_dir
    print(f"   ✓ Config directory: {config_dir}")
    print(f"   ✓ History file: {repo_config.history_file}")
    print(f"   ✓ Preferences file: {repo_config.preferences_file}")

    # Test 2: Start a session
    print("\n2. Starting new session...")
    session = repo_config.start_session("test-model")
    print(f"   ✓ Session ID: {session.session_id}")
    print(f"   ✓ Started at: {session.started_at}")

    # Test 3: Add messages
    print("\n3. Adding messages...")
    repo_config.add_message("user", "Hello, how are you?")
    print("   ✓ Added user message")
    repo_config.add_message("assistant", "I'm doing well, thank you!")
    print("   ✓ Added assistant message")
    repo_config.add_message("user", "Can you help me with Python?")
    print("   ✓ Added another user message")
    repo_config.add_message("assistant", "Of course! I'd be happy to help.")
    print("   ✓ Added another assistant message")

    # Test 4: Get session stats
    print("\n4. Getting session statistics...")
    stats = repo_config.get_session_stats()
    print(f"   ✓ Session ID: {stats['session_id']}")
    print(f"   ✓ Message count: {stats['message_count']}")
    print(f"   ✓ Tokens estimate: {stats['tokens_estimate']}")

    # Test 5: Test preferences
    print("\n5. Testing preferences...")
    print(f"   Auto-approve write: {repo_config.preferences.auto_approve_write}")
    print(f"   Auto-approve read: {repo_config.preferences.auto_approve_read}")
    print(f"   Auto-approve edit: {repo_config.preferences.auto_approve_edit}")
    print(f"   Auto-approve bash: {repo_config.preferences.auto_approve_bash}")

    # Test 6: Toggle a preference
    print("\n6. Toggling write preference...")
    repo_config.update_preference("auto_approve_write", True)
    print(f"   ✓ Auto-approve write: {repo_config.preferences.auto_approve_write}")
    assert repo_config.should_auto_approve("write") == True
    print("   ✓ should_auto_approve('write') returns True")

    # Test 7: End session
    print("\n7. Ending session...")
    repo_config.end_session()
    print("   ✓ Session ended and saved")

    # Test 8: Check files were created
    print("\n8. Verifying files...")
    if repo_config.history_file.exists():
        print(f"   ✓ History file created: {repo_config.history_file}")
        # Show file size
        size = repo_config.history_file.stat().st_size
        print(f"   ✓ History file size: {size} bytes")
    else:
        print(f"   ✗ History file not found")
        return False

    if repo_config.preferences_file.exists():
        print(f"   ✓ Preferences file created: {repo_config.preferences_file}")
        size = repo_config.preferences_file.stat().st_size
        print(f"   ✓ Preferences file size: {size} bytes")
    else:
        print(f"   ✗ Preferences file not found")
        return False

    # Test 9: Check .gitignore
    gitignore_file = config_dir / ".gitignore"
    if gitignore_file.exists():
        print(f"   ✓ .gitignore created: {gitignore_file}")
    else:
        print(f"   ~ .gitignore not found")

    # Test 10: Test global instance
    print("\n9. Testing global instance...")
    global_config = get_repo_config()
    print(f"   ✓ Global config directory: {global_config.config_dir}")

    # Get all sessions stats
    all_stats = global_config.get_all_sessions_stats()
    print(f"   ✓ Total sessions: {all_stats['total_sessions']}")
    print(f"   ✓ Total messages: {all_stats['total_messages']}")

    # Test 11: Read the JSON files
    print("\n10. Reading JSON files...")
    try:
        import json
        with open(repo_config.history_file, 'r') as f:
            history_data = json.load(f)
        print(f"   ✓ History JSON valid")
        print(f"   ✓ Sessions in file: {len(history_data['sessions'])}")

        with open(repo_config.preferences_file, 'r') as f:
            pref_data = json.load(f)
        print(f"   ✓ Preferences JSON valid")
        print(f"   ✓ Auto-approve write in file: {pref_data['auto_approve_write']}")
    except Exception as e:
        print(f"   ✗ Error reading JSON: {e}")
        return False

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return True


def cleanup():
    """Clean up test files"""
    print("\nCleaning up test files...")
    config_dir = Path.cwd() / ".poor-cli"
    if config_dir.exists():
        import shutil
        shutil.rmtree(config_dir)
        print(f"   ✓ Removed {config_dir}")


if __name__ == "__main__":
    try:
        success = test_repo_config()

        # Ask if user wants to cleanup
        response = input("\nRemove .poor-cli directory? (y/n): ").lower().strip()
        if response == 'y':
            cleanup()
        else:
            print(f"\nTest files kept in: {Path.cwd() / '.poor-cli'}")

        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
