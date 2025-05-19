import sys
import os

age = int(os.getenv("AGE", "unknown"))

if len(sys.argv) > 1:
    name = sys.argv[1]
    print(f"Hello, {name}! You are {age} years old.")
else:
    print(f"Hello, World! You are {age} years old.")
