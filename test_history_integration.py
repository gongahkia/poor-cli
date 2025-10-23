"""
Test history integration in REPL
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poor_cli.repo_config import get_repo_config

def test_history():
    print("Testing history integration...")

    # Get repo config
    config = get_repo_config()
    print(f"\n1. Config directory: {config.config_dir}")
    print(f"   Exists: {config.config_dir.exists()}")

    # Start session
    print("\n2. Starting session...")
    session = config.start_session()
    print(f"   Session ID: {session.session_id}")

    # Add some messages
    print("\n3. Adding messages...")
    config.add_message("user", "Hello, how are you?")
    config.add_message("assistant", "I'm doing well, thanks!")
    config.add_message("user", "Can you help me?")
    config.add_message("assistant", "Of course!")
    print("   Added 4 messages")

    # Check if history file exists
    print(f"\n4. History file: {config.history_file}")
    print(f"   Exists: {config.history_file.exists()}")

    if config.history_file.exists():
        size = config.history_file.stat().st_size
        print(f"   Size: {size} bytes")

        # Read the file
        import json
        with open(config.history_file, 'r') as f:
            data = json.load(f)
        print(f"   Sessions in file: {len(data.get('sessions', []))}")

        # Check current session
        if config.current_session:
            print(f"   Current session messages: {len(config.current_session.messages)}")

    # Get session stats
    print("\n5. Session stats:")
    stats = config.get_session_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # Get all stats
    print("\n6. All sessions stats:")
    all_stats = config.get_all_sessions_stats()
    for key, value in all_stats.items():
        print(f"   {key}: {value}")

    # End session
    print("\n7. Ending session...")
    config.end_session()
    print("   Session ended")

    # Check file again
    print(f"\n8. After ending session:")
    print(f"   History file exists: {config.history_file.exists()}")
    if config.history_file.exists():
        with open(config.history_file, 'r') as f:
            data = json.load(f)
        print(f"   Sessions in file: {len(data.get('sessions', []))}")
        if data.get('sessions'):
            last_session = data['sessions'][-1]
            print(f"   Last session ID: {last_session['session_id']}")
            print(f"   Last session messages: {len(last_session['messages'])}")
            print(f"   Last session ended: {last_session.get('ended_at', 'Not set')}")

if __name__ == "__main__":
    test_history()
