"""Static claim matching and import-resolved AST evidence."""
import ast
import fnmatch
import os
from pathlib import Path
import re

POSITIVE = (
    "graphql api", "graphql apis", "graphql endpoint", "graphql endpoints",
    "graphql server", "graphql schema", "graphql interface", "graphql support",
    "graphql enabled", "graphql powered", "graphql based", "supports graphql",
    "support for graphql", "uses graphql", "using graphql", "over graphql",
    "via graphql", "with graphql", "graphql query support", "graphql mutation support",
)
NEGATIVE = (
    "no graphql api support", "no graphql support", "does not support graphql",
    "does not use graphql", "graphql not supported", "without graphql",
    "no graphql api", "no graphql",
)
SCHEMA_MODULES = {"strawberry", "graphene", "ariadne", "graphql", "graphql_core"}


def normalize(text):
    return " ".join(text.lower().replace("n't", " not").replace("-", " ").split())


def pattern(phrases):
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r")\b")


POS_PATTERN = pattern(POSITIVE)
NEG_PATTERN = pattern(NEGATIVE)


def claims(text):
    paragraphs = []
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.match(r"^\s{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", line):
                fence = None
            continue
        if match:
            if lines:
                paragraphs.append(" ".join(lines))
                lines = []
            fence = match.group(1)
        elif not line.strip():
            if lines:
                paragraphs.append(" ".join(lines))
                lines = []
        else:
            lines.append(line)
    if lines:
        paragraphs.append(" ".join(lines))
    positive = negative = False
    for paragraph in paragraphs:
        text = normalize(paragraph)
        negative = negative or bool(NEG_PATTERN.search(text))
        positive = positive or bool(POS_PATTERN.search(NEG_PATTERN.sub(" ", text)))
    return positive, negative


def evidence(source):
    tree = ast.parse(source)
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                imports[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                imports[item.asname or item.name] = node.module + "." + item.name

    def resolve(node):
        if isinstance(node, ast.Name):
            return imports.get(node.id, "")
        if isinstance(node, ast.Attribute):
            parent = resolve(node.value)
            return parent + "." + node.attr if parent else ""
        return ""

    def parts(node):
        name = resolve(node).split(".")
        return name[0], name[-1]

    routes = set()
    client = execute = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            module, name = parts(node.func)
            if ((name == "Schema" and module in SCHEMA_MODULES)
                    or (name == "make_executable_schema" and module == "ariadne")
                    or (name == "GraphQLSchema" and module in {"graphql", "graphql_core"})
                    or (name == "GraphQLRouter" and module == "strawberry")):
                routes.add("A")
            if module == "ariadne" and name in {"QueryType", "MutationType"}:
                routes.add("B")
            client = client or (module == "gql" and name == "Client")
            execute = execute or (isinstance(node.func, ast.Attribute) and node.func.attr == "execute")
        elif isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if parts(target) == ("strawberry", "type"):
                    routes.add("B")
            if any(parts(base) == ("graphene", "ObjectType") for base in node.bases):
                routes.add("B")
    if client and execute:
        routes.add("C")
    return sorted(routes)


def audit(root, ignore=(), fail_on="HIGH"):
    root = Path(root)
    if not root.is_dir() or not os.access(str(root), os.R_OK | os.X_OK):
        raise ValueError("root must be a readable directory")
    doc_claims = [False, False]
    production = []
    test_evidence = []
    warnings = []
    for directory, dirs, files in os.walk(str(root), onerror=lambda error: (_ for _ in ()).throw(error)):
        dirs[:] = sorted(d for d in dirs if not Path(directory, d).is_symlink())
        for filename in sorted(files):
            path = Path(directory, filename)
            relative = path.relative_to(root)
            rel = relative.as_posix()
            if path.is_symlink() or any(fnmatch.fnmatchcase(rel, glob) for glob in ignore):
                continue
            is_doc = rel == "README.md" or ("docs" in relative.parts[:-1] and path.suffix.lower() == ".md")
            if is_doc:
                found = claims(path.read_text(encoding="utf-8"))
                doc_claims = [old or new for old, new in zip(doc_claims, found)]
            if path.suffix != ".py" or any(p in {"fixtures", "docs", "examples"} for p in relative.parts[:-1]):
                continue
            is_test = "tests" in relative.parts[:-1] or filename.startswith("test_") or filename.endswith("_test.py")
            try:
                routes = evidence(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeError) as error:
                warnings.append("{}: {}".format(rel, error))
                continue
            if routes:
                (test_evidence if is_test else production).append({"path": rel, "routes": routes})
    findings = []
    if doc_claims[0] and not production:
        findings.append({"rule": "documented-graphql-claim-false", "severity": "MEDIUM" if test_evidence else "HIGH", "message": "Documented query-interface capability has evidence only in tests." if test_evidence else "Documented query-interface capability has no production evidence."})
    if doc_claims[1] and production:
        findings.append({"rule": "documented-no-graphql-claim-false", "severity": "HIGH", "message": "Documented absence conflicts with production evidence."})
    failed = any(f["severity"] == "HIGH" or fail_on == "MEDIUM" for f in findings)
    return {"verdict": "FAIL" if failed else "PASS", "findings": findings, "claims": {"positive": doc_claims[0], "negative": doc_claims[1]}, "evidence": production, "test_evidence": test_evidence, "warnings": warnings}
