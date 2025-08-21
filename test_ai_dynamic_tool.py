#!/usr/bin/env python3
"""
Test the AI-powered dynamic tool creator
Run this after installing openai and setting OPENAI_API_KEY environment variable
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.tools.dynamic_tool_creator import create_dynamic_tool


def test_ai_dynamic_tool():
    """Test AI-powered dynamic tool creation"""

    # Test requests that show AI capabilities
    test_requests = [
        "create a Python script that fetches weather data from openweathermap using WEATHER_API_KEY provided in folder and check the current weather for Ho Chi Minh City",
        "create a simple script to fetch and display the current date and time",
        "create a Python application to calculate the factorial of a number 10 and give me the result",
        "create a simple script to generate a random password with 12 characters",
        "create a simple script to check memory usage",
    ]

    print("🤖 Testing AI-Powered Dynamic Tool Creator")
    print("=" * 60)
    print("Note: Requires OPENAI_API_KEY environment variable to be set")
    print("📱 Each test result will be sent to your Telegram bot!")
    print("=" * 60)

    for i, request in enumerate(test_requests, 1):
        print(f"\n{i}. AI Request: {request}")
        print("-" * 50)

        try:
            # Test WITH sending to Telegram for each request
            result = create_dynamic_tool(
                user_request=request,
                preferred_language="auto",
                send_to_telegram=True,  # Changed to True to send each result to Telegram
            )

            if result["success"]:
                print(f"✅ AI SUCCESS - Language: {result['language']}")
                print(f"📁 Generated file: dynamic_commands/{result['filename']}")
                print(f"📤 Output preview: {result['stdout'][:200]}...")

                # Show a snippet of the generated code
                code_lines = result["code"].split("\\n")[:10]
                print(f"🔧 Generated code preview:")
                for line in code_lines:
                    print(f"    {line}")
                print("    ...")

            else:
                error_msg = result.get("error", result.get("stderr", "Unknown error"))
                print(f"❌ FAILED - {error_msg}")
                if result.get("stderr"):
                    print(f"Error details: {result['stderr'][:200]}...")
                if result.get("stdout"):
                    print(f"Output before error: {result['stdout'][:200]}...")

        except Exception as e:
            print(f"❌ EXCEPTION: {str(e)}")

    print(f"\n🎉 AI Testing completed!")
    print(f"📂 Check the dynamic_commands/ folder for all generated scripts")
    print(f"📱 All test results have been sent to your Telegram bot!")

    # Final test with explicit Telegram integration message
    print(f"\n📱 Testing final Telegram integration message...")
    try:
        result = create_dynamic_tool(
            user_request="Final test: Show current system info and confirm all tests completed",
            preferred_language="python",
            send_to_telegram=True,
        )

        if result["success"]:
            print(
                "✅ Final Telegram test successful! All tests completed and sent to Telegram."
            )
        else:
            error_msg = result.get("error", result.get("stderr", "Unknown"))
            print(f"❌ Final Telegram test failed: {error_msg}")
            if result.get("stderr"):
                print(f"Final test error details: {result['stderr'][:200]}...")

    except Exception as e:
        print(f"❌ Telegram test failed: {str(e)}")


if __name__ == "__main__":
    # Check if OpenAI API key is available
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not found in environment variables")
        print("   The tool will use fallback templates instead of AI generation")
        print("   To use AI features, set: export OPENAI_API_KEY='your-key-here'")
        print("")

    test_ai_dynamic_tool()
