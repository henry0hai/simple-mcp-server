import os
import subprocess
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
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

        # Create script registry file for reuse tracking
        self.registry_file = self.commands_dir / "script_registry.json"
        if not self.registry_file.exists():
            with open(self.registry_file, "w") as f:
                json.dump({}, f, indent=2)

    def _normalize_request(self, request: str) -> str:
        """Normalize user request for comparison purposes"""
        # Convert to lowercase and remove extra spaces
        normalized = " ".join(request.lower().strip().split())

        # Define common variations that should be treated as the same
        variations = {
            "computer name": [
                "computer name",
                "hostname",
                "server name",
                "machine name",
                "host name",
            ],
            "current time": [
                "current time",
                "server time",
                "current date time",
                "date time",
                "time",
            ],
            "ip address": [
                "ip address",
                "current ip",
                "server ip",
                "network ip",
                "my ip",
            ],
            "disk space": [
                "disk space",
                "available space",
                "disk usage",
                "storage space",
            ],
            "memory usage": ["memory usage", "ram usage", "memory", "ram"],
            "system info": ["system info", "system information", "server info"],
            "uptime": ["uptime", "system uptime", "server uptime"],
        }

        # Replace variations with canonical form
        for canonical, variants in variations.items():
            for variant in variants:
                if variant in normalized:
                    normalized = normalized.replace(variant, canonical)

        return normalized

    def _get_request_hash(self, request: str, language: str) -> str:
        """Generate a hash for the normalized request and language"""
        normalized_request = self._normalize_request(request)
        combined = f"{normalized_request}:{language}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _load_script_registry(self) -> Dict:
        """Load the script registry from file"""
        try:
            with open(self.registry_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_script_registry(self, registry: Dict):
        """Save the script registry to file"""
        try:
            with open(self.registry_file, "w") as f:
                json.dump(registry, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save script registry: {str(e)}")

    def _find_existing_script(
        self, request: str, language: str
    ) -> Optional[Tuple[str, str]]:
        """Find an existing script that matches the request"""
        registry = self._load_script_registry()
        request_hash = self._get_request_hash(request, language)

        # Direct hash match
        if request_hash in registry:
            script_info = registry[request_hash]
            script_path = self.commands_dir / script_info["filename"]
            if script_path.exists():
                logger.info(f"Found exact match for request: {script_info['filename']}")
                return script_info["filename"], script_info["original_request"]

        # Fuzzy matching for similar requests
        normalized_request = self._normalize_request(request)
        for stored_hash, script_info in registry.items():
            stored_normalized = self._normalize_request(script_info["original_request"])

            # Check for high similarity (simple word matching for now)
            if (
                language == script_info["language"]
                and self._calculate_similarity(normalized_request, stored_normalized)
                > 0.8
            ):
                script_path = self.commands_dir / script_info["filename"]
                if script_path.exists():
                    logger.info(
                        f"Found similar script for request: {script_info['filename']}"
                    )
                    return script_info["filename"], script_info["original_request"]

        return None

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings (simple implementation)"""
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def _register_script(self, request: str, language: str, filename: str):
        """Register a new script in the registry"""
        registry = self._load_script_registry()
        request_hash = self._get_request_hash(request, language)

        registry[request_hash] = {
            "filename": filename,
            "original_request": request,
            "language": language,
            "created_at": datetime.now().isoformat(),
            "usage_count": 1,
        }

        self._save_script_registry(registry)

    def _update_script_usage(self, filename: str):
        """Update usage count for an existing script"""
        registry = self._load_script_registry()

        for script_info in registry.values():
            if script_info["filename"] == filename:
                script_info["usage_count"] = script_info.get("usage_count", 0) + 1
                script_info["last_used"] = datetime.now().isoformat()
                break

        self._save_script_registry(registry)

    def cleanup_old_scripts(self, max_unused_days: int = 30):
        """Clean up old unused scripts to keep directory manageable"""
        registry = self._load_script_registry()
        current_time = datetime.now()
        scripts_to_remove = []

        for script_hash, script_info in registry.items():
            # Check if script file still exists
            script_path = self.commands_dir / script_info["filename"]
            if not script_path.exists():
                scripts_to_remove.append(script_hash)
                continue

            # Check if script hasn't been used recently
            last_used = script_info.get("last_used", script_info.get("created_at"))
            if last_used:
                last_used_date = datetime.fromisoformat(
                    last_used.replace("Z", "+00:00").replace("+00:00", "")
                )
                days_unused = (current_time - last_used_date).days

                # Remove scripts that haven't been used in a while and have low usage count
                usage_count = script_info.get("usage_count", 1)
                if days_unused > max_unused_days and usage_count <= 2:
                    try:
                        script_path.unlink()  # Delete the file
                        scripts_to_remove.append(script_hash)
                        logger.info(f"Removed unused script: {script_info['filename']}")
                    except Exception as e:
                        logger.error(
                            f"Failed to remove script {script_info['filename']}: {str(e)}"
                        )

        # Update registry
        for script_hash in scripts_to_remove:
            registry.pop(script_hash, None)

        if scripts_to_remove:
            self._save_script_registry(registry)
            logger.info(f"Cleaned up {len(scripts_to_remove)} old scripts")

    def get_script_stats(self) -> Dict:
        """Get statistics about script usage and reuse"""
        registry = self._load_script_registry()

        total_scripts = len(registry)
        total_usage = sum(
            script_info.get("usage_count", 1) for script_info in registry.values()
        )
        reused_scripts = sum(
            1
            for script_info in registry.values()
            if script_info.get("usage_count", 1) > 1
        )

        return {
            "total_scripts": total_scripts,
            "total_usage": total_usage,
            "reused_scripts": reused_scripts,
            "reuse_rate": (
                (reused_scripts / total_scripts * 100) if total_scripts > 0 else 0
            ),
            "average_usage": (total_usage / total_scripts) if total_scripts > 0 else 0,
        }

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
    ) -> Tuple[str, str, str, bool]:
        """
        Generate intelligent code based on user request using AI.
        Returns: (code, language, filename, is_reused)
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

        # Check for existing script first
        existing_script = self._find_existing_script(user_request, language)
        if existing_script:
            filename, original_request = existing_script
            script_path = self.commands_dir / filename

            # Read the existing code
            with open(script_path, "r") as f:
                code = f.read()

            logger.info(
                f"Reusing existing script: {filename} (originally for: '{original_request}')"
            )
            self._update_script_usage(filename)
            return code, language, filename, True

        # Generate new code using AI if no existing script found
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

        # Register the new script
        self._register_script(user_request, language, filename)

        return code, language, filename, False

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
   - For computer name: `scutil --get ComputerName` or `scutil --get LocalHostName`
   - For user name: `whoami` or `id -un`
   - For IP display: `ifconfig | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{{print $2}}'`
   - For memory display: `vm_stat | head -n 10`
   - For password generation: `openssl rand -base64 12`
   - For uptime display: `uptime`
   - For disk display: `df -h`
   - For date/time: `date`
   - For processes: `ps aux | head -10`
   - For system info: `uname -a` or `system_profiler SPSoftwareDataType`
   
3. NEVER use Linux-specific commands that don't exist on macOS:
   - DON'T use: `getent`, `free`, `hostname -I`, `lscpu`, `lsblk`
   - DON'T use: `/proc/` filesystem (doesn't exist on macOS)
   - DON'T use: `systemctl`, `service`, `apt`, `yum`, `rpm`

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

    async def execute_script(
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

            # Execute with timeout from the project root directory using async subprocess
            import asyncio

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_root),  # Run from project root for proper imports
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                stdout = stdout_data.decode("utf-8") if stdout_data else ""
                stderr = stderr_data.decode("utf-8") if stderr_data else ""
                returncode = process.returncode

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.warning(f"Script execution timed out: {filename}")
                return False, "", f"Script execution timed out after {timeout} seconds"

            # Don't clean up - keep the script for future reference
            logger.info(f"Script executed with return code: {returncode}")

            return returncode == 0, stdout, stderr

        except Exception as e:
            logger.error(f"Execution error for {filename}: {str(e)}")
            return False, "", f"Execution error: {str(e)}"

    async def create_and_execute_tool(
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
            code, language, filename, is_reused = self.generate_code_from_request(
                user_request, preferred_language
            )

            # Execute the script (now async)
            success, stdout, stderr = await self.execute_script(
                code, language, filename
            )

            # Prepare response
            response = {
                "success": success,
                "request": user_request,
                "language": language,
                "filename": filename,
                "code": code,
                "stdout": stdout,
                "stderr": stderr,
                "is_reused": is_reused,
                "timestamp": datetime.now().isoformat(),
            }

            # Format message for Telegram
            if send_to_telegram:
                if success:
                    if is_reused:
                        message = f"♻️ **Dynamic Tool Reused Successfully**\n\n"
                    else:
                        message = f"✅ **Dynamic Tool Executed Successfully**\n\n"
                    message += f"**Request:** {user_request}\n"
                    message += f"**Language:** {language}\n"
                    message += f"**File:** `dynamic_commands/{filename}`\n"
                    if is_reused:
                        message += f"**Status:** Reused existing script\n"
                    message += f"\n**Output:**\n```\n{stdout[:1500]}{'...' if len(stdout) > 1500 else ''}\n```"

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


async def create_dynamic_tool(
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
    return await dynamic_tool_creator.create_and_execute_tool(
        user_request, preferred_language, send_to_telegram, chat_id
    )
