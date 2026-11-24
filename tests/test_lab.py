import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lab
import capture


class CleanupSafety(unittest.TestCase):
    def test_cleanup_without_owned_state_does_not_touch_host(self):
        with patch.object(lab, "state", return_value={}), patch.object(lab, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "No owned deployment"):
                lab.cleanup()
            run.assert_not_called()

    def test_cleanup_refuses_a_foreign_container(self):
        foreign = subprocess.CompletedProcess([], 0, json.dumps([{"Config": {"Labels": {"other": "project"}}}]), "")
        with patch.object(lab, "state", return_value={"started_at": "test"}), \
             patch.object(lab, "active", side_effect=lambda unit, user=False: unit == lab.ENGINE), \
             patch.object(lab, "docker", return_value=foreign) as docker:
            with self.assertRaisesRegex(RuntimeError, "foreign container"):
                lab.cleanup()
            self.assertEqual(docker.call_args_list, [call("inspect", lab.CONTAINER, check=False)])

    def test_controlled_failure_always_restarts_web_server(self):
        with patch.object(lab, "state", return_value={"verified_at": "test", "url": "https://example.invalid"}), \
             patch.object(lab, "docker") as docker, \
             patch.object(lab, "http", side_effect=RuntimeError("probe failed")):
            with self.assertRaisesRegex(RuntimeError, "probe failed"):
                lab.troubleshoot()
            self.assertEqual(docker.call_args_list, [call("stop", "--time=5", lab.CONTAINER), call("start", lab.CONTAINER)])

    def test_capture_refuses_to_present_old_results_as_live(self):
        with patch.object(lab, "state", return_value={"verified_at": "test", "cleaned_at": "test"}), \
             patch.object(lab, "docker") as docker:
            with self.assertRaisesRegex(RuntimeError, "before cleanup"):
                capture.main()
            docker.assert_not_called()

    def test_firewall_cleanup_preserves_unexpected_docker_rules(self):
        no_daemon = subprocess.CompletedProcess([], 1, "", "")
        foreign = subprocess.CompletedProcess([], 0, "-N DOCKER-USER\n-A DOCKER-USER -s 192.0.2.1 -j ACCEPT\n", "")
        with patch.object(lab, "run", side_effect=[no_daemon, foreign]) as run:
            with self.assertRaisesRegex(RuntimeError, "preserving them"):
                lab.cleanup_engine_rules()
            self.assertEqual(len(run.call_args_list), 2)


if __name__ == "__main__":
    unittest.main()
