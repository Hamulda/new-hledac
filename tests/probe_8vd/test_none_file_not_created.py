"""Test that None file is not created."""
import pathlib
import os
import sys

# Use absolute path
_test_dir = pathlib.Path(__file__).parent
Universal_dir = _test_dir.parent.parent.parent  # tests/probe_8vd -> tests -> hledac -> universal
os.chdir(Universal_dir)

assert not pathlib.Path("None").exists(), \
    "Soubor 'None' nesmí existovat — oprav guard v EXPORT fázi"
