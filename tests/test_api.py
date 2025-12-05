#!/usr/bin/env python3
"""Test suite for FastAPI REST API endpoints.

Run with: python -m pytest tests/test_api.py -v
Or standalone: python tests/test_api.py

These tests verify API endpoints work correctly with the service layer.
"""

import sys
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient


class TestAPIMessageEndpoints(unittest.TestCase):
    """Tests for message-related API endpoints."""

    @classmethod
    def setUpClass(cls):
        """Set up test client with mocked services."""
        # We need to mock the services before importing the app
        cls.mock_db = MagicMock()
        cls.mock_openai = MagicMock()
        cls.mock_room = MagicMock()
        cls.mock_heartbeat = MagicMock()

    def setUp(self):
        """Set up fresh test client for each test."""
        # Import app after setting up mocks
        import api

        # Inject mocked services
        api.db = self.mock_db
        api.openai_service = self.mock_openai
        api.room_service = self.mock_room
        api.heartbeat_service = self.mock_heartbeat

        self.client = TestClient(api.app, raise_server_exceptions=False)

    def test_send_message_basic(self):
        """Test sending a basic message."""
        from models import ChatMessage
        from datetime import datetime

        # Setup mock
        mock_message = ChatMessage(
            id=1,
            room_id=2,
            sender_name="Test User",
            content="Hello",
            timestamp=datetime.utcnow(),
            sequence_number=1,
            message_type="text"
        )
        self.mock_db.get_messages_for_room.return_value = [mock_message]

        response = self.client.post(
            "/api/agents/2/room/messages",
            json={"sender_name": "Test User", "content": "Hello"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sender_name"], "Test User")
        self.assertEqual(data["content"], "Hello")

        # Verify room_service.send_message was called correctly
        self.mock_room.send_message.assert_called()

    def test_send_message_with_reply_to_id(self):
        """Test sending a message with reply_to_id parameter.

        This test ensures the API correctly passes reply_to_id to the service layer.
        Regression test for: TypeError: RoomService.send_message() got an unexpected keyword argument 'reply_to_id'
        """
        from models import ChatMessage
        from datetime import datetime

        # Setup mock
        mock_message = ChatMessage(
            id=2,
            room_id=2,
            sender_name="Test User",
            content="This is a reply",
            timestamp=datetime.utcnow(),
            sequence_number=2,
            message_type="text",
            reply_to_id=1
        )
        self.mock_db.get_messages_for_room.return_value = [mock_message]

        response = self.client.post(
            "/api/agents/2/room/messages",
            json={
                "sender_name": "Test User",
                "content": "This is a reply",
                "reply_to_id": 1
            }
        )

        self.assertEqual(response.status_code, 200)

        # Verify room_service.send_message was called with reply_to_id
        call_args = self.mock_room.send_message.call_args
        self.assertEqual(call_args.kwargs.get('reply_to_id'), 1)

    def test_send_message_without_reply_to_id(self):
        """Test sending a message without reply_to_id (should be None)."""
        from models import ChatMessage
        from datetime import datetime

        mock_message = ChatMessage(
            id=3,
            room_id=2,
            sender_name="Test User",
            content="No reply",
            timestamp=datetime.utcnow(),
            sequence_number=3,
            message_type="text"
        )
        self.mock_db.get_messages_for_room.return_value = [mock_message]

        response = self.client.post(
            "/api/agents/2/room/messages",
            json={"sender_name": "Test User", "content": "No reply"}
        )

        self.assertEqual(response.status_code, 200)

        # Verify reply_to_id was passed as None
        call_args = self.mock_room.send_message.call_args
        self.assertIsNone(call_args.kwargs.get('reply_to_id'))


class TestRoomServiceSendMessage(unittest.TestCase):
    """Direct tests for RoomService.send_message() method."""

    def setUp(self):
        """Set up a fresh RoomService with mocked database."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")

        from services.database_service import DatabaseService
        from services.room_service import RoomService

        self.db = DatabaseService(self.db_path)
        self.room_service = RoomService(self.db)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        import gc
        gc.collect()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_send_message_accepts_reply_to_id(self):
        """Test that send_message accepts reply_to_id parameter.

        Regression test for: TypeError: RoomService.send_message() got an unexpected keyword argument 'reply_to_id'
        """
        # This should not raise TypeError
        message = self.room_service.send_message(
            room_id=1,
            sender_name="Test",
            content="Test message",
            reply_to_id=None
        )

        self.assertIsNotNone(message)
        self.assertEqual(message.content, "Test message")

    def test_send_message_with_reply_to_id_value(self):
        """Test send_message correctly stores reply_to_id."""
        # First create a parent message
        parent = self.room_service.send_message(
            room_id=1,
            sender_name="Parent",
            content="Parent message"
        )

        # Now create a reply
        reply = self.room_service.send_message(
            room_id=1,
            sender_name="Reply",
            content="Reply message",
            reply_to_id=parent.id
        )

        self.assertIsNotNone(reply)
        self.assertEqual(reply.reply_to_id, parent.id)

    def test_send_message_signature_matches_api_usage(self):
        """Verify send_message signature matches how the API calls it.

        The API calls: room_service.send_message(room_id, sender_name, content, reply_to_id=...)
        """
        import inspect
        from services.room_service import RoomService

        sig = inspect.signature(RoomService.send_message)
        params = list(sig.parameters.keys())

        # Should have: self, room_id, sender_name, content, message_type, reply_to_id
        self.assertIn('room_id', params)
        self.assertIn('sender_name', params)
        self.assertIn('content', params)
        self.assertIn('reply_to_id', params)


class TestAPIAgentEndpoints(unittest.TestCase):
    """Tests for agent-related API endpoints."""

    def setUp(self):
        """Set up test client."""
        import api

        api.db = MagicMock()
        api.openai_service = MagicMock()
        api.room_service = MagicMock()
        api.heartbeat_service = MagicMock()

        self.client = TestClient(api.app, raise_server_exceptions=False)
        self.mock_db = api.db

    def test_get_agents(self):
        """Test getting list of agents."""
        from models import AIAgent
        from datetime import datetime

        mock_agents = [
            AIAgent(
                id=2,
                name="Test Agent",
                model="gpt-4o-mini",
                background_prompt="Test prompt",
                created_at=datetime.utcnow()
            )
        ]
        self.mock_db.get_all_agents.return_value = mock_agents

        response = self.client.get("/api/agents")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_create_agent(self):
        """Test creating a new agent."""
        self.mock_db.save_agent.return_value = 5

        response = self.client.post(
            "/api/agents",
            json={
                "name": "New Agent",
                "model": "gpt-4o-mini",
                "background_prompt": "A test agent"
            }
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "New Agent")


class TestAPIHealthEndpoint(unittest.TestCase):
    """Tests for health check endpoint."""

    def setUp(self):
        """Set up test client."""
        import api

        api.db = MagicMock()
        api.openai_service = MagicMock()
        api.room_service = MagicMock()
        api.heartbeat_service = MagicMock()
        api.heartbeat_service.is_running = False
        api.openai_service.has_api_key = True

        self.client = TestClient(api.app, raise_server_exceptions=False)

    def test_health_check(self):
        """Test health check returns expected structure."""
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("heartbeat_running", data)
        self.assertIn("api_connected", data)


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestRoomServiceSendMessage))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIMessageEndpoints))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIAgentEndpoints))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIHealthEndpoint))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("API Endpoint Test Suite")
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
