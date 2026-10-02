# Security policy

## Supported versions

EIO-Agents uses the private reporting channel below for security reports. Release support applies to published
versions.

| Version | Supported |
|---|---|
| `0.6.0rc1` | Security fixes during its release-candidate series |
| Historical development candidates | No public support commitment |

## Reporting a vulnerability

**Do not open a public issue for a security report.** Use one of these private channels:

- GitHub private vulnerability reporting: the "Report a vulnerability" button on the repository's Security tab;
- email: support@proofagent.ai.

Please include:

- a description of the issue and its impact;
- a minimal reproduction (an archive or record that triggers it, or a code snippet), with any personal data removed;
- the output of `eio-agents version` and your Python version;
- any mitigation you suggest.

We aim to acknowledge a report within 2 business days and to give an initial assessment within 5 business days. When a
fix is released we publish a GitHub Security Advisory, credit the reporter unless they ask not to be named, and note the
advisory in [CHANGELOG.md](CHANGELOG.md).

## Scope

EIO-Agents converts, validates and verifies evaluation records. These are in scope:

- **Crafted input.** An archive or record that makes the library crash outside its documented exceptions, or use unbounded
  memory or CPU.
- **Verification bypass.** A record that passes `verify()` but differs from the record its archive converts to, or that
  `validate()` accepts although it breaks an EIO rule (for example a witness flag or a proof status that does not
  recompute).
- **Redaction bypass.** A value of a class the redactor covers (an e-mail address, an SSN-form or IBAN-form number, a
  Luhn-valid card number, a key with the prefix `sk-`, `AKIA`, `ghp_` or `xoxa-`/`xoxb-`/`xoxp-`, or the four digits
  after "last 4" or "SSN") that reaches an excerpt or any other field of a record unredacted.
- **Digest or id collisions.** Two different records with one `per_sha256`, or two different refs or claims with one id,
  caused by the canonical form or the id recipes.
- **Integrity of the bundled EIO release.** A way to make `eio_agents.ontology.load()` accept modules whose bytes differ
  from their pins.
- **Supply chain.** Issues with the two runtime dependencies, PyYAML (used only through `safe_load`) and `jsonschema`, as
  they affect this library.

Out of scope:

- whether a model-graded (harness LLM) verdict in an archive is correct. EIO-Agents records such verdicts as support, never
  as proof;
- personal data of classes the redactor does not cover, such as names, phone numbers, postal addresses or other kinds
  of tokens. This is a documented limitation (see [docs/concepts.md](docs/concepts.md#evidence));
- the content of provisional framework mappings (please open a public issue or a mapping proposal instead);
- ProofAgent Harness and ProofAgent Platform, which have their own security policies and reporting channels;
- vulnerabilities in dependencies that do not affect EIO-Agents (please report them upstream).

## Notes for integrators

- `convert()` takes JSON bytes or a parsed dict only; it never reads a path (`convert_file()` reads a file the caller
  names). `validate()`, `verify()` and `explain()` run in process: no temporary file and no child process.
- A PER record is not signed. A matching digest shows that a record is unchanged and correctly derived from the given
  archive; it does not show who produced the archive. Keep archives and records in storage you control.
- Records hold excerpts of at most 400 code points with pattern redaction, and can still contain personal data. Treat
  records as personal data unless you have reviewed them. The archives they are derived from may contain more; protect
  archives accordingly.
- Limit archive size, and run conversion and verification under a timeout, when the input is untrusted: redaction time
  grows quadratically with the length of some crafted inputs. A fix is planned (it was not part of step L2).
