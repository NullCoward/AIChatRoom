#!/usr/bin/env python3
"""Test suite for DatabaseService - SQLite persistence layer.

Run with: python -m pytest tests/test_database_service.py -v
Or standalone: python tests/test_database_service.py
"""

import sys
import os
import tempfile
import unittest
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database_service import DatabaseService
from models import AIAgent, ChatMessage, ChatRoom, RoomMembership


class TestDatabaseServiceSetup(unittest.TestCase):
    """Tests for database initialization and setup."""

    def setUp(self):
        """Create a temporary database for each test."""
        import shutil
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")

    def tearDown(self):
        """Clean up temporary files (ignore Windows file locking errors)."""
        import shutil
        import gc
        gc.collect()  # Help release SQLite connections
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_database_file(self):
        """Test that database file is created."""
        db = DatabaseService(self.db_path)
        self.assertTrue(os.path.exists(self.db_path))

    def test_creates_tables(self):
        """Test that required tables are created."""
        db = DatabaseService(self.db_path)

        # Check tables exist by trying operations
        agents = db.get_all_agents()
        self.assertIsInstance(agents, list)

        messages = db.get_all_messages()
        self.assertIsInstance(messages, list)


class TestAgentCRUD(unittest.TestCase):
    """Tests for Agent CRUD operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = DatabaseService(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_get_agent(self):
        """Test saving and retrieving an agent."""
        agent = AIAgent(
            name="TestAgent",
            background_prompt="A test agent",
            model="gpt-4o-mini"
        )
        agent_id = self.db.save_agent(agent)
        self.assertIsNotNone(agent_id)
        self.assertGreater(agent_id, 0)

        retrieved = self.db.get_agent(agent_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "TestAgent")
        self.assertEqual(retrieved.model, "gpt-4o-mini")

    def test_update_agent(self):
        """Test updating an existing agent."""
        agent = AIAgent(name="Original")
        agent_id = self.db.save_agent(agent)

        # Retrieve, modify, save again
        agent = self.db.get_agent(agent_id)
        agent.name = "Updated"
        agent.temperature = 0.9
        self.db.save_agent(agent)

        retrieved = self.db.get_agent(agent_id)
        self.assertEqual(retrieved.name, "Updated")
        self.assertEqual(retrieved.temperature, 0.9)

    def test_delete_agent(self):
        """Test deleting an agent."""
        agent = AIAgent(name="ToDelete")
        agent_id = self.db.save_agent(agent)

        self.db.delete_agent(agent_id)

        retrieved = self.db.get_agent(agent_id)
        self.assertIsNone(retrieved)

    def test_get_all_agents(self):
        """Test retrieving all agents."""
        self.db.save_agent(AIAgent(name="Agent1"))
        self.db.save_agent(AIAgent(name="Agent2"))
        self.db.save_agent(AIAgent(name="Agent3"))

        agents = self.db.get_all_agents()
        self.assertGreaterEqual(len(agents), 3)

    def test_get_ai_agents_excludes_architect(self):
        """Test get_ai_agents excludes The Architect."""
        # Create The Architect
        architect = AIAgent(name="The Architect", is_architect=True)
        self.db.save_agent(architect)

        # Create regular agent
        self.db.save_agent(AIAgent(name="Regular"))

        ai_agents = self.db.get_ai_agents()
        for agent in ai_agents:
            self.assertFalse(agent.is_architect)

    def test_get_architect(self):
        """Test retrieving The Architect."""
        architect = AIAgent(name="The Architect", is_architect=True)
        self.db.save_agent(architect)

        retrieved = self.db.get_architect()
        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.is_architect)

    def test_agent_with_all_fields(self):
        """Test saving agent with all fields populated."""
        agent = AIAgent(
            name="FullAgent",
            background_prompt="Full background",
            agent_type="bot",
            model="gpt-4o",
            temperature=1.2,
            hud_input_format="compact_json",
            hud_output_format="toon",
            room_wpm=120,
            can_create_agents=True,
            self_concept_json='{"key": "value"}',
            room_billboard="Welcome!"
        )
        agent_id = self.db.save_agent(agent)
        retrieved = self.db.get_agent(agent_id)

        self.assertEqual(retrieved.agent_type, "bot")
        self.assertEqual(retrieved.model, "gpt-4o")
        self.assertEqual(retrieved.hud_input_format, "compact_json")
        self.assertTrue(retrieved.can_create_agents)
        self.assertEqual(retrieved.room_billboard, "Welcome!")


class TestMessageCRUD(unittest.TestCase):
    """Tests for Message CRUD operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = DatabaseService(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_get_message(self):
        """Test saving and retrieving a message."""
        msg = ChatMessage(
            room_id=1,
            sender_name="Alice",
            content="Hello, world!"
        )
        msg_id = self.db.save_message(msg)
        self.assertIsNotNone(msg_id)

        retrieved = self.db.get_message_by_id(msg_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.sender_name, "Alice")
        self.assertEqual(retrieved.content, "Hello, world!")

    def test_get_messages_for_room(self):
        """Test retrieving messages for a specific room."""
        # Messages for room 1
        self.db.save_message(ChatMessage(room_id=1, sender_name="A", content="Msg1"))
        self.db.save_message(ChatMessage(room_id=1, sender_name="B", content="Msg2"))

        # Messages for room 2
        self.db.save_message(ChatMessage(room_id=2, sender_name="C", content="Msg3"))

        room1_msgs = self.db.get_messages_for_room(1)
        self.assertEqual(len(room1_msgs), 2)

        room2_msgs = self.db.get_messages_for_room(2)
        self.assertEqual(len(room2_msgs), 1)

    def test_get_messages_since(self):
        """Test retrieving messages since a sequence number."""
        self.db.save_message(ChatMessage(room_id=1, content="Old", sequence_number=10))
        self.db.save_message(ChatMessage(room_id=1, content="New", sequence_number=20))
        self.db.save_message(ChatMessage(room_id=1, content="Newer", sequence_number=30))

        msgs = self.db.get_messages_since(15)
        contents = [m.content for m in msgs]
        self.assertIn("New", contents)
        self.assertIn("Newer", contents)
        self.assertNotIn("Old", contents)

    def test_clear_messages(self):
        """Test clearing all messages."""
        self.db.save_message(ChatMessage(room_id=1, content="Test1"))
        self.db.save_message(ChatMessage(room_id=1, content="Test2"))

        self.db.clear_messages()

        msgs = self.db.get_all_messages()
        self.assertEqual(len(msgs), 0)

    def test_clear_room_messages(self):
        """Test clearing messages for specific room."""
        self.db.save_message(ChatMessage(room_id=1, content="Room1"))
        self.db.save_message(ChatMessage(room_id=2, content="Room2"))

        self.db.clear_room_messages(1)

        room1_msgs = self.db.get_messages_for_room(1)
        room2_msgs = self.db.get_messages_for_room(2)

        self.assertEqual(len(room1_msgs), 0)
        self.assertEqual(len(room2_msgs), 1)

    def test_get_next_sequence_number(self):
        """Test sequence number generation."""
        # With no messages, should return 1
        seq1 = self.db.get_next_sequence_number()
        self.assertEqual(seq1, 1)

        # Save a message to advance the sequence
        self.db.save_message(ChatMessage(room_id=1, content="Test", sequence_number=1))

        # Now should return 2
        seq2 = self.db.get_next_sequence_number()
        self.assertEqual(seq2, 2)

    def test_message_with_reply(self):
        """Test saving message with reply_to_id."""
        parent_id = self.db.save_message(ChatMessage(room_id=1, content="Parent"))
        reply_id = self.db.save_message(ChatMessage(
            room_id=1,
            content="Reply",
            reply_to_id=parent_id
        ))

        reply = self.db.get_message_by_id(reply_id)
        self.assertEqual(reply.reply_to_id, parent_id)


class TestMembershipCRUD(unittest.TestCase):
    """Tests for RoomMembership CRUD operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = DatabaseService(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_get_membership(self):
        """Test saving and retrieving a membership."""
        membership = RoomMembership(
            agent_id=5,
            room_id=10,
            attention_pct=25.0
        )
        mem_id = self.db.save_membership(membership)
        self.assertIsNotNone(mem_id)

        retrieved = self.db.get_membership(5, 10)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.attention_pct, 25.0)

    def test_get_room_members(self):
        """Test getting all memberships for a room."""
        self.db.save_membership(RoomMembership(agent_id=1, room_id=5))
        self.db.save_membership(RoomMembership(agent_id=2, room_id=5))
        self.db.save_membership(RoomMembership(agent_id=3, room_id=5))

        members = self.db.get_room_members(5)
        self.assertEqual(len(members), 3)

    def test_get_agent_memberships(self):
        """Test getting all memberships for an agent."""
        self.db.save_membership(RoomMembership(agent_id=5, room_id=1))
        self.db.save_membership(RoomMembership(agent_id=5, room_id=2))
        self.db.save_membership(RoomMembership(agent_id=5, room_id=3))

        memberships = self.db.get_agent_memberships(5)
        self.assertEqual(len(memberships), 3)

    def test_delete_membership(self):
        """Test deleting a membership."""
        self.db.save_membership(RoomMembership(agent_id=5, room_id=10))

        self.db.delete_membership(5, 10)

        retrieved = self.db.get_membership(5, 10)
        self.assertIsNone(retrieved)

    def test_update_membership(self):
        """Test updating an existing membership."""
        self.db.save_membership(RoomMembership(agent_id=5, room_id=10, attention_pct=10.0))

        membership = self.db.get_membership(5, 10)
        membership.attention_pct = 50.0
        self.db.save_membership(membership)

        retrieved = self.db.get_membership(5, 10)
        self.assertEqual(retrieved.attention_pct, 50.0)


class TestSettingsCRUD(unittest.TestCase):
    """Tests for Settings CRUD operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = DatabaseService(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_set_and_get_setting(self):
        """Test saving and retrieving a setting."""
        self.db.set_setting("api_key", "test-key-123")
        value = self.db.get_setting("api_key")
        self.assertEqual(value, "test-key-123")

    def test_get_missing_setting_with_default(self):
        """Test getting missing setting returns default."""
        value = self.db.get_setting("missing_key", "default_value")
        self.assertEqual(value, "default_value")

    def test_update_setting(self):
        """Test updating an existing setting."""
        self.db.set_setting("key", "value1")
        self.db.set_setting("key", "value2")

        value = self.db.get_setting("key")
        self.assertEqual(value, "value2")


class TestReactions(unittest.TestCase):
    """Tests for message reaction operations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = DatabaseService(self.db_path)
        # Create a message to react to
        self.msg_id = self.db.save_message(ChatMessage(room_id=1, content="Test"))

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    
    
    
class TestSessionExportImport(unittest.TestCase):
    """Tests for session export/import functionality."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = DatabaseService(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_session(self):
        """Test exporting session data."""
        self.db.save_agent(AIAgent(name="ExportTest"))
        self.db.save_message(ChatMessage(room_id=1, content="Export msg"))

        data = self.db.export_session()

        self.assertIn('agents', data)
        self.assertIn('messages', data)
        self.assertGreater(len(data['agents']), 0)

    def test_import_session(self):
        """Test importing session data (messages only, as designed)."""
        # Create initial data with an agent and message
        agent_id = self.db.save_agent(AIAgent(name="Original"))
        self.db.save_message(ChatMessage(room_id=agent_id, content="Test message"))

        # Export
        exported = self.db.export_session()

        # Verify export has both agents and messages
        self.assertIn('agents', exported)
        self.assertIn('messages', exported)
        self.assertGreater(len(exported['agents']), 0)
        self.assertGreater(len(exported['messages']), 0)

        # Create new database and import
        new_db_path = os.path.join(self.tmpdir, "import_test.db")
        new_db = DatabaseService(new_db_path)
        new_db.import_session(exported)

        # Import only imports messages, not agents (by design - see docstring)
        messages = new_db.get_all_messages()
        self.assertGreater(len(messages), 0)


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseServiceSetup))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentCRUD))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageCRUD))
    suite.addTests(loader.loadTestsFromTestCase(TestMembershipCRUD))
    suite.addTests(loader.loadTestsFromTestCase(TestSettingsCRUD))
    suite.addTests(loader.loadTestsFromTestCase(TestReactions))
    suite.addTests(loader.loadTestsFromTestCase(TestSessionExportImport))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("Database Service Test Suite")
    print("=" * 70)
    print()

    success = run_tests()

    print()
    print("=" * 70)
    if success:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED - See above for details")
    print("=" * 70)

    sys.exit(0 if success else 1)
