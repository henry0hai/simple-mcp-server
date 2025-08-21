import os
import subprocess
import hashlib
import json
import re
import asyncio
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

        # Enhanced fuzzy matching for similar requests
        normalized_request = self._normalize_request(request)
        best_match = None
        best_similarity = 0.0

        for stored_hash, script_info in registry.items():
            if language != script_info["language"]:
                continue

            script_path = self.commands_dir / script_info["filename"]
            if not script_path.exists():
                continue

            # Calculate request similarity
            stored_normalized = self._normalize_request(script_info["original_request"])
            request_similarity = self._calculate_similarity(
                normalized_request, stored_normalized
            )

            # Also check filename similarity (semantic matching)
            filename_similarity = self._calculate_filename_similarity(
                request, script_info["filename"]
            )

            # Combine both similarities (weighted: 70% request, 30% filename)
            combined_similarity = (request_similarity * 0.7) + (
                filename_similarity * 0.3
            )

            if combined_similarity > best_similarity and combined_similarity > 0.75:
                best_similarity = combined_similarity
                best_match = (script_info["filename"], script_info["original_request"])

        if best_match:
            logger.info(
                f"Found similar script for request (similarity: {best_similarity:.2f}): {best_match[0]}"
            )
            return best_match

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

    def _calculate_filename_similarity(self, request: str, filename: str) -> float:
        """Calculate similarity between a request and a filename (semantic matching)"""
        # Extract the task name from filename (remove timestamp and extension)
        filename_without_ext = filename.split(".")[0]  # Remove extension
        # Remove timestamp pattern (MMDD_HHMM)
        import re

        task_name = re.sub(r"_\d{4}_\d{4}$", "", filename_without_ext)

        # Convert underscores to spaces for comparison
        task_words = set(task_name.replace("_", " ").lower().split())
        request_words = set(request.lower().split())

        # Remove common stop words for better matching
        stop_words = {
            "get",
            "show",
            "display",
            "fetch",
            "find",
            "current",
            "system",
            "info",
            "information",
            "script",
            "python",
            "bash",
        }
        task_words = task_words - stop_words
        request_words = request_words - stop_words

        if not task_words and not request_words:
            return 1.0
        if not task_words or not request_words:
            return 0.0

        intersection = task_words.intersection(request_words)
        union = task_words.union(request_words)

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

    def _generate_semantic_filename(self, user_request: str, language: str) -> str:
        """Generate meaningful, semantic filename based on the task type and request"""
        request_lower = user_request.lower().strip()

        # Define concise semantic patterns for different types of tasks
        task_patterns = {
            # System Information (shortened names)
            "sys_info": [
                "system info",
                "system information",
                "hardware info",
                "machine info",
            ],
            "hostname": [
                "computer name",
                "hostname",
                "server name",
                "machine name",
                "host name",
            ],
            "current_time": [
                "current time",
                "date time",
                "time now",
                "server time",
                "current date",
            ],
            "uptime": ["uptime", "system uptime", "server uptime", "how long running"],
            "memory": ["memory usage", "ram usage", "memory info", "ram info"],
            "disk_space": [
                "disk space",
                "disk usage",
                "storage space",
                "available space",
            ],
            "ip_addr": ["ip address", "current ip", "network ip", "my ip", "server ip"],
            "user_info": ["current user", "username", "user info", "whoami"],
            "processes": ["running processes", "process list", "active processes"],
            # Weather and API
            "weather": [
                "weather",
                "temperature",
                "forecast",
                "weather info",
                "climate",
            ],
            "api_call": ["api call", "fetch data", "api request", "http request"],
            # Calculations and Data Processing
            "calc": ["calculate", "computation", "math", "arithmetic", "formula"],
            "passwd": [
                "password",
                "random password",
                "secure password",
                "generate password",
            ],
            "data_proc": [
                "process data",
                "analyze data",
                "data analysis",
                "parse data",
            ],
            "convert": ["convert", "conversion", "unit conversion"],
            # File Operations (safe ones only)
            "list_files": ["list files", "show files", "directory contents"],
            "read_file": ["read file", "display file", "show file content"],
            # Network and Connectivity
            "ping": ["ping", "network test", "connectivity check", "internet test"],
            "net_info": ["network info", "network status", "interface info"],
            # Random Data Generation
            "random": ["random", "generate random", "random data", "random number"],
        }

        # Find the best matching task pattern
        matched_task = None
        for task_name, patterns in task_patterns.items():
            for pattern in patterns:
                if pattern in request_lower:
                    matched_task = task_name
                    break
            if matched_task:
                break

        # If no pattern matched, create a short descriptive name from key words
        if not matched_task:
            # Extract meaningful words (filter out common words)
            stop_words = {
                "the",
                "a",
                "an",
                "and",
                "or",
                "but",
                "in",
                "on",
                "at",
                "to",
                "for",
                "of",
                "with",
                "by",
                "from",
                "up",
                "about",
                "into",
                "through",
                "during",
                "before",
                "after",
                "above",
                "below",
                "can",
                "could",
                "should",
                "would",
                "will",
                "shall",
                "may",
                "might",
                "must",
                "please",
                "create",
                "make",
                "generate",
                "show",
                "display",
                "get",
                "fetch",
                "find",
                "script",
                "python",
                "bash",
                "program",
                "application",
                "tool",
                "function",
                "code",
                "me",
                "my",
                "i",
                "you",
                "we",
                "they",
                "it",
                "that",
                "this",
                "what",
                "how",
                "when",
                "where",
                "why",
                "which",
                "who",
            }

            words = []
            for word in request_lower.split():
                clean_word = "".join(c for c in word if c.isalnum())
                if clean_word and clean_word not in stop_words and len(clean_word) > 2:
                    words.append(clean_word[:8])  # Limit word length to 8 chars

            if words:
                # Take up to 2 most meaningful words and limit total length
                matched_task = "_".join(words[:2])
            else:
                matched_task = "custom"

        # Ensure task name is not too long (max 20 characters)
        if len(matched_task) > 20:
            matched_task = matched_task[:20]

        # Add short timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%m%d_%H%M")

        # Add language extension
        extension = "sh" if language == "bash" else "py"

        # Generate final filename (should be under 35 characters total)
        filename = f"{matched_task}_{timestamp}.{extension}"

        return filename

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

        # Generate meaningful semantic filename
        filename = self._generate_semantic_filename(user_request, language)

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
                # Build the system prompt without f-string to avoid curly brace conflicts
                system_prompt = "You are an expert Python developer. Generate a complete, executable Python script based on the user's request.\n\n"
                system_prompt += "CRITICAL SECURITY RESTRICTIONS:\n"
                system_prompt += "- NEVER generate scripts that modify, delete, create, or write files outside of $HOME/Downloads/\n"
                system_prompt += "- NEVER access sensitive directories: .ssh, .env, /etc, /var, /usr, /root, ~/.config, ~/.cache, etc.\n"
                system_prompt += "- NEVER generate scripts that install packages, modify system settings, or change permissions\n"
                system_prompt += "- NEVER access environment variables containing passwords, tokens, or credentials\n"
                system_prompt += "- ONLY READ-ONLY operations are allowed for system information (CPU, memory, disk usage, etc.)\n"
                system_prompt += (
                    "- File operations are ONLY allowed in $HOME/Downloads/ directory\n"
                )
                system_prompt += (
                    "- NEVER use sudo, chmod, chown, or system modification commands\n"
                )
                system_prompt += "- NEVER access network interfaces configuration or system network settings\n\n"
                system_prompt += "ALLOWED OPERATIONS:\n"
                system_prompt += "- Read system information (CPU, memory, disk usage, processes) - READ ONLY\n"
                system_prompt += "- Make HTTP API requests to external services\n"
                system_prompt += "- Read files from $HOME/Downloads/ directory ONLY\n"
                system_prompt += "- Perform calculations and data processing\n"
                system_prompt += "- Generate reports and display information\n"
                system_prompt += "- Access project config for API keys (weather, telegram) for external requests\n\n"
                system_prompt += f"IMPORTANT: The script will execute from: {self.project_root}/dynamic_commands/\n"
                system_prompt += f"The project config is located at: {self.project_root}/src/config/config.py\n\n"
                system_prompt += "Requirements:\n"
                system_prompt += "1. Follow the structure and patterns from this template (pay attention to import paths):\n"
                system_prompt += "```python\n" + template_content + "\n```\n\n"
                system_prompt += (
                    "2. Use the EXACT same import structure as the template\n"
                )
                system_prompt += "3. Access config variables using these exact attribute names (ONLY for external API requests)\n"
                system_prompt += "4. Include proper error handling and logging\n"
                system_prompt += "5-24. [All other requirements as before]\n\n"
                system_prompt += "MANDATORY RETURN VALUE STRUCTURE:\n"
                system_prompt += "Every script MUST follow this exact pattern:\n"
                system_prompt += "```python\n"
                system_prompt += "def main():\n"
                system_prompt += "    result = {\n"
                system_prompt += '        "success": False,\n'
                system_prompt += '        "data": None,\n'
                system_prompt += '        "error": None,\n'
                system_prompt += (
                    '        "timestamp": datetime.datetime.now().isoformat()\n'
                )
                system_prompt += "    }\n"
                system_prompt += "    try:\n"
                system_prompt += "        # Your main logic here\n"
                system_prompt += '        result["success"] = True\n'
                system_prompt += '        result["data"] = "your_actual_results_here"\n'
                system_prompt += "    except Exception as e:\n"
                system_prompt += '        result["error"] = str(e)\n'
                system_prompt += '        print(f"❌ Error: {str(e)}")\n'
                system_prompt += "    finally:\n"
                system_prompt += "        import json\n"
                system_prompt += (
                    r'        print("\n=== FINAL RESULT (JSON) ===")' + "\n"
                )
                system_prompt += "        print(json.dumps(result, indent=2))\n"
                system_prompt += r'        print("===========================")' + "\n"
                system_prompt += '        if not result["success"]:\n'
                system_prompt += "            sys.exit(1)\n"
                system_prompt += "    return result\n"
                system_prompt += "```\n\n"
                system_prompt += "Generate only the Python code, no explanations or markdown formatting."

            else:  # bash
                # Build the bash system prompt without f-string to avoid curly brace conflicts
                system_prompt = "You are an expert Bash script developer. Generate a complete, executable Bash script based on the user's request.\n\n"
                system_prompt += "CRITICAL SECURITY RESTRICTIONS:\n"
                system_prompt += "- NEVER generate scripts that modify, delete, create, or write files\n"
                system_prompt += "- NEVER access sensitive directories: ~/.ssh, /etc, /var, /usr, /root, ~/.config, ~/.cache, etc.\n"
                system_prompt += "- NEVER use commands: rm, mv, cp, touch, mkdir, chmod, chown, sudo, su, etc.\n"
                system_prompt += (
                    "- ONLY READ-ONLY operations for system information are allowed\n\n"
                )
                system_prompt += "ALLOWED OPERATIONS:\n"
                system_prompt += "- Display system information (READ-ONLY): date, uptime, whoami, hostname\n"
                system_prompt += (
                    "- Check system resources (READ-ONLY): vm_stat, df -h, ps aux\n"
                )
                system_prompt += "- Generate random data: openssl rand\n"
                system_prompt += (
                    "- Network information (READ-ONLY): ifconfig (display only)\n\n"
                )
                system_prompt += "CRITICAL: This script MUST run on macOS! Use only macOS-compatible commands and syntax.\n\n"
                system_prompt += "Requirements:\n"
                system_prompt += "1. Follow this template structure:\n"
                system_prompt += "```bash\n" + template_content + "\n```\n\n"
                system_prompt += "2. Use ONLY macOS-compatible READ-ONLY commands\n"
                system_prompt += "3. Include proper error handling (set -e, set -u)\n"
                system_prompt += (
                    "4. ALWAYS output final results in JSON format for easy parsing\n"
                )
                system_prompt += "5. ALWAYS use trap commands to ensure results are output even on failure\n\n"
                system_prompt += "MANDATORY RETURN VALUE STRUCTURE:\n"
                system_prompt += "Every Bash script MUST follow this exact pattern from the template:\n"
                system_prompt += "```bash\n"
                system_prompt += "SUCCESS=true\n"
                system_prompt += 'ERROR_MSG=""\n'
                system_prompt += 'OUTPUT_DATA=""\n'
                system_prompt += "trap 'output_result' EXIT\n"
                system_prompt += "output_result() {\n"
                system_prompt += '    echo "{\\"success\\": $SUCCESS, \\"data\\": \\"$OUTPUT_DATA\\", \\"error\\": \\"$ERROR_MSG\\"}"\n'
                system_prompt += "}\n"
                system_prompt += "```\n\n"
                system_prompt += "Generate only the Bash script code, no explanations or markdown formatting."

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
