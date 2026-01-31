"""
Pytest configuration and fixtures.
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_python_code():
    """Sample Python code for testing."""
    return '''
def calculate_sum(numbers):
    """Calculate the sum of a list of numbers."""
    total = 0
    for num in numbers:
        total += num
    return total

def main():
    result = calculate_sum([1, 2, 3, 4, 5])
    print(f"Sum: {result}")

if __name__ == "__main__":
    main()
'''


@pytest.fixture
def sample_javascript_code():
    """Sample JavaScript code for testing."""
    return '''
function calculateSum(numbers) {
    let total = 0;
    for (const num of numbers) {
        total += num;
    }
    return total;
}

const result = calculateSum([1, 2, 3, 4, 5]);
console.log(`Sum: ${result}`);
'''


@pytest.fixture
def mock_api_key(monkeypatch):
    """Set mock API keys for testing."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key-12345")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-12345")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
