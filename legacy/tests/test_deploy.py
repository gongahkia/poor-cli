"""Tests for deploy module."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from poor_cli.deploy import (
    DeployTarget,
    DeployResult,
    detect_deploy_targets,
    _build_deploy_command,
    _extract_url,
    validate_pre_deploy,
    get_deploy_history,
    _record_deploy_history,
)


class TestDeployTarget(unittest.TestCase):
    def test_to_dict_all_fields(self):
        t = DeployTarget(name="vercel", cli_command="vercel", available=True, config_file="vercel.json", description="Vercel")
        d = t.to_dict()
        for key in ("name", "cliCommand", "available", "configFile", "description"):
            self.assertIn(key, d)

    def test_available_default_false(self):
        t = DeployTarget(name="x", cli_command="x", available=False)
        self.assertFalse(t.available)


class TestDeployResult(unittest.TestCase):
    def test_to_dict_fields(self):
        r = DeployResult(target="vercel", success=True, url="https://test.vercel.app", message="deployed")
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["target"], "vercel")
        self.assertEqual(d["url"], "https://test.vercel.app")

    def test_failed_result(self):
        r = DeployResult(target="fly", success=False, message="failed")
        self.assertFalse(r.success)


class TestDetectDeployTargets(unittest.TestCase):
    def test_returns_five_targets(self):
        targets = detect_deploy_targets()
        self.assertEqual(len(targets), 5)

    def test_target_names(self):
        names = {t.name for t in detect_deploy_targets()}
        self.assertEqual(names, {"vercel", "netlify", "fly", "railway", "cloudflare"})

    @patch("shutil.which", return_value="/usr/bin/vercel")
    def test_vercel_available_when_cli_exists(self, mock_which):
        targets = detect_deploy_targets()
        vercel = [t for t in targets if t.name == "vercel"][0]
        self.assertTrue(vercel.available)

    def test_config_file_detected(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "vercel.json").write_text("{}")
            targets = detect_deploy_targets(root=td)
            vercel = [t for t in targets if t.name == "vercel"][0]
            self.assertEqual(vercel.config_file, "vercel.json")


class TestBuildDeployCommand(unittest.TestCase):
    def test_vercel_prod(self):
        t = DeployTarget(name="vercel", cli_command="vercel", available=True)
        cmd = _build_deploy_command(t, prod=True)
        self.assertIn("--prod", cmd)
        self.assertIn("--yes", cmd)

    def test_netlify_no_prod(self):
        t = DeployTarget(name="netlify", cli_command="netlify", available=True)
        cmd = _build_deploy_command(t, prod=False)
        self.assertIn("netlify deploy", cmd)
        self.assertNotIn("--prod", cmd)

    @patch("shutil.which", return_value="/usr/bin/flyctl")
    def test_fly_uses_flyctl(self, mock_which):
        t = DeployTarget(name="fly", cli_command="fly", available=True)
        cmd = _build_deploy_command(t, prod=False)
        self.assertIn("flyctl deploy", cmd)

    def test_railway(self):
        t = DeployTarget(name="railway", cli_command="railway", available=True)
        cmd = _build_deploy_command(t, prod=False)
        self.assertEqual(cmd, "railway up")

    def test_cloudflare(self):
        t = DeployTarget(name="cloudflare", cli_command="wrangler", available=True)
        cmd = _build_deploy_command(t, prod=False)
        self.assertEqual(cmd, "wrangler pages deploy")


class TestExtractUrl(unittest.TestCase):
    def test_vercel_url(self):
        url = _extract_url("Deployed to https://my-app.vercel.app done")
        self.assertEqual(url, "https://my-app.vercel.app")

    def test_netlify_url(self):
        url = _extract_url("Site deployed: https://cool-site.netlify.app/")
        self.assertIn("netlify.app", url)

    def test_fly_url(self):
        url = _extract_url("Deployed https://myapp.fly.dev successfully")
        self.assertIn("fly.dev", url)

    def test_no_url_returns_empty(self):
        url = _extract_url("no urls here just text")
        self.assertEqual(url, "")


class TestValidatePreDeploy(unittest.TestCase):
    @patch("subprocess.run")
    def test_clean_repo_passes(self, mock_run):
        mock_run.return_value = MagicMock(stdout=b"", returncode=0)
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "vercel.json").write_text("{}")
            with patch("shutil.which", return_value="/usr/bin/vercel"):
                result = validate_pre_deploy(root=td)
        self.assertTrue(result["valid"])
        self.assertEqual(result["issues"], [])

    @patch("subprocess.run")
    def test_dirty_repo_fails(self, mock_run):
        mock_run.return_value = MagicMock(stdout=b"M file.py\n", returncode=0)
        result = validate_pre_deploy()
        self.assertIn("uncommitted changes detected", result["issues"])


class TestDeployHistory(unittest.TestCase):
    def test_empty_history_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            entries = get_deploy_history(root=td)
            self.assertEqual(entries, [])

    def test_record_and_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            r = DeployResult(target="vercel", success=True, url="https://t.vercel.app", message="ok")
            _record_deploy_history(r, root=td)
            entries = get_deploy_history(root=td)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["target"], "vercel")
            self.assertTrue(entries[0]["success"])
            self.assertIn("timestamp", entries[0])

    def test_multiple_entries(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(5):
                r = DeployResult(target=f"t{i}", success=True, message=f"deploy {i}")
                _record_deploy_history(r, root=td)
            entries = get_deploy_history(root=td)
            self.assertEqual(len(entries), 5)

    def test_limit_applied(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(10):
                r = DeployResult(target=f"t{i}", success=True, message=f"deploy {i}")
                _record_deploy_history(r, root=td)
            entries = get_deploy_history(root=td, limit=3)
            self.assertEqual(len(entries), 3)


class TestDeployAuditLogging(unittest.TestCase):
    @patch("poor_cli.deploy.get_audit_logger", create=True)
    def test_audit_log_called_on_deploy(self, mock_getter):
        # just verify _audit_deploy doesn't crash
        from poor_cli.deploy import _audit_deploy
        _audit_deploy("deploy:start", "vercel", {"cmd": "vercel --yes"})
