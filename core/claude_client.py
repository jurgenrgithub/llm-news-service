"""Claude CLI wrapper for LLM calls"""

import json
import os
import subprocess
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ClaudeResponse:
    """Response from Claude CLI call"""
    output: str
    exit_code: int
    is_error: bool = False
    error_message: Optional[str] = None


class ClaudeClient:
    """Client for Claude CLI calls using subscription."""

    def __init__(
        self,
        cli_path: str = "/bin/claude",
        model: str = "claude-opus-4-5-20251101",
        timeout: int = 300,
        max_turns: int = 1,
    ):
        self.cli_path = cli_path
        self.model = model
        self.timeout = timeout
        self.max_turns = max_turns

    def query(self, prompt: str) -> ClaudeResponse:
        """
        Execute a one-shot prompt via Claude CLI.

        Args:
            prompt: The prompt to send

        Returns:
            ClaudeResponse with output and metadata
        """
        env = dict(os.environ, PYTHONIOENCODING="utf-8")

        cmd = [
            self.cli_path,
            "-p",  # Print mode (non-interactive)
            "--model", self.model,
            "--max-turns", str(self.max_turns),
            "--output-format", "text",
        ]

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            is_error = result.returncode != 0

            return ClaudeResponse(
                output=result.stdout.strip(),
                exit_code=result.returncode,
                is_error=is_error,
                error_message=result.stderr if is_error else None,
            )

        except subprocess.TimeoutExpired:
            return ClaudeResponse(
                output="",
                exit_code=-1,
                is_error=True,
                error_message=f"Timeout after {self.timeout}s",
            )
        except FileNotFoundError:
            return ClaudeResponse(
                output="",
                exit_code=-1,
                is_error=True,
                error_message=f"Claude CLI not found: {self.cli_path}",
            )
        except Exception as e:
            return ClaudeResponse(
                output="",
                exit_code=-1,
                is_error=True,
                error_message=str(e),
            )

    def query_json(self, prompt: str) -> dict:
        """
        Execute prompt and parse JSON from response.

        Args:
            prompt: The prompt (should request JSON output)

        Returns:
            Parsed JSON dict, or error dict
        """
        response = self.query(prompt)

        if response.is_error:
            return {"error": response.error_message}

        # Try to extract JSON from response
        output = response.output

        # Handle markdown code blocks
        if "```json" in output:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", output)
            if match:
                output = match.group(1)
        elif "```" in output:
            match = re.search(r"```\s*([\s\S]*?)\s*```", output)
            if match:
                output = match.group(1)

        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse error: {e}", "raw": response.output}
