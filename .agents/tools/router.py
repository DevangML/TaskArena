#!/usr/bin/env python3
import sys
from pathlib import Path
from util import enqueue

def main():
    repo = str(Path(".").resolve())
    if sys.stdin.isatty():
        prompt = input("Task prompt: ").strip()
        enqueue(prompt, repo)
    else:
        for line in sys.stdin:
            line=line.strip()
            if line: enqueue(line, repo)

if __name__ == "__main__":
    main()
