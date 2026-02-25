import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from devbox.workspace.db import (
    STATE_POOL,
    WorkspaceDB,
    WorkspaceRecord,
)
from devbox.workspace.pool import PoolManager
from devbox.workspace.commands import _format_uptime


class WorkspaceDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "workspaces.db"
        self.db = WorkspaceDB(self.db_path)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_claim_pool_member_by_template(self) -> None:
        ws1 = WorkspaceRecord(
            id="1",
            name="pool-a",
            container_id="cid-a",
            state=STATE_POOL,
            template="base",
            created_at="2026-02-01T00:00:00+00:00",
            pool_member=True,
            cpu=2,
            memory="4g",
        )
        ws2 = WorkspaceRecord(
            id="2",
            name="pool-b",
            container_id="cid-b",
            state=STATE_POOL,
            template="python",
            created_at="2026-02-01T00:01:00+00:00",
            pool_member=True,
            cpu=2,
            memory="4g",
        )
        self.db.insert_workspace(ws1)
        self.db.insert_workspace(ws2)

        claimed = self.db.claim_pool_member("dev-python", template="python")
        self.assertIsNotNone(claimed)
        claimed_record, old_name = claimed

        self.assertEqual(old_name, "pool-b")
        self.assertEqual(claimed_record.name, "dev-python")
        self.assertFalse(claimed_record.pool_member)


class PoolManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "workspaces.db"
        self.db = WorkspaceDB(self.db_path)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_initialize_sets_target_and_creates_warm_pool(self) -> None:
        pool = PoolManager(self.db)

        with patch("devbox.workspace.pool.dc.create_container") as create_container:
            create_container.side_effect = [
                SimpleNamespace(id="container-1"),
                SimpleNamespace(id="container-2"),
            ]
            created = pool.initialize(size=2, template="python")

        self.assertEqual(len(created), 2)
        self.assertEqual(self.db.get_pool_target(), 2)
        self.assertEqual(self.db.get_pool_template(), "python")
        self.assertEqual(len(self.db.list_pool_members()), 2)

    def test_acquire_rolls_back_when_container_rename_fails(self) -> None:
        pool = PoolManager(self.db)

        with patch("devbox.workspace.pool.dc.create_container") as create_container:
            create_container.return_value = SimpleNamespace(id="container-1")
            pool.initialize(size=1, template="base")

        with patch("devbox.workspace.pool.dc.rename_container", side_effect=RuntimeError("rename failed")):
            with patch("devbox.workspace.pool.dc.get_container", return_value=SimpleNamespace(status="running")):
                claimed = pool.acquire("dev-1", template="base")

        self.assertIsNone(claimed)
        members = self.db.list_pool_members()
        self.assertEqual(len(members), 1)
        self.assertTrue(members[0].name.startswith("devbox-pool-"))

    def test_acquire_prunes_stale_pool_members(self) -> None:
        pool = PoolManager(self.db)

        with patch("devbox.workspace.pool.dc.create_container") as create_container:
            create_container.return_value = SimpleNamespace(id="container-1")
            pool.initialize(size=1, template="base")

        with patch("devbox.workspace.pool.dc.get_container", return_value=None):
            with patch.object(pool, "_replenish_async") as replenish_async:
                claimed = pool.acquire("dev-1", template="base")

        self.assertIsNone(claimed)
        self.assertEqual(len(self.db.list_pool_members()), 0)
        replenish_async.assert_called_once()


class WorkspaceCommandHelpersTests(unittest.TestCase):
    def test_format_uptime(self) -> None:
        self.assertEqual(_format_uptime(None), "n/a")
        self.assertEqual(_format_uptime(50), "50s")
        self.assertEqual(_format_uptime(61), "1m 1s")
        self.assertEqual(_format_uptime(3661), "1h 1m")


if __name__ == "__main__":
    unittest.main()
