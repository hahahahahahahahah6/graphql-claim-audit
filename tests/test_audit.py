import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from graphql_claim_audit import audit
from graphql_claim_audit.audit import claims, evidence, normalize, POS_PATTERN, NEG_PATTERN
from graphql_claim_audit.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class AuditTests(unittest.TestCase):
    def fixture(self, name, severity=None):
        result = audit(FIXTURES / name)
        self.assertEqual(result["verdict"], "FAIL" if severity == "HIGH" else "PASS")
        self.assertEqual([f["severity"] for f in result["findings"]], [severity] if severity else [])
        return result

    def temporary(self, doc, source=None, filename="app.py", **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(doc)
            if source is not None:
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            return audit(root, **kwargs)

    def test_01_strawberry(self):
        result = self.fixture('strawberry', None)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'strawberry')]), 0)

    def test_02_graphene(self):
        result = self.fixture('graphene', None)

    def test_03_ariadne(self):
        result = self.fixture('ariadne', None)

    def test_04_strawberry_type(self):
        result = self.fixture('strawberry_type', None)

    def test_05_graphene_type(self):
        result = self.fixture('graphene_type', None)

    def test_06_ariadne_type(self):
        result = self.fixture('ariadne_type', None)

    def test_07_client(self):
        result = self.fixture('client', None)

    def test_08_alias(self):
        result = self.fixture('alias', None)

    def test_09_bare_import(self):
        result = self.fixture('bare_import', 'HIGH')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'bare_import')]), 2)

    def test_10_local_schema(self):
        result = self.fixture('local_schema', 'HIGH')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'local_schema')]), 2)

    def test_11_rest(self):
        result = self.fixture('rest', 'HIGH')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'rest')]), 2)

    def test_12_query_param(self):
        result = self.fixture('query_param', 'HIGH')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'query_param')]), 2)

    def test_13_string(self):
        result = self.fixture('string', 'HIGH')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'string')]), 2)

    def test_14_webhook(self):
        result = self.fixture('webhook', 'HIGH')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'webhook')]), 2)

    def test_15_negative(self):
        result = self.fixture('negative', 'HIGH')
        self.assertEqual(result["findings"][0]["rule"], "documented-no-graphql-claim-false")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'negative')]), 2)

    def test_16_no_claim(self):
        result = self.fixture('no_claim', None)

    def test_17_bare_noun(self):
        result = self.fixture('bare_noun', None)

    def test_18_rest_claim(self):
        result = self.fixture('rest_claim', None)

    def test_19_no_source(self):
        self.assertEqual(self.temporary('graphql api')['findings'][0]['severity'], 'HIGH')
        self.assertEqual(self.temporary('no graphql support')['findings'], [])

    def test_20_tests_only(self):
        source = 'import strawberry\nstrawberry.Schema()'
        for filename in ('tests/app.py', 'test_app.py', 'app_test.py'):
            result = self.temporary('graphql api', source, filename)
            self.assertEqual(result['findings'][0]['severity'], 'MEDIUM')
            self.assertEqual(result['verdict'], 'PASS')
            self.assertEqual(self.temporary('graphql api', source, filename, fail_on='MEDIUM')['verdict'], 'FAIL')

    def test_21_fences_inline(self):
        for fence in ('```', '~~~~'):
            self.assertEqual(self.temporary(fence + '\ngraphql api\n' + fence)['findings'], [])
        self.assertEqual(self.temporary('`graphql api`')['verdict'], 'FAIL')

    def test_22_negation(self):
        self.assertEqual(claims('does not support graphql'), (False, True))
        self.assertEqual(claims("doesn't support graphql"), (False, True))
        self.assertEqual(claims('no graphql api support'), (False, True))

    def test_23_client_halves(self):
        for source in ('from gql import Client\nClient()', 'client.execute(query)'):
            self.assertEqual(self.temporary('graphql api', source)['verdict'], 'FAIL')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'README.md').write_text('graphql api')
            (root/'a.py').write_text('from gql import Client\nClient()')
            (root/'b.py').write_text('client.execute(query)')
            self.assertEqual(audit(root)['verdict'], 'FAIL')

    def test_24_self_audit(self):
        result = audit(ROOT)
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['claims'], {'positive': False, 'negative': False})
        for path in [ROOT/'README.md'] + list(ROOT.glob('**/docs/**/*.md')):
            text = normalize(path.read_text())
            self.assertIsNone(POS_PATTERN.search(text), str(path))
            self.assertIsNone(NEG_PATTERN.search(text), str(path))

    def test_25_cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as caught:
            main(['--version'])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), '0.1.0')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([str(FIXTURES/'strawberry'), '--json']), 0)
        self.assertEqual(json.loads(output.getvalue())['verdict'], 'PASS')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main([str(FIXTURES/'strawberry'), '--verbose'])
        self.assertIn('app.py', output.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'docs').mkdir()
            (root/'docs'/'old.md').write_text('graphql api')
            self.assertEqual(audit(root)['verdict'], 'FAIL')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(root), '--ignore', 'docs/*.md']), 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['/nonexistent/audit-root']), 1)
            with self.assertRaises(SystemExit) as caught:
                main(['--invalid'])
            self.assertEqual(caught.exception.code, 1)

    def test_26_env_guard(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            if path.name == '.env':
                raise AssertionError('environment file was opened')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            self.assertEqual(audit(FIXTURES)['verdict'], 'PASS')

    def test_27_packaging(self):
        command = 'py' + 'thon'
        for folder in (ROOT/'graphql_claim_audit', ROOT/'tests'):
            for path in folder.rglob('*.py'):
                self.assertIsNone(re.search(r'\b' + command + r'\b', path.read_text()), str(path))
        self.assertIsNone(re.search(r'\b' + command + r'\b', (ROOT/'README.md').read_text()))
        project = (ROOT/'pyproject.toml').read_text()
        self.assertIn('license = "MIT"', project)
        self.assertIn('setuptools>=77', project)
        self.assertIn('requires-' + command + ' = ">=3.9"', project)
        self.assertIn('recursive-include tests', (ROOT/'MANIFEST.in').read_text())

    def test_28_additional_schema_routes(self):
        for source in ('from graphql import GraphQLSchema as GS\nGS()',
                       'import graphql_core as core\ncore.GraphQLSchema()',
                       'from strawberry.fastapi import GraphQLRouter as Router\nRouter(schema)',
                       'import strawberry\nstrawberry.fastapi.GraphQLRouter(schema)',
                       'from strawberry import Schema as S\nS()',
                       'from ariadne import MutationType as MT\nMT()'):
            self.assertTrue(evidence(source), source)

    def test_29_exclusions(self):
        for filename in ('fixtures/app.py', 'docs/app.py', 'examples/app.py'):
            result = self.temporary('graphql api', 'import strawberry\nstrawberry.Schema()', filename)
            self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        for source in ('from strawberry import Schema',
                       'def graphql_handler():\n    return "constant"',
                       '"""import strawberry; strawberry.Schema()"""',
                       '# strawberry.Schema()\nx = "strawberry.Schema()"'):
            self.assertFalse(evidence(source))

    def test_30_normalization_scope(self):
        self.assertEqual(claims('GRAPHQL-API'), (True, False))
        self.assertEqual(claims('graphql\nendpoint'), (True, False))
        self.assertEqual(claims('graphql\n\nendpoint'), (False, False))
        self.assertEqual(claims('graphql apiculture'), (False, False))
        self.assertEqual(claims('webhook websocket server server-sent events filter by query json api'), (False, False))

    def test_31_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'README.md').write_text('graphql api')
            (root/'examples').mkdir()
            (root/'examples/source.py').write_text('import strawberry\nstrawberry.Schema()')
            (root/'app.py').symlink_to(root/'examples/source.py')
            (root/'linked').symlink_to(root/'examples', target_is_directory=True)
            self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')

    def test_32_asymmetry_and_two_families(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'tests/docs').mkdir(parents=True)
            (root/'tests/docs/note.md').write_text('no graphql support')
            (root/'app.py').write_text('import strawberry\nstrawberry.Schema()')
            self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')
        result = self.temporary('graphql api\n\nno graphql support')
        self.assertEqual(len(result['findings']), 1)

    def test_33_parse_warning(self):
        result = self.temporary('graphql api', 'def invalid(')
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(len(result['warnings']), 1)


if __name__ == '__main__':
    unittest.main()
