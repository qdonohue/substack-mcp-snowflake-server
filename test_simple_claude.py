#!/usr/bin/env python3
import subprocess
import os

# Test with a very simple prompt
test_prompt = """Say hello.

===FINAL_ANSWER===
Hello!
===END_ANSWER==="""

print("Testing if claude command works at all...")

# First, let's just try to run claude with a simple echo test
result = subprocess.run(
    ["which", "claude"],
    capture_output=True,
    text=True,
)
print(f"Claude location: {result.stdout.strip()}")

# Try the simplest possible claude command
result = subprocess.run(
    ["claude", "--help"],
    capture_output=True,
    text=True,
)
print(f"\nClaude help return code: {result.returncode}")
if result.returncode != 0:
    print(f"Error: {result.stderr}")

# Now try with actual prompt but with explicit env
env = os.environ.copy()
result = subprocess.run(
    ["claude", "-p", "Say hello"],
    capture_output=True,
    text=True,
    env=env,
    cwd="/tmp"  # Use a simple directory
)
print(f"\nSimple prompt return code: {result.returncode}")
print(f"Stdout: {result.stdout[:200]}...")  # First 200 chars
if result.stderr:
    print(f"Stderr: {result.stderr[:200]}...")