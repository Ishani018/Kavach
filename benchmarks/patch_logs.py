import os
import json
from pathlib import Path

def patch_log_file(filepath: Path):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        modified = False
        if "messages" in data and isinstance(data["messages"], list):
            for msg in data["messages"]:
                if isinstance(msg, dict) and msg.get("role") == "tool":
                    content = msg.get("content")
                    if isinstance(content, str):
                        # Convert string to list of content blocks
                        msg["content"] = [{"type": "text", "content": content}]
                        modified = True
                        
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            print(f"Patched: {filepath}")
    except Exception as e:
        print(f"Error patching {filepath}: {e}")

def main():
    logs_dir = Path("benchmarks/results_v2/agentdojo_gemma_laptop/logs")
    if not logs_dir.exists():
        print(f"Logs directory {logs_dir} does not exist.")
        return
        
    print(f"Scanning for JSON log files in {logs_dir}...")
    count = 0
    for root, _, files in os.walk(logs_dir):
        for file in files:
            if file.endswith(".json"):
                patch_log_file(Path(root) / file)
                count += 1
                
    print(f"Finished. Scanned {count} files.")

if __name__ == "__main__":
    main()
