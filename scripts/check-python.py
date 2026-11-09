"""Parse tracked Python without bytecode writes or source mutation."""
import ast
from pathlib import Path
import subprocess

for name in subprocess.check_output(["git", "ls-files", "-z", "*.py"]).decode().split("\0"):
    if name:
        ast.parse(Path(name).read_bytes(), filename=name)
print("All tracked Python parsed successfully")
