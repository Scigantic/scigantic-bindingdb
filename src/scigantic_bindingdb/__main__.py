"""Enables `python -m scigantic_bindingdb`, same commands as the `scigantic-bindingdb` console script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
