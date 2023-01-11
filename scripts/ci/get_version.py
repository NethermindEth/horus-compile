#!/usr/bin/env python3

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
from horus import __version__


def main():
    print(f"horus-compile {__version__}")


if __name__ == "__main__":
    sys.exit(main())
