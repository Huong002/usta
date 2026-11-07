import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SOURCE_DIR))

from usta.main import main

if __name__ == "__main__":
    main()
