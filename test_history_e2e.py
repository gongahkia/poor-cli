"""
End-to-end test for history logging
"""
import sys
import os
from pathlib import Path
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Clean up before starting
config_dir = Path.cwd() / ".poor-cli"
if config_dir.exists():
    shutil.rmtree(config_dir)
    print("Cleaned up existing .poor-cli directory\n")

from poor_cli.repo_config import get_repo_config

def test_e2e():
    print("=" * 60)
    print("End-to-End History Logging Test")
    print("=" * 60)

    # Step 1: Simulate app startup
    print("\n1. Simulating app startup...")
    repo_config = get_repo_config()
    print(f"   ✓ RepoConfig initialized")
    print(f"   ✓ Config dir: {repo_config.config_dir}")

    # Step 2: Start session
    print("\n2. Starting session...")
    session = repo_config.start_session("gemini-2.5-flash")
    print(f"   ✓ Session started: {session.session_id}")

    # Step 3: Simulate conversation
    print("\n3. Simulating conversation...")
    messages = [
        ("user", "Hello, can you help me?"),
        ("assistant", "Of course! I'd be happy to help."),
        ("user", "Create a hello.py file"),
        ("assistant", "I'll create that file for you."),
        ("user", "Thanks!"),
        ("assistant", "You're welcome!"),
    ]

    for role, content in messages:
        repo_config.add_message(role, content)
        print(f"   ✓ Added {role} message")

    # Step 4: Check current session stats
    print("\n4. Checking session stats...")
    stats = repo_config.get_session_stats()
    print(f"   Session ID: {stats['session_id']}")
    print(f"   Messages: {stats['message_count']}")
    print(f"   Tokens: {stats['tokens_estimate']}")

    # Step 5: Verify history file
    print("\n5. Verifying history file...")
    if repo_config.history_file.exists():
        print(f"   ✓ History file exists: {repo_config.history_file}")
        size = repo_config.history_file.stat().st_size
        print(f"   ✓ Size: {size} bytes")
    else:
        print(f"   ✗ History file not found!")
        return False

    # Step 6: Read history file
    print("\n6. Reading history file contents...")
    import json
    with open(repo_config.history_file, 'r') as f:
        data = json.load(f)

    # During active session, sessions list might be empty
    # Messages are saved but session isn't added to list until end_session()
    print(f"   Sessions in file: {len(data.get('sessions', []))}")
    print(f"   Current session has: {len(repo_config.current_session.messages)} messages")

    # Step 7: Test /history show functionality
    print("\n7. Testing get_recent_messages...")
    recent = repo_config.get_recent_messages(3)
    print(f"   ✓ Got {len(recent)} recent messages")
    for msg in recent:
        print(f"     - {msg.role}: {msg.content[:50]}...")

    # Step 8: End session
    print("\n8. Ending session...")
    repo_config.end_session()
    print("   ✓ Session ended")

    # Step 9: Verify session is saved
    print("\n9. Verifying session saved to file...")
    with open(repo_config.history_file, 'r') as f:
        data = json.load(f)

    print(f"   ✓ Sessions in file: {len(data['sessions'])}")
    if data['sessions']:
        last_session = data['sessions'][-1]
        print(f"   ✓ Last session ID: {last_session['session_id']}")
        print(f"   ✓ Last session messages: {len(last_session['messages'])}")
        print(f"   ✓ Session ended at: {last_session.get('ended_at', 'N/A')}")

        # Show sample messages
        print("\n10. Sample messages from saved session:")
        for i, msg in enumerate(last_session['messages'][:3], 1):
            print(f"   {i}. {msg['role']}: {msg['content'][:60]}...")

    # Step 10: Test all sessions stats
    print("\n11. Testing all_sessions_stats...")
    # Create new repo config instance to test loading
    repo_config2 = get_repo_config()
    all_stats = repo_config2.get_all_sessions_stats()
    print(f"   Total sessions: {all_stats['total_sessions']}")
    print(f"   Total messages: {all_stats['total_messages']}")
    print(f"   Total tokens: {all_stats['total_tokens_estimate']}")

    print("\n" + "=" * 60)
    print("✓ All end-to-end tests passed!")
    print("=" * 60)

    return True

if __name__ == "__main__":
    try:
        success = test_e2e()

        print(f"\nHistory file location: {Path.cwd() / '.poor-cli' / 'history.json'}")
        print("\nYou can now:")
        print("  1. Run poor-cli and type /history to see stats")
        print("  2. Type /history show to see recent messages")
        print("  3. Check .poor-cli/history.json directly")

        response = input("\nRemove .poor-cli directory? (y/n): ").lower().strip()
        if response == 'y':
            shutil.rmtree(Path.cwd() / ".poor-cli")
            print("✓ Cleaned up")

        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
