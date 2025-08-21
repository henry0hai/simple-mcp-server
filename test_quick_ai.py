#!/usr/bin/env python3
"""
Quick test for AI improvements
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.tools.dynamic_tool_creator import create_dynamic_tool


def test_fixes():
    """Test the specific fixes we made"""

    # Test memory usage with improved bash
    print("🔧 Testing memory usage script (bash, macOS compatible)...")
    result = create_dynamic_tool(
        user_request="create a simple script to check memory usage on macOS",
        preferred_language="bash",
        send_to_telegram=False,
    )

    if result["success"]:
        print("✅ Memory script SUCCESS")
        print(f"Output: {result['stdout'][:100]}...")
    else:
        print("❌ Memory script FAILED")
        print(f"Error: {result.get('stderr', result.get('error', 'Unknown'))[:200]}")

    # Test weather API with correct config attribute
    print("\n🌤️  Testing weather API with correct config...")
    result = create_dynamic_tool(
        user_request="create a Python script to get weather for Ho Chi Minh City using the weather API",
        preferred_language="python",
        send_to_telegram=False,
    )

    if result["success"]:
        print("✅ Weather script SUCCESS")
        print(f"Output: {result['stdout'][:100]}...")
    else:
        print("❌ Weather script FAILED")
        print(f"Error: {result.get('stderr', result.get('error', 'Unknown'))[:200]}")


if __name__ == "__main__":
    test_fixes()
