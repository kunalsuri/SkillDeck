import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
from kitchen.cli import main

class TestCli(unittest.TestCase):
    @patch("kitchen.cli.run_precheck")
    def test_cli_precheck_ok_exits_zero(self, mock_precheck):
        mock_precheck.return_value = True
        with patch.object(sys, "argv", ["cli.py", "precheck"]):
            with self.assertRaises(SystemExit) as cm:
                main()
        mock_precheck.assert_called_once()
        self.assertEqual(cm.exception.code, 0)

    @patch("kitchen.cli.run_precheck")
    def test_cli_precheck_blocked_exits_one(self, mock_precheck):
        mock_precheck.return_value = False
        with patch.object(sys, "argv", ["cli.py", "precheck"]):
            with self.assertRaises(SystemExit) as cm:
                main()
        mock_precheck.assert_called_once()
        self.assertEqual(cm.exception.code, 1)

    @patch("kitchen.cli.ingest_all")
    def test_cli_ingest(self, mock_ingest):
        with patch.object(sys, "argv", ["cli.py", "ingest"]):
            main()
        mock_ingest.assert_called_once()

    @patch("kitchen.cli.canonicalize_all")
    def test_cli_canonicalize(self, mock_canonicalize):
        with patch.object(sys, "argv", ["cli.py", "canonicalize"]):
            main()
        mock_canonicalize.assert_called_once()

    @patch("kitchen.cli.run_dedup")
    def test_cli_dedup(self, mock_dedup):
        with patch.object(sys, "argv", ["cli.py", "dedup"]):
            main()
        mock_dedup.assert_called_once()

    @patch("kitchen.cli.prepare_cluster_input")
    def test_cli_cluster_prepare(self, mock_prepare):
        with patch.object(sys, "argv", ["cli.py", "cluster-prepare"]):
            main()
        mock_prepare.assert_called_once()

    @patch("kitchen.cli.apply_cluster_assignments")
    def test_cli_cluster_apply_default_path(self, mock_apply):
        with patch.object(sys, "argv", ["cli.py", "cluster-apply"]):
            main()
        mock_apply.assert_called_once_with(None)

    @patch("kitchen.cli.apply_cluster_assignments")
    def test_cli_cluster_apply_explicit_path(self, mock_apply):
        with patch.object(sys, "argv", ["cli.py", "cluster-apply", "some/path.json"]):
            main()
        mock_apply.assert_called_once_with(Path("some/path.json"))

    @patch("kitchen.cli.run_rank")
    def test_cli_rank(self, mock_rank):
        with patch.object(sys, "argv", ["cli.py", "rank"]):
            main()
        mock_rank.assert_called_once()

    @patch("kitchen.cli.run_nutrition")
    def test_cli_nutrition(self, mock_nutrition):
        with patch.object(sys, "argv", ["cli.py", "nutrition"]):
            main()
        mock_nutrition.assert_called_once()

    @patch("kitchen.cli.prepare_phase_input")
    def test_cli_phase_prepare(self, mock_prepare):
        with patch.object(sys, "argv", ["cli.py", "phase-prepare"]):
            main()
        mock_prepare.assert_called_once()

    @patch("kitchen.cli.apply_phase_assignments")
    def test_cli_phase_apply_default_path(self, mock_apply):
        with patch.object(sys, "argv", ["cli.py", "phase-apply"]):
            main()
        mock_apply.assert_called_once_with(None)

    @patch("kitchen.cli.apply_phase_assignments")
    def test_cli_phase_apply_explicit_path(self, mock_apply):
        with patch.object(sys, "argv", ["cli.py", "phase-apply", "some/path.json"]):
            main()
        mock_apply.assert_called_once_with(Path("some/path.json"))

    @patch("kitchen.cli.prepare_cards_input")
    def test_cli_cards_prepare(self, mock_prepare):
        with patch.object(sys, "argv", ["cli.py", "cards-prepare"]):
            main()
        mock_prepare.assert_called_once()

    @patch("kitchen.cli.apply_card_assignments")
    def test_cli_cards_apply_default_path(self, mock_apply):
        with patch.object(sys, "argv", ["cli.py", "cards-apply"]):
            main()
        mock_apply.assert_called_once_with(None)

    @patch("kitchen.cli.review_skill")
    def test_cli_review_skill(self, mock_review):
        with patch.object(sys, "argv", ["cli.py", "review", "some-skill-id"]):
            main()
        mock_review.assert_called_once_with("some-skill-id", web_mode=False)

    @patch("kitchen.cli.show_queue")
    def test_cli_review_queue(self, mock_queue):
        with patch.object(sys, "argv", ["cli.py", "review", "--queue"]):
            main()
        mock_queue.assert_called_once()

    @patch("kitchen.cli.start_review_server")
    def test_cli_review_web_no_id(self, mock_start_server):
        with patch.object(sys, "argv", ["cli.py", "review", "--web"]):
            main()
        mock_start_server.assert_called_once()

    @patch("kitchen.cli.show_queue")
    def test_cli_review_default_queue(self, mock_queue):
        with patch.object(sys, "argv", ["cli.py", "review"]):
            main()
        mock_queue.assert_called_once()

    @patch("kitchen.cli.run_emit")
    def test_cli_emit(self, mock_emit):
        with patch.object(sys, "argv", ["cli.py", "emit"]):
            main()
        mock_emit.assert_called_once()

    @patch("kitchen.cli.check_freshness")
    def test_cli_freshness(self, mock_freshness):
        with patch.object(sys, "argv", ["cli.py", "freshness"]):
            main()
        mock_freshness.assert_called_once()

    @patch("kitchen.cli.ingest_all")
    @patch("kitchen.cli.canonicalize_all")
    @patch("kitchen.cli.run_dedup")
    @patch("kitchen.cli.run_rank")
    @patch("kitchen.cli.run_nutrition")
    def test_cli_pipeline(self, mock_nutrition, mock_rank, mock_dedup, mock_canonicalize, mock_ingest):
        with patch.object(sys, "argv", ["cli.py", "pipeline"]):
            main()
        mock_ingest.assert_called_once()
        mock_canonicalize.assert_called_once()
        mock_dedup.assert_called_once()
        mock_rank.assert_called_once()
        mock_nutrition.assert_called_once()

if __name__ == "__main__":
    unittest.main()
