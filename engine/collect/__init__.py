"""Collectors. Each one catches its own errors, logs through Http/RunLog, and returns
plain Python structures with `not_found` where data is missing. Internal series are
lists of (aware datetime, value) tuples; output.py decides what gets serialized."""
