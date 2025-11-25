#!/usr/bin/env python3
"""Main test runner for AI Chatroom application.

Run all tests: python tests/run_all_tests.py
Run with verbose: python tests/run_all_tests.py -v
Run specific suite: python tests/run_all_tests.py --suite models
"""

import sys
import os
import unittest
import argparse
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Import all test modules
from tests import test_models
from tests import test_database_service
from tests import test_hud_service
from tests import test_openai_service
from tests import test_toon_service
from tests import test_config_prompts
from tests import test_api


# Test suite registry
TEST_SUITES = {
    'models': test_models,
    'database': test_database_service,
    'hud': test_hud_service,
    'openai': test_openai_service,
    'toon': test_toon_service,
    'config': test_config_prompts,
    'api': test_api,
}


def get_all_test_cases():
    """Get all test case classes from all modules."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Models
    suite.addTests(loader.loadTestsFromModule(test_models))

    # Database service
    suite.addTests(loader.loadTestsFromModule(test_database_service))

    # HUD service
    suite.addTests(loader.loadTestsFromModule(test_hud_service))

    # OpenAI service
    suite.addTests(loader.loadTestsFromModule(test_openai_service))

    # TOON service
    suite.addTests(loader.loadTestsFromModule(test_toon_service))

    # Config & Prompts
    suite.addTests(loader.loadTestsFromModule(test_config_prompts))

    # API tests
    suite.addTests(loader.loadTestsFromModule(test_api))

    return suite


def run_suite(suite_name, verbosity=2):
    """Run a specific test suite."""
    if suite_name not in TEST_SUITES:
        print(f"Unknown suite: {suite_name}")
        print(f"Available suites: {', '.join(TEST_SUITES.keys())}")
        return False

    module = TEST_SUITES[suite_name]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(module)

    print(f"\n{'=' * 70}")
    print(f"Running {suite_name.upper()} tests")
    print(f"{'=' * 70}\n")

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_all_tests(verbosity=2):
    """Run all test suites."""
    suite = get_all_test_cases()

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    return result


def print_summary(result, elapsed_time):
    """Print test summary."""
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    passed = total - failures - errors - skipped

    print(f"\nTotal tests: {total}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failures}")
    print(f"  Errors:  {errors}")
    print(f"  Skipped: {skipped}")
    print(f"\nTime elapsed: {elapsed_time:.2f} seconds")

    if result.wasSuccessful():
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED!")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("SOME TESTS FAILED")
        print("=" * 70)

        if result.failures:
            print("\nFailed tests:")
            for test, _ in result.failures:
                print(f"  - {test}")

        if result.errors:
            print("\nTests with errors:")
            for test, _ in result.errors:
                print(f"  - {test}")


def main():
    parser = argparse.ArgumentParser(description="Run AI Chatroom tests")
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Quiet output (only show failures)'
    )
    parser.add_argument(
        '--suite',
        choices=list(TEST_SUITES.keys()),
        help='Run specific test suite'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available test suites'
    )

    args = parser.parse_args()

    if args.list:
        print("Available test suites:")
        for name, module in TEST_SUITES.items():
            doc = module.__doc__ or "No description"
            print(f"  {name}: {doc.split(chr(10))[0]}")
        return 0

    verbosity = 1
    if args.verbose:
        verbosity = 2
    if args.quiet:
        verbosity = 0

    print("=" * 70)
    print("AI CHATROOM TEST SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    start_time = time.time()

    if args.suite:
        success = run_suite(args.suite, verbosity)
        elapsed = time.time() - start_time
        print(f"\nTime elapsed: {elapsed:.2f} seconds")
        return 0 if success else 1
    else:
        result = run_all_tests(verbosity)
        elapsed = time.time() - start_time
        print_summary(result, elapsed)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
