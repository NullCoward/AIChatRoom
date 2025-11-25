# Test suite for AI Chat Room
#
# Run all tests: python tests/run_all_tests.py
# Run specific suite: python tests/run_all_tests.py --suite models
# Run with pytest: python -m pytest tests/ -v
#
# Test suites:
#   - test_models.py - Data models (AIAgent, ChatMessage, SelfConcept, etc.)
#   - test_database_service.py - SQLite persistence layer
#   - test_hud_service.py - Context window building and response parsing
#   - test_openai_service.py - OpenAI API integration (mocked)
#   - test_toon_service.py - TOON serialization format
#   - test_config_prompts.py - Configuration and prompts
