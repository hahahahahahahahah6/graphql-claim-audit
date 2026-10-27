# graphql-claim-audit

Version 0.1.0 audits documented schema-based query-interface claims against
Python source without executing the audited project. It runs offline and has
no third-party runtime dependencies. Requires Python 3.9 or later.

Install and run:

```sh
python3 -m pip install .
graphql-claim-audit /path/to/project
python3 -m graphql_claim_audit /path/to/project --json
python3 -m graphql_claim_audit /path/to/project --verbose --ignore 'docs/old.md'
python3 -m graphql_claim_audit /path/to/project --fail-on MEDIUM
```

The scanner reads root README.md and Markdown files beneath any directory
named docs. Inline code counts; fenced blocks are excluded. Matching is case
insensitive, joins lines within paragraphs, expands contracted negation,
converts hyphens to spaces, and uses word boundaries. Negative spans are
removed before positive matching. Only the exact phrase templates stored in
`graphql_claim_audit/audit.py` count. A bare protocol name, REST or JSON
interface, webhook, websocket, server-sent event, or query-parameter filter
does not count as a claim.

Production evidence comes from alias-resolved imports and AST constructs:
library schema constructors, library type definitions, or a gql client
constructor accompanied by an execute call in the same module. Source is
never imported. Tests, fixtures, documentation, examples, and symlinked files
are excluded from production evidence. Test evidence can reduce a missing
capability finding to MEDIUM. Environment files are never read.

HIGH findings fail by default; MEDIUM findings are reported but only fail
when requested. Exit status is 0 for PASS, 2 for FAIL, and 1 for usage or
filesystem errors. JSON includes verdict, findings (rule, severity, message),
claim flags, production and test evidence paths and routes, and parse warnings.
Each claim family produces at most one finding. Verbose text lists evidence.
Repeat --ignore to exclude relative paths matching shell-style globs.

## Limitations

This is a syntactic consistency check, not a runtime or network test. Only the
exact templates in the source are recognized; other wording can be missed.
Imports alone, strings, comments, local lookalike classes, ordinary HTTP
handlers, and filtering functions do not establish capability. Client execution
is checked within a module, without tracing the receiver. Conditional or unused
constructs may count, and rebinding imported names is not tracked. Invalid
source produces warnings and contributes no evidence. A positive claim without
source is reported; an absence claim without source passes. Absence claims
conflicting with production evidence remain HIGH even in documentation nested
inside tests. Ignoring files can change the result.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

The source distribution includes tests and fixtures. Licensed under MIT.
