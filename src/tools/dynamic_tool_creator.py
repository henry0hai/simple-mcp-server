import os
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import requests
from src.config.config import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI library not installed. Using fallback templates.")


class DynamicToolCreator:
    """
    A tool that dynamically generates and executes code based on user requests,
    saves them in dynamic_commands/ folder, and sends results back via Telegram.
    """

    def __init__(self):
        # Use project's dynamic_commands directory instead of /tmp
        self.project_root = Path(__file__).parent.parent.parent
        self.commands_dir = self.project_root / "dynamic_commands"
        self.commands_dir.mkdir(exist_ok=True)

        # Initialize OpenAI if available
        if (
            OPENAI_AVAILABLE
            and hasattr(config, "openai_api_key")
            and config.openai_api_key
        ):
            openai.api_key = config.openai_api_key
            self.ai_enabled = True
            logger.info("OpenAI API initialized for dynamic code generation")
        else:
            self.ai_enabled = False
            logger.warning(
                "OpenAI API not available. Please install openai library and set OPENAI_API_KEY."
            )

        # Create a README file if it doesn't exist
        readme_file = self.commands_dir / "README.md"
        if not readme_file.exists():
            with open(readme_file, "w") as f:
                f.write(
                    """# Dynamic Commands

This directory contains dynamically generated scripts created by the AI assistant.

- **Python scripts**: Have access to all installed packages and src.config.config
- **Bash scripts**: Can use standard Unix utilities
- **Generated files**: Are persistent and can be reused
- **AI Generated**: Scripts are dynamically created using OpenAI API

Generated at: """
                    + datetime.now().isoformat()
                    + "\n"
                )

    def send_telegram_message(
        self, message: str, chat_id: Optional[str] = None
    ) -> bool:
        """Send a message to Telegram bot."""
        try:
            if not chat_id:
                chat_id = config.admin_id

            url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

            response = requests.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Telegram message sent successfully")
                return True
            else:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending Telegram message: {str(e)}")
            return False

    def generate_code_from_request(
        self, user_request: str, preferred_language: str = "auto"
    ) -> Tuple[str, str, str]:
        """
        Generate intelligent code based on user request using AI.
        Returns: (code, language, filename)
        """
        request_lower = user_request.lower()

        # Security check: Reject dangerous requests
        dangerous_keywords = [
            "delete ",
            "remove ",
            "rm ",
            "mv ",
            "cp ",
            "chmod ",
            "chown ",
            "sudo ",
            "su ",
            "install ",
            "uninstall ",
            "modify ",
            "edit ",
            "write to",
            "create file",
            "mkdir ",
            ".ssh",
            ".env",
            "/etc/",
            "/var/",
            "/usr/",
            "/root/",
            "~/.config",
            "~/.cache",
            "bashrc",
            "zshrc",
            "passwd",
            "shadow",
            "hosts",
            "fstab",
            "crontab",
            "systemctl ",
            "service ",
            "daemon ",
            "kill ",
            "killall ",
            "pkill ",
            " format ",
            "fdisk ",
            "mount ",
            "umount ",
            "dd ",
            "shred ",
        ]

        for keyword in dangerous_keywords:
            if keyword in request_lower:
                raise ValueError(
                    f"Security violation: Request contains dangerous operation '{keyword.strip()}'. "
                    f"Only read-only system information and data processing scripts are allowed. "
                    f"File operations are restricted to $HOME/Downloads/ directory only."
                )

        # Additional dangerous patterns
        dangerous_patterns = [
            "deletes everything",
            "delete everything",
            "removes everything",
            "remove everything",
            "overwrite",
            "overwriting",
            "wipe",
            "wiping",
            "destroy",
            "destroying",
            "malicious",
            "malware",
            "virus",
            "hack",
            "exploit",
            "backdoor",
            "system files",
            "important files",
            "configuration files",
            "config files",
            "private key",
            "secret key",
            "password file",
            "credential",
            "firewall",
            "iptables",
            "security",
            "permission",
            "privilege",
        ]

        # Check dangerous patterns
        for pattern in dangerous_patterns:
            if pattern in request_lower:
                raise ValueError(
                    f"Security violation: Request contains dangerous pattern '{pattern}'. "
                    f"Only read-only system information and safe data processing scripts are allowed."
                )

        # Determine the best language for the task
        if preferred_language == "auto":
            # Force Python for API requests, weather data, calculations, etc.
            if any(
                keyword in request_lower
                for keyword in [
                    "python script",
                    "python application",
                    "api",
                    "weather",
                    "calculate",
                    "data",
                    "json",
                    "parse",
                    "analyze",
                    "process",
                    "fetch",
                    "request",
                ]
            ):
                language = "python"
            # Only use bash for simple system commands
            elif any(
                keyword in request_lower
                for keyword in ["date", "time", "password", "simple script"]
            ) and not any(
                keyword in request_lower
                for keyword in ["python", "application", "fetch", "api"]
            ):
                language = "bash"
            else:
                language = "python"  # Default to python for more complex tasks
        else:
            language = preferred_language

        # Generate code using AI or fallback to templates
        if self.ai_enabled:
            code = self._generate_ai_code(user_request, language)
        else:
            raise ValueError(
                "OpenAI API is required for dynamic code generation. Please install openai library and set OPENAI_API_KEY in your configuration."
            )

        # Generate meaningful filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Create a short descriptive name from the request
        clean_request = "".join(
            c for c in user_request.lower() if c.isalnum() or c.isspace()
        )
        words = clean_request.split()[:3]  # Take first 3 words
        description = "_".join(words) if words else "generic"

        if language == "bash":
            filename = f"{description}_{timestamp}.sh"
        else:
            filename = f"{description}_{timestamp}.py"

        return code, language, filename

    def _generate_ai_code(self, user_request: str, language: str) -> str:
        """Generate code using OpenAI API with template reference"""
        try:
            # Read the template for reference
            template_path = (
                self.commands_dir
                / "templates"
                / f"{language}_template.{language[:2] if language == 'bash' else 'py'}"
            )
            template_content = ""

            if template_path.exists():
                with open(template_path, "r") as f:
                    template_content = f.read()

            if language == "python":
                system_prompt = f"""You are an expert Python developer. Generate a complete, executable Python script based on the user's request.

CRITICAL SECURITY RESTRICTIONS:
- NEVER generate scripts that modify, delete, create, or write files outside of $HOME/Downloads/
- NEVER access sensitive directories: .ssh, .env, /etc, /var, /usr, /root, ~/.config, ~/.cache, etc.
- NEVER generate scripts that install packages, modify system settings, or change permissions
- NEVER access environment variables containing passwords, tokens, or credentials
- ONLY READ-ONLY operations are allowed for system information (CPU, memory, disk usage, etc.)
- File operations are ONLY allowed in $HOME/Downloads/ directory
- NEVER use sudo, chmod, chown, or system modification commands
- NEVER access network interfaces configuration or system network settings

ALLOWED OPERATIONS:
- Read system information (CPU, memory, disk usage, processes) - READ ONLY
- Make HTTP API requests to external services
- Read files from $HOME/Downloads/ directory ONLY
- Perform calculations and data processing
- Generate reports and display information
- Access project config for API keys (weather, telegram) for external requests

IMPORTANT: The script will execute from: {self.project_root}/dynamic_commands/
The project config is located at: {self.project_root}/src/config/config.py

Requirements:
1. Follow the structure and patterns from this template (pay attention to import paths):
```python
{template_content}
```

2. Use the EXACT same import structure as the template:
   - project_root = Path(__file__).parent.parent  # dynamic_commands/ -> project root
   - sys.path.append(str(project_root))
   - from src.config.config import config

3. Access config variables using these exact attribute names (ONLY for external API requests):
   - config.weather_api_key (for OpenWeatherMap API)
   - config.telegram_bot_token (for Telegram bot)
   - config.admin_id (for admin user ID)
   - config.openai_api_key (for OpenAI API)
   - config.weather_base_url (weather API base URL)

4. Include proper error handling and logging
5. Use appropriate imports and libraries (requests, json, os, sys, datetime, pathlib, etc.)
6. Include comprehensive comments and docstrings
7. Follow Python best practices
8. Make the script robust and production-ready
9. Add proper main() function and if __name__ == "__main__" guard
10. Handle exceptions gracefully
11. For system info tasks, use cross-platform Python libraries (READ-ONLY)
12. Always check if config is available before using: if config and config.attribute_name:
13. REFUSE requests that involve file manipulation outside $HOME/Downloads/
14. REFUSE requests that involve system configuration or security-related operations

Available libraries: requests, json, os, sys, datetime, pathlib, subprocess, shutil, csv, psutil, socket
Available project modules: src.config.config, src.utils.logging_utils

Generate only the Python code, no explanations or markdown formatting."""

            else:  # bash
                system_prompt = f"""You are an expert Bash script developer. Generate a complete, executable Bash script based on the user's request.

CRITICAL SECURITY RESTRICTIONS:
- NEVER generate scripts that modify, delete, create, or write files
- NEVER access sensitive directories: ~/.ssh, /etc, /var, /usr, /root, ~/.config, ~/.cache, etc.
- NEVER use commands: rm, mv, cp, touch, mkdir, chmod, chown, sudo, su, etc.
- NEVER modify system configurations or network settings
- NEVER access environment files like .env, .bashrc, .zshrc, etc.
- ONLY READ-ONLY operations for system information are allowed
- NEVER install or uninstall software
- NEVER modify user permissions or system settings

ALLOWED OPERATIONS:
- Display system information (READ-ONLY): date, uptime, whoami, hostname
- Check system resources (READ-ONLY): vm_stat, df -h, ps aux
- Generate random data: openssl rand
- Network information (READ-ONLY): ifconfig (display only)
- Simple calculations and text processing
- Display information with echo commands

CRITICAL: This script MUST run on macOS! Use only macOS-compatible commands and syntax.

Requirements:
1. Follow this template structure:
```bash
{template_content}
```

2. Use ONLY macOS-compatible READ-ONLY commands:
   - For IP display: `ifconfig | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{{print $2}}'`
   - For memory display: `vm_stat | head -n 10`
   - For password generation: `openssl rand -base64 12`
   - For uptime display: `uptime`
   - For disk display: `df -h`
   - For date/time: `date`
   - For processes: `ps aux | head -10`

3. Include proper error handling (set -e, set -u)
4. Test command availability with `if ! command -v cmd &> /dev/null`
5. Use simple, reliable variable assignments
6. Avoid any file system modifications
7. Add comprehensive error checking
8. Keep variables simple and well-defined
9. Use double quotes around variables: "$variable"
10. Don't use undefined variables (this causes "unbound variable" errors)
11. REFUSE requests that involve file manipulation, system modification, or accessing sensitive directories
12. Only display/read system information, never modify anything

IMPORTANT: When using `set -u`, make sure ALL variables are properly defined before use!

Generate only the Bash script code, no explanations or markdown formatting."""

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Create a {language} script for: {user_request}",
                },
            ]

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=3000,
                temperature=0.3,
            )

            generated_code = response.choices[0].message.content.strip()

            # Clean up the response (remove markdown code blocks if present)
            if generated_code.startswith("```"):
                lines = generated_code.split("\n")
                # Remove first and last lines if they contain ```
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                generated_code = "\n".join(lines)

            logger.info(
                f"Successfully generated {language} code using AI for: {user_request}"
            )
            return generated_code

        except Exception as e:
            logger.error(f"AI code generation failed: {str(e)}")
            raise ValueError(
                f"Failed to generate code using AI: {str(e)}. Please check your OpenAI API key and try again."
            )

    def execute_script(
        self, code: str, language: str, filename: str, timeout: int = 30
    ) -> Tuple[bool, str, str]:
        """
        Execute the generated script safely and keep it in dynamic_commands/.
        Returns: (success, stdout, stderr)
        """
        try:
            script_path = self.commands_dir / filename

            # Write the script to file
            with open(script_path, "w") as f:
                f.write(code)

            logger.info(f"Created script: {script_path}")

            # Make executable if bash script
            if language == "bash":
                os.chmod(script_path, 0o755)
                cmd = ["/bin/bash", str(script_path)]
            else:
                # For Python scripts, use the virtual environment's python if available
                python_path = str(self.project_root / "mcp-env" / "bin" / "python3")
                if os.path.exists(python_path):
                    cmd = [python_path, str(script_path)]
                else:
                    cmd = ["/usr/bin/env", "python3", str(script_path)]

            # Execute with timeout from the project root directory
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_root),  # Run from project root for proper imports
            )

            # Don't clean up - keep the script for future reference
            logger.info(f"Script executed with return code: {result.returncode}")

            return result.returncode == 0, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            logger.warning(f"Script execution timed out: {filename}")
            return False, "", f"Script execution timed out after {timeout} seconds"
        except Exception as e:
            logger.error(f"Execution error for {filename}: {str(e)}")
            return False, "", f"Execution error: {str(e)}"

    def create_and_execute_tool(
        self,
        user_request: str,
        preferred_language: str = "auto",
        send_to_telegram: bool = True,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main function to create and execute a dynamic tool.
        """
        try:
            logger.info(f"Creating dynamic tool for request: {user_request}")

            # Generate code
            code, language, filename = self.generate_code_from_request(
                user_request, preferred_language
            )

            # Execute the script
            success, stdout, stderr = self.execute_script(code, language, filename)

            # Prepare response
            response = {
                "success": success,
                "request": user_request,
                "language": language,
                "filename": filename,
                "code": code,
                "stdout": stdout,
                "stderr": stderr,
                "timestamp": datetime.now().isoformat(),
            }

            # Format message for Telegram
            if send_to_telegram:
                if success:
                    message = f"✅ **Dynamic Tool Executed Successfully**\n\n"
                    message += f"**Request:** {user_request}\n"
                    message += f"**Language:** {language}\n"
                    message += f"**File:** `dynamic_commands/{filename}`\n\n"
                    message += f"**Output:**\n```\n{stdout[:1500]}{'...' if len(stdout) > 1500 else ''}\n```"

                    if stderr and stderr.strip():
                        message += f"\n\n**Warnings:**\n```\n{stderr[:500]}\n```"
                else:
                    message = f"❌ **Dynamic Tool Execution Failed**\n\n"
                    message += f"**Request:** {user_request}\n"
                    message += f"**Language:** {language}\n"
                    message += f"**File:** `dynamic_commands/{filename}`\n\n"

                    # Show both stdout and stderr for failed executions
                    if stdout and stdout.strip():
                        message += (
                            f"**Output before error:**\n```\n{stdout[:800]}\n```\n\n"
                        )

                    if stderr and stderr.strip():
                        message += f"**Error Details:**\n```\n{stderr[:800]}\n```"
                    else:
                        message += f"**Error:** No specific error details available"

                # Send to Telegram
                self.send_telegram_message(message, chat_id)

            return response

        except Exception as e:
            logger.error(f"Error in create_and_execute_tool: {str(e)}")
            error_response = {
                "success": False,
                "error": str(e),
                "request": user_request,
                "timestamp": datetime.now().isoformat(),
            }

            if send_to_telegram:
                error_message = f"❌ **Dynamic Tool Creation Failed**\n\n"
                error_message += f"**Request:** {user_request}\n"
                error_message += f"**Error:** {str(e)}"
                self.send_telegram_message(error_message, chat_id)

            return error_response


# Global instance
dynamic_tool_creator = DynamicToolCreator()


def create_dynamic_tool(
    user_request: str,
    preferred_language: str = "auto",
    send_to_telegram: bool = True,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Public function to create and execute dynamic tools.

    Args:
        user_request: The user's request describing what they want the tool to do
        preferred_language: "auto", "bash", or "python"
        send_to_telegram: Whether to send results to Telegram
        chat_id: Telegram chat ID (uses admin_id if not provided)

    Returns:
        Dictionary with execution results
    """
    return dynamic_tool_creator.create_and_execute_tool(
        user_request, preferred_language, send_to_telegram, chat_id
    )
