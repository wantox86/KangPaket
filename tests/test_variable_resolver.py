"""Tests for variable resolver, environment manager and runner integration."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.environment_manager import EnvironmentManager
from app.core.postman_importer import (
    PostmanImportError, parse_postman_environment, parse_postman_file,
)
from app.core.runner_engine import RunnerEngine
from app.core.variable_resolver import resolve_profile, resolve_text
from app.models.environment_model import Environment, Variable
from app.models.request_model import RequestProfile
from app.models.response_model import ResponseResult
from app.models.runner_model import RunnerConfig


def _profile(**kw) -> RequestProfile:
    base = dict(
        name="p",
        url="https://{{host}}/api/{{id}}",
        headers={"X-Token": "{{ token }}"},
        params={"q": "{{q}}"},
        body_type="raw",
        body_content='{"u": "{{user}}"}',
        body_form={"f": "{{user}}"},
        auth_type="basic",
        auth_data={"username": "{{user}}", "password": "{{pw}}"},
        assertions=[{"type": "body_contains", "value": "{{user}}"},
                    {"type": "status_code_equals", "value": 200}],
    )
    base.update(kw)
    return RequestProfile(**base)


class ResolveTextTests(unittest.TestCase):
    def test_layer_priority_first_wins(self):
        layers = [{"a": "csv"}, {"a": "env", "b": "env"}, {"a": "glob", "b": "glob", "c": "glob"}]
        self.assertEqual(resolve_text("{{a}}-{{b}}-{{c}}", layers), "csv-env-glob")

    def test_unknown_left_as_is(self):
        self.assertEqual(resolve_text("{{nope}} {{$nope}}", [{"a": "1"}]), "{{nope}} {{$nope}}")

    def test_whitespace_in_placeholder(self):
        self.assertEqual(resolve_text("{{ x }}/{{x }}", [{"x": "1"}]), "1/1")

    def test_non_recursive(self):
        layers = [{"a": "{{b}}", "b": "deep"}]
        self.assertEqual(resolve_text("{{a}}", layers), "{{b}}")

    def test_system_vars(self):
        self.assertTrue(resolve_text("{{$timestamp}}", []).isdigit())
        self.assertTrue(resolve_text("{{$isoTimestamp}}", []).endswith("Z"))
        self.assertEqual(len(resolve_text("{{$guid}}", [])), 36)
        self.assertTrue(0 <= int(resolve_text("{{$randomInt}}", [])) <= 1000)
        self.assertNotEqual(resolve_text("{{$guid}}", []), resolve_text("{{$guid}}", []))

    def test_user_var_overrides_system(self):
        self.assertEqual(resolve_text("{{$guid}}", [{"$guid": "fixed"}]), "fixed")


class ResolveProfileTests(unittest.TestCase):
    LAYERS = [{"user": "bob", "id": "7"}, {"host": "h.io", "token": "t", "pw": "s", "q": "z"}]

    def test_all_fields_resolved(self):
        p = resolve_profile(_profile(), self.LAYERS)
        self.assertEqual(p.url, "https://h.io/api/7")
        self.assertEqual(p.headers, {"X-Token": "t"})
        self.assertEqual(p.params, {"q": "z"})
        self.assertEqual(p.body_content, '{"u": "bob"}')
        self.assertEqual(p.body_form, {"f": "bob"})
        self.assertEqual(p.auth_data, {"username": "bob", "password": "s"})
        self.assertEqual(p.assertions[0]["value"], "bob")
        self.assertEqual(p.assertions[1]["value"], 200)

    def test_original_not_mutated(self):
        orig = _profile()
        snapshot = orig.to_dict()
        resolve_profile(orig, self.LAYERS)
        self.assertEqual(orig.to_dict(), snapshot)


class EnvironmentManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "data", "environments.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file(self):
        m = EnvironmentManager(self.path)
        self.assertEqual((m.envs, m.globals, m.active_id), ([], [], None))
        self.assertEqual(m.layers(), [{}])

    def test_corrupt_file(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("{not json")
        m = EnvironmentManager(self.path)
        self.assertEqual(m.envs, [])

    def test_roundtrip_and_layers(self):
        m = EnvironmentManager(self.path)
        env = m.add(Environment("dev", [
            Variable("host", "dev.io"),
            Variable("password", "pw", secret=True),
            Variable("off", "x", enabled=False),
        ]))
        m.globals = [Variable("host", "glob.io"), Variable("g", "1")]
        m.set_active(env.id)

        m2 = EnvironmentManager(self.path)
        self.assertEqual(m2.active_id, env.id)
        self.assertTrue(m2.active.vars[1].secret)
        self.assertEqual(m2.layers(), [{"host": "dev.io", "password": "pw"}, {"host": "glob.io", "g": "1"}])

    def test_stale_active_id_dropped(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            json.dump({"active": "gone", "globals": [], "envs": []}, f)
        self.assertIsNone(EnvironmentManager(self.path).active_id)

    def test_unique_name(self):
        m = EnvironmentManager(self.path)
        m.add(Environment("dev"))
        self.assertEqual(m.unique_name("dev"), "dev (2)")


class _FakeClient:
    def __init__(self):
        self.sent: list[RequestProfile] = []

    def send(self, profile, **kw):
        self.sent.append(profile)
        return ResponseResult(status_code=200, status_text="OK", body="hi bob", elapsed_ms=1.0)


class _FakeSettings:
    def get(self, key, default=None):
        return default


class RunnerIntegrationTests(unittest.TestCase):
    def _engine(self, env_mgr=None):
        client = _FakeClient()
        return RunnerEngine(client, _FakeSettings(), environments=env_mgr), client

    def test_csv_only_behaviour_unchanged(self):
        engine, client = self._engine()
        item = engine._execute_one(_profile(), 1, RunnerConfig(name="t"), {"host": "a", "id": "1", "user": "bob", "token": "t", "q": "q", "pw": "p"})
        self.assertEqual(client.sent[0].url, "https://a/api/1")
        self.assertEqual(client.sent[0].assertions[0]["value"], "bob")
        self.assertEqual(item.status, "success")

    def test_csv_overrides_env_and_assertions_use_env(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        m = EnvironmentManager(os.path.join(tmp.name, "e.json"))
        env = m.add(Environment("dev", [Variable("host", "env.io"), Variable("user", "bob"), Variable("id", "9")]))
        m.set_active(env.id)
        engine, client = self._engine(m)
        engine._env_layers = m.layers()
        item = engine._execute_one(_profile(), 1, RunnerConfig(name="t"), {"id": "csv"})
        self.assertEqual(client.sent[0].url, "https://env.io/api/csv")
        self.assertEqual(client.sent[0].assertions[0]["value"], "bob")
        self.assertEqual(item.status, "success")

    def test_old_methods_removed(self):
        self.assertFalse(hasattr(RunnerEngine, "_substitute_vars"))
        self.assertFalse(hasattr(RunnerEngine, "_apply_vars_to_profile"))


class PostmanVariableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def _collection(self, variable):
        return {
            "info": {"name": "Demo", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
            "variable": variable,
            "item": [{"name": "r", "request": {
                "method": "GET",
                "url": "{{base}}/x/{{other}}",
                "header": [{"key": "A", "value": "{{base}}"}],
            }}],
        }

    def test_collection_variables_become_variables(self):
        path = self._write("c.json", self._collection([
            {"key": "base", "value": "https://h"},
            {"key": "ApiPassword", "value": "pw"},
            {"key": "off", "value": "1", "disabled": True},
            {"value": "nokey"},
        ]))
        result = parse_postman_file(path)
        by_key = {v.key: v for v in result.variables}
        self.assertEqual(set(by_key), {"base", "ApiPassword", "off"})
        self.assertFalse(by_key["base"].secret)
        self.assertTrue(by_key["ApiPassword"].secret)
        self.assertFalse(by_key["off"].enabled)
        info = [w for w in result.warnings if "imported as environment" in w]
        self.assertEqual(len(info), 1)
        self.assertFalse(any("not converted" in w for w in result.warnings))
        # url still has an unknown {{other}}, header only has known {{base}}
        self.assertTrue(any("URL contains" in w for w in result.warnings))
        self.assertFalse(any("header" in w and "variable" in w for w in result.warnings))

    def test_no_variables_keeps_placeholder_warning(self):
        result = parse_postman_file(self._write("c.json", self._collection([])))
        self.assertEqual(result.variables, [])
        self.assertTrue(any("URL contains" in w for w in result.warnings))

    def test_environment_file(self):
        path = self._write("e.postman_environment.json", {
            "name": "Staging",
            "values": [
                {"key": "host", "value": "s.io", "enabled": True},
                {"key": "token", "value": "t", "enabled": False},
                {"key": "x", "value": "y", "type": "secret"},
            ],
        })
        env = parse_postman_environment(path)
        self.assertEqual(env.name, "Staging")
        self.assertEqual([(v.key, v.enabled, v.secret) for v in env.vars],
                         [("host", True, False), ("token", False, True), ("x", True, True)])

    def test_collection_is_not_environment(self):
        path = self._write("c.json", self._collection([]))
        with self.assertRaises(PostmanImportError):
            parse_postman_environment(path)


if __name__ == "__main__":
    unittest.main()
