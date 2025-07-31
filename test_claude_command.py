#!/usr/bin/env python3
import subprocess

# Test the claude command with marker-based output
test_prompt = """Please tell me what 2+2 equals.

When you have your final answer, output it between these markers:
===FINAL_ANSWER===
[your answer here]
===END_ANSWER==="""

print("Testing claude command with marker-based output...")
result = subprocess.run(
    [
        "claude",
        "-p",
        test_prompt,
    ],
    capture_output=True,
    text=True,
)

print(f"Return code: {result.returncode}")
print(f"Stdout:\n{result.stdout}")
print(f"Stderr: {result.stderr}")

if result.returncode == 0:
    # Extract content between markers
    output = result.stdout
    start_marker = "===FINAL_ANSWER==="
    end_marker = "===END_ANSWER==="
    
    start_idx = output.find(start_marker)
    end_idx = output.find(end_marker)
    
    if start_idx != -1 and end_idx != -1:
        # Extract the content between markers
        start_idx += len(start_marker)
        final_answer = output[start_idx:end_idx].strip()
        print(f"\nExtracted answer: {final_answer}")
    else:
        print("\nMarkers not found in output")