"""
run_tests.py - Runs every self-test of the shared engine.

    python run_tests.py

Both apps use the same engine (the pattern_core folder), so passing these
tests covers the calculations of the desktop app, the web app and the backtest.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, HERE)

import test_backtest  # noqa: E402
import test_confirm  # noqa: E402
import test_indicators  # noqa: E402
import test_patterns  # noqa: E402
import test_policy  # noqa: E402
import test_statistics  # noqa: E402

if __name__ == "__main__":
    results = []
    for name, mod in (("Indicators", test_indicators), ("Patterns", test_patterns), ("Backtest rules", test_backtest),
                      ("Textbook checks", test_confirm),
                      ("Statistics", test_statistics), ("Trading policies", test_policy)):
        print(f"\n===== {name} =====")
        results.append(mod.run())
    print("\nALL TESTS PASSED" if all(results) else "\nSOME TESTS FAILED")
    sys.exit(0 if all(results) else 1)
