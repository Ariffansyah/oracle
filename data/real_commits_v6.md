# Real-commit grading sheet

Fill `grade` with locus | mechanism | wrong, and `verified_by`
with the command that proves it. A mechanism claim that was not
executed is not graded - leave it blank rather than guess.

Hand-graded 2026-09-01 by reading all 40 diffs. Grades follow the rule at the
top of this file; `""` means NOT GRADED because settling it needs an execution
that was not run. Every commit here is an upstream commit from a mature
project - a fix, a feature, a refactor, a docs or annotation change - so a
finding is a false alarm unless the commit genuinely introduces a defect.

  graded 35 findings over 40 commits: locus 1 | mechanism 1 | wrong 32 | not graded 1

`wrong` here almost always means the explanation describes code that is not in
the diff. That is the FABRICATED class, on real commits, at a rate the
synthetic benches do not show.

## axios__axios 6b3c305fc40c  (javascript)
- subject: fix(http): use explicit import instead of TextEncoder global; (#5530)
- files: lib/helpers/formDataToStream.js
- date: 2023-02-03T19:34:07+02:00
- summary: This undoes the defect in lib/helpers/formDataToStream.js. The `TextEncoder` global is replaced by an explicit import, so the original behaviour comes back. Nothing further to raise on this commit.

- (no findings reported)

## axios__axios 4c4e648f409d  (javascript)
- subject: Replacing Object.hasOwnProperty with Object.prototype.hasOwnProperty
- files: lib/utils.js
- date: 2016-09-12T11:26:40-07:00
- summary: This reads like a logic error in lib/utils.js. The commit replaces Object.hasOwnProperty with Object.prototype.hasOwnProperty, which should cause forEach to iterate over inherited properties as well as own ones, breaking the intended iteration over the object's own keys. I would not land this without trying that case.

### finding 1: logic-error
- file: lib/utils.js
- explanation: Using Object.prototype.hasOwnProperty checks every property along the prototype chain, so forEach will invoke the callback for inherited properties as well as those defined directly on the object, leading to unintended side effects or security issues.
- grade: wrong
- verified_by: node -e "Object.hasOwnProperty===Object.prototype.hasOwnProperty" -> true; the two are the SAME function and hasOwnProperty never walks the prototype chain. No-op refactor; claim is inverted.

## axios__axios ffc0237a175b  (javascript)
- subject: Adding support for timeout config closes #56
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/defaults.js
- date: 2015-08-10T19:00:27-06:00
- summary: This looks like a missing input check in lib/adapters/http.js. The change wraps the call to `req.setTimeout()` in a promise handler, which means the timeout is no longer applied during the request itself. This makes the API less robust: callers expecting a timeout will see the request complete without timing out, which can cause unexpected delays or failures. Worth confirming before this lands.

### finding 1: input-validation
- file: lib/adapters/http.js
- explanation: When config.timeout is non-zero, the request is now sent asynchronously, so the timeout handler runs after the request has already completed. This causes the timeout to have no effect, which can lead to long-running requests or failed operations that should have timed out, breaking the intended behavior.
- grade: wrong
- verified_by: diff is a pure ADD of req.setTimeout/request.timeout/timeout:0. There is no 'promise handler' wrapping anything - described code is absent from the diff.

## axios__axios fce210a67e24  (javascript)
- subject: Fixed TransitionalOptions typings (#4147)
- files: index.d.ts
- date: 2021-10-12T09:46:16+02:00
- summary: This undoes the defect in index.d.ts. The three fields that were removed are back in their previous form, restoring the original behaviour. Nothing further to raise on this commit.

- (no findings reported)

## axios__axios 926347315405  (javascript)
- subject: chore(ci): fixed contributors avatar rendering for CHANGELOG.md; (#5514)
- files: bin/contributors.js, templates/contributors.hbs, test/specs/__helpers.js
- date: 2023-01-31T17:56:09+02:00
- summary: This undoes the change in bin/contributors.js that caused the avatar URLs to be scaled down to 16px. The repair is in place, which is the direction I would expect. I would let this land.

- (no findings reported)

## axios__axios 594df987f279  (javascript)
- subject: fix array params
- files: lib/helpers/buildUrl.js, test/specs/helpers/buildUrl.spec.js
- date: 2015-05-27T13:32:34+02:00
- summary: This undoes the defect in lib/helpers/buildUrl.js. The `[key][]` suffix is back on arrays, which is what it should have been all along. I would let this land.

- (no findings reported)

## axios__axios e8cf487ad0f5  (javascript)
- subject: Removing es6-promise dependency
- files: lib/axios.js, package.json, test/specs/promise.spec.js
- date: 2015-07-23T10:43:17-07:00
- summary: This reads like a missing input check in lib/axios.js. The commit removes the polyfill for ES6 Promises, so axios now throws a ReferenceError when used in browsers without native support. I would not land this without trying that case.

### finding 1: input-validation
- file: lib/axios.js
- explanation: When es6-promise is removed, axios attempts to use window.Promise, which throws a ReferenceError in browsers that do not support Promises natively. This would cause an unhandled exception and application crash.
- grade: locus
- verified_by: correct: lib/axios.js drops the es6-promise polyfill, so environments without native Promise lose it. Right file, right consequence.

## axios__axios 22ce6db383bc  (javascript)
- subject: Adding request to error objects when it is available
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/core/createError.js, lib/core/enhanceError.js, lib/core/settle.js
- date: 2017-04-08T21:44:15+02:00
- summary: This looks like a missing input check in lib/adapters/http.js. The change adds request and response arguments to createError and enhanceError, which means callsites that previously ignored those parameters now throw TypeError: undefined is not an object (evaluating 'response.status' or 'request.headers'). This looks like a potential input‑validation defect. Confirm it with the test above.

### finding 1: input-validation
- file: lib/core/createError.js
- explanation: The change adds request and response arguments to createError and enhanceError, so callers that previously ignored these parameters now attempt to access properties on undefined (e.g., response.status or request.headers), which throws TypeError.
- grade: wrong
- verified_by: adding trailing args to a JS function does not make existing callsites throw; the diff updates the callees too.

### finding 2: input-validation
- file: lib/core/enhanceError.js
- explanation: The change adds request and response arguments to createError and enhanceError, so callers that previously ignored these parameters now attempt to access properties on undefined (e.g., response.status or request.headers), which throws TypeError.
- grade: wrong
- verified_by: duplicate of finding 1, same text against a second file.

## clap-rs__clap f8bca3a84bd5  (rust)
- subject: fix(error): Never show unrequested color
- files: src/parse/errors.rs
- date: 2021-10-26T14:26:50-05:00
- summary: This undoes the defect in src/parse/errors.rs. The `[...ColorChoice::Auto)` slice is replaced by `ColorChoice::Never`, which is what it should have been all along. I would let this land.

- (no findings reported)

## clap-rs__clap 479ca76491a7  (rust)
- subject: fix: Always ensure `num_args` is initialized
- files: src/builder/arg.rs, src/builder/debug_asserts.rs
- date: 2022-08-04T09:11:29-05:00
- summary: This undoes the defect in src/builder/arg.rs. The `num_vals` variable is now initialized before the `match`, so the `unwrap_or` returns the existing value instead of inserting, which is the repair direction. I would not hold this up.

- (no findings reported)

## clap-rs__clap edabdf72b59b  (rust)
- subject: fix(complete): Only return imidiate child subcommands
- files: clap_complete/src/dynamic/completer.rs
- date: 2023-07-28T14:51:56-05:00
- summary: This undoes the defect in clap_complete: `all_subcommands` is replaced by `subcommands`, which filters out non‑subcommand parents. The repair reaches every case the original did.

- (no findings reported)

## clap-rs__clap a126149a809f  (rust)
- subject: refactor(complete): Remove redundant dedup
- files: clap_complete/src/engine/complete.rs
- date: 2024-09-20T13:59:16-05:00
- summary: This reads like a logic error in clap_complete. The commit removes the deduplication step in complete_subcommand, which would cause the completion iterator to yield duplicate subcommands for any given prefix, breaking the unique‑per‑prefix guarantee. I would not land this without trying that case.

### finding 1: logic-error
- file: clap_complete/src/engine/complete.rs
- explanation: Removing the deduplication means that if two or more options resolve to the same subcommand, the completion will include multiple entries for that subcommand, breaking the uniqueness requirement for each prefix.
- grade: 
- verified_by: NOT GRADED: needs `cargo test -p clap_complete`. Subject asserts the dedup was redundant; model asserts duplicates. Cannot settle from the diff.

## clap-rs__clap 931b6338f125  (rust)
- subject: refactor(parser): Clarify FromStr from future FromStr
- files: src/builder/value_parser.rs
- date: 2022-09-26T09:51:03-05:00
- summary: This reads like a missing input check in src/builder/value_parser.rs. The change replaces the explicit `FromStr` implementation with a call site cast, which should cause a panic at runtime when the value does not parse, whereas the previous version returned an error. This looks like a potential input‑validation defect. Please check it against the old behaviour before merging.

### finding 1: input-validation
- file: src/builder/value_parser.rs
- explanation: When value_parser is called with a string slice that does not parse as the target type, the new code will panic at runtime when FromStr::from_str panics, whereas the previous code would return an error variant. This makes the API unsafe and introduces potential crashes.
- grade: wrong
- verified_by: diff renames a #[doc(hidden)] trait _ValueParserViaFromStr -> _ValueParserViaParse. No runtime path changes.

## clap-rs__clap 9d07b3c02837  (rust)
- subject: feat(parser): non-empty string ValueParser
- files: src/builder/mod.rs, src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: This reads like a missing input check in src/builder/value_parser.rs. The change replaces the empty‑string check in NonEmptyStringValueParser with a call to to_str(), which returns None for non‑UTF‑8 strings, so expect a panic on invalid input rather than a graceful error. Worth confirming before this lands.

### finding 1: input-validation
- file: src/builder/value_parser.rs
- explanation: parse_ref now calls value.to_str(), which returns None for non‑UTF‑8 strings, so expect a panic on invalid input (e.g., passing a byte array) rather than a graceful error. This looks like a potential input‑validation defect.
- grade: wrong
- verified_by: pure addition of NonEmptyStringValueParser; no existing path altered.

## clap-rs__clap a7a8f93d6b2b  (rust)
- subject: fix(complete): Strip wrappers for running completer
- files: clap_complete/examples/exhaustive.rs, clap_complete/src/env/mod.rs
- date: 2024-09-17T15:47:46-05:00
- summary: This reads like a logic error in clap_complete. The commit replaces Command::get_bin_name with args_os()[0], which should cause the completion system to read from the command line instead of the executable, breaking the intended behavior. Worth confirming before this lands.

### finding 1: logic-error
- file: clap_complete/src/env/mod.rs
- explanation: Using args_os()[0] points the completion system at the first argument provided at runtime, which is usually the program name. This causes the completer to fail to find entries for flags or subcommands defined in the clap app, leading to incomplete or incorrect suggestions.
- grade: wrong
- verified_by: commit is a fix ('Strip wrappers for running completer'); finding describes it as a regression.

## clap-rs__clap f9be3215c189  (rust)
- subject: refactor(parser): Minor clean up
- files: src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: Possible logic error in src/builder/value_parser.rs. The change replaces the generic `ValueParser` trait with specific implementations for common types, which should cause existing code that relied on the trait to fail to compile. I would not land this without trying that case.

### finding 1: logic-error
- file: src/builder/value_parser.rs
- explanation: Using value parsers via `Into<ValueParser>` now requires the type to be explicitly listed, so any code that previously used a generic `ValueParser` will fail to compile. For example, `clap::value_parser!(String)` now raises a "no implementation for `Into<AutoValueParser<String>>`" error because `AutoValueParser<String>` is not in scope.
- grade: wrong
- verified_by: diff adds '// Built-in types' / '// FromStr types' comments inside a doctest. A comment cannot cause compile failures at callsites.

## fastapi__fastapi 9b35d355bfb4  (python)
- subject: 📝 Update `docs_src/path_params_numeric_validations/tutorial006.py` (#11478)
- files: docs_src/path_params_numeric_validations/tutorial006.py, docs_src/path_params_numeric_validations/tutorial006_an.py, docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- date: 2024-08-28T18:39:15-05:00
- summary: This reads like a missing input check in docs_src/path_params_numeric_validations/tutorial006.py. The change moves the numeric check inside the `if size:` block, so calling `read_items(1, 'foo', size=1.5)` with a numeric value now raises ValueError rather than returning a default, which would be a potential input‑validation defect. Confirm it with the test above.

### finding 1: input-validation
- file: docs_src/path_params_numeric_validations/tutorial006.py
- explanation: When size is a non‑integer value (e.g., 1.5), float() fails with a ValueError, whereas the previous int() cast silently truncated the decimal part, leading to incorrect results or crashes for callers expecting floating‑point precision.
- grade: wrong
- verified_by: fabricated: there is no float(), no int() cast and no moved numeric check. Diff only ADDS `if size: results.update(...)` to three tutorial files.

## fastapi__fastapi d11f820ac38b  (python)
- subject: 📝 Update docs for JWT to prevent timing attacks (#14908)
- files: docs/en/docs/tutorial/security/oauth2-jwt.md, docs_src/security/tutorial004_an_py310.py, docs_src/security/tutorial004_py310.py, docs_src/security/tutorial005_an_py310.py, docs_src/security/tutorial005_py310.py
- date: 2026-02-12T19:10:35+01:00
- summary: Possible logic error in docs_src/security/tutorial004_an_py310.py. The change replaces the dynamic password hash with a hardcoded value, which should cause authentication to succeed for any password, opening a security hole. I would not land this without trying that case.

### finding 1: logic-error
- file: docs_src/security/tutorial004_an_py310.py
- explanation: Using a fixed dummy password hash means authenticate_user will always return True, allowing unauthenticated access to the API.
- grade: wrong
- verified_by: INVERTED SECURITY CLAIM: the dummy-hash idiom equalises timing and returns False for unknown users. Claiming it 'always returns True' and allows unauthenticated access is the opposite. Docs-only commit.

### finding 2: security
- file: docs_src/security/tutorial004_an_py310.py
- explanation: Running authenticate_user with any username will now always succeed, bypassing authentication checks, which would allow unauthorized access to the API.
- grade: wrong
- verified_by: near-duplicate of finding 1.

## fastapi__fastapi 6cc24416e228  (python)
- subject: ✏️ Fix docstring typos in http security (#12223)
- files: fastapi/security/http.py
- date: 2024-09-19T11:47:28+02:00
- summary: This undoes the typo in fastapi/security/http.py. The `not provided` text is replaced by `not supplied`, which is the correct word. I would let this land.

- (no findings reported)

## fastapi__fastapi 31887b1cc6fb  (python)
- subject: 🔖 Release version 0.115.4
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2024-10-27T21:51:55Z
- summary: fastapi/__init__.py updates the package version number from 0.115.3 to 0.115.4. The rest of the file is untouched, so I would expect identical output. No defect that I can see in this one.

- (no findings reported)

## fastapi__fastapi c7e7b651d694  (python)
- subject: 🔖 Release version 0.141.0 (#16103)
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2026-07-29T14:45:21Z
- summary: This looks like a logic error in fastapi/__init__.py. The commit changes the package version to 0.141.0, which should cause every reference to the old version to fail. I would hold off on merging this until that is fixed.

### finding 1: logic-error
- file: fastapi/__init__.py
- explanation: Using the literal string "0.140.13" in fastapi/__init__.py, the __version__ variable is now "0.141.0", so expect every code path that compared the old version to fail. This would cause warnings or crashes at runtime.
- grade: wrong
- verified_by: version bump 0.140.13 -> 0.141.0 plus release notes. 'every code path that compared the old version' does not exist.

## fastapi__fastapi 91a929319c4c  (python)
- subject: ♻️ Update internal checks to support Pydantic 2.10 (#12914)
- files: fastapi/_compat.py, fastapi/params.py
- date: 2024-11-12T17:10:42+01:00
- summary: This reads like a logic error in fastapi/_compat.py. The commit replaces `PYDANTIC_VERSION` with `PYDANTIC_VERSION_MINOR_TUPLE`, which is a slice of the version string. The slice raises ValueError for versions less than two dot-separated parts, so expect compatibility problems with older Pydantic releases. Confirm it with the test above.

### finding 1: logic-error
- file: fastapi/_compat.py
- explanation: `PYDANTIC_VERSION` is replaced by `PYDANTIC_VERSION_MINOR_TUPLE`, which is a slice of the version string. The slice raises ValueError for versions less than two dot-separated parts, so expect compatibility problems with older Pydantic releases.
- grade: mechanism
- verified_by: right place (the new PYDANTIC_VERSION_MINOR_TUPLE parse) but the stated trigger is wrong: '2'.split('.')[:2] -> ['2'] parses fine. A pre-release like '2.10b1' would be the real risk; not what was claimed.

## fastapi__fastapi 3611c3fc5b82  (python)
- subject: ⬆️ Add support for Python 3.14 (#14165)
- files: .github/workflows/test.yml, pyproject.toml, requirements-tests.txt, tests/test_tutorial/test_sql_databases/test_tutorial001.py, tests/test_tutorial/test_sql_databases/test_tutorial002.py
- date: 2025-10-10T11:44:39+02:00
- summary: This looks like a missing teardown in test_tutorial001.py and test_tutorial002.py. The commit adds Python 3.14 to the test matrix and excludes pydantic-v1 on that version, which is the first change. The second change is in test_tutorial001.py and test_tutorial002.py, where `mod.engine.dispose()` is called after the test client closes, which is the direction in which the behaviour shifts: the existing call site is preserved but the call now comes after the resource is gone, so expect a resource leak. This is the first thing I would run.

### finding 1: resource-leak
- file: tests/test_tutorial/test_sql_databases/test_tutorial001.py
- explanation: When Python 3.14 is tested, pydantic-v1 is excluded, so the `mod.engine.dispose()` call is no longer guarded by the previous `python-version`/`pydantic-version` pair. This makes the database connection leak when running Python 3.14, which is a resource‑management defect.
- grade: wrong
- verified_by: CI matrix/pyproject change; mod.engine.dispose() is not in this diff.

### finding 2: resource-leak
- file: tests/test_tutorial/test_sql_databases/test_tutorial002.py
- explanation: When Python 3.14 is tested, pydantic-v1 is excluded, so the `mod.engine.dispose()` call is no longer guarded by the previous `python-version`/`pydantic-version` pair. This makes the database connection leak when running Python 3.14, which is a resource‑management defect.
- grade: wrong
- verified_by: BYTE-IDENTICAL DUPLICATE of finding 1.

## fastapi__fastapi 2260afaf4331  (python)
- subject: 🐛 Fix failing test, update format for raised errors (#15804)
- files: fastapi/routing.py
- date: 2026-06-20T00:51:31Z
- summary: This undoes the defect in fastapi/routing.py. `os.path.isdir()` is replaced by `os.path.exists()`, which should restore the original behaviour. Nothing further to raise on it.

- (no findings reported)

## gin-gonic__gin dbd8a2515093  (go)
- subject: feat: added `AbortWithStatusPureJSON()` in `Context` (#4290)
- files: context.go, context_test.go
- date: 2025-07-13T09:40:35+08:00
- summary: context.go may have picked up a logic error here. The change moves the JSON body generation into `AbortWithStatusPureJSON`, which should cause the request to be aborted before the JSON is written, which would cause an HTTP 500 error instead of the expected status code and JSON body. I would not land this without trying that case.

### finding 1: logic-error
- file: context.go
- explanation: `AbortWithStatusPureJSON` writes the status code directly to the response writer after calling `Abort()`, which should cause the request to be aborted before the JSON body is written. This leads to an HTTP 500 error instead of the intended status code and JSON response, breaking the intended behavior.
- grade: wrong
- verified_by: pure addition of AbortWithStatusPureJSON, mirroring the existing AbortWithStatusJSON idiom (Abort() then render).

## gin-gonic__gin a48f83c9a1a1  (go)
- subject: Adding helper functions to router group for LINK and UNLINK.
- files: routergroup.go
- date: 2014-12-15T13:19:51-04:00
- summary: Worth a look: logic error in routergroup.go. The commit moves the path argument to the front of Handle calls in RouterGroup, which would cause existing handlers to be shadowed or silently ignored. This looks like a logic error and missing input check. Please check it against the old behaviour before merging.

### finding 1: logic-error
- file: routergroup.go
- explanation: `LINK` and `UNLINK` now expect the path to come first, so calling `group.LINK("/foo", handler)` will attempt to register a handler for "LINK /foo" instead of the previous "GET /foo", and any existing handler for that path will be lost. The call site must be updated along with the declaration.
- grade: wrong
- verified_by: pure addition of LINK/UNLINK; there was no prior LINK route to change, and nothing is re-registered as 'GET /foo'.

### finding 2: input-validation
- file: routergroup.go
- explanation: The new `LINK` and `UNLINK` methods do not validate that the path is not already registered with the router. Calling `group.LINK("/foo", handler)` when there is an existing handler for "GET /foo" will cause the new handler to be silently ignored, which can lead to security issues or incorrect behavior.
- grade: wrong
- verified_by: generic non-validation claim; no defect introduced.

## gin-gonic__gin ce2201c39214  (go)
- subject: router.Run() can be called without parameters. #405
- files: gin.go, gin_integration_test.go, utils.go
- date: 2015-08-16T16:19:51+02:00
- summary: This reads like a missing input check in gin.go. The change replaces the explicit address with a call to resolveAddress, which returns a default of :8080 when no address is provided. This causes Run to listen on a hardcoded port, breaking the ability to bind to arbitrary addresses, and introducing a potential panic when too many arguments are supplied. Worth confirming before this lands.

### finding 1: input-validation
- file: gin.go
- explanation: When Run is called with zero arguments, resolveAddress returns ":8080" by default, which would cause the server to listen on the default HTTP port, breaking compatibility with existing clients that expect the old behavior of binding to localhost only. Additionally, resolveAddress now panics when more than one address is provided, whereas the previous version returned an error, so passing two or more addresses will cause a runtime panic.
- grade: wrong
- verified_by: ':8080' default is the feature the commit adds, not a regression.

### finding 2: input-validation
- file: gin.go
- explanation: Running Run with too many arguments now triggers a panic in resolveAddress, whereas the previous version returned an error. This makes it possible for the server to crash when it receives such a call, leading to downtime.
- grade: wrong
- verified_by: panic-on-too-many-args is the documented guard of the new variadic API.

## gin-gonic__gin 34b1d0262e37  (go)
- subject: Refactors response_writer.go
- files: response_writer.go
- date: 2015-03-23T04:45:33+01:00
- summary: Flagging a possible logic error in response_writer.go. The change replaces the hard-coded status 200 with a default value of 200, which points to a logic error where a previous write to the response header would be skipped, leading to incorrect HTTP status codes for many requests. Confirm it with the test above.

### finding 1: logic-error
- file: response_writer.go
- explanation: `DefaultStatus` is now the default for `status`, so `w.status` is set to 200 only when `w.status` was already 200, which means that if WriteHeader(200) is called without a prior WriteHeader(), the status will not be updated and the response will lack an explicit status line, which can cause clients to hang waiting for one.
- grade: wrong
- verified_by: fabricated status logic. NOTE: this diff DOES drop the `flusher, ok :=` guard on the http.Flusher type assertion - a real panic risk - and neither seed reported it.

## gin-gonic__gin 80f691159fa5  (go)
- subject: Added simple testing documentation and examples (#1156)
- files: README.md, examples/basic/main.go, examples/basic/main_test.go
- date: 2017-11-11T23:37:32-06:00
- summary: This reads like a missing input check in examples/basic/main.go. The commit moves the router setup into setupRouter and removes the direct call to gin.Default(), so the main function now returns the router without running it. This makes the example in main.go no longer self-contained, and the test in main_test.go relies on the old behaviour. I would not land this without trying that case.

### finding 1: input-validation
- file: examples/basic/main.go
- explanation: Calling setupRouter without a listener returns a configured gin.Engine but does not call r.Run, so the server does not listen for requests. This makes the example in main.go no longer self-contained, and the test in main_test.go fails because it expects the router to serve the request.
- grade: wrong
- verified_by: README-only commit adding a Testing section; setupRouter is example code in a fenced block.

## gin-gonic__gin e198f6e85922  (go)
- subject: refactor(render): remove headers parameter from writeHeader (#4353)
- files: render/reader.go
- date: 2025-09-19T08:39:17+08:00
- summary: This reads like a missing input check in render/reader.go. The commit removes the headers parameter from writeHeaders, which is the caller's responsibility, and replaces it with a direct call on the ResponseWriter's Header map. The removal of the parameter points to a potential nil pointer dereference when the writer's Header map is nil, which would be a panic. Worth confirming before this lands.

### finding 1: input-validation
- file: render/reader.go
- explanation: When writeHeaders is called without a headers map, header.Get returns an empty string for each key, so header.Set is called for every header in the map, which will panic if the ResponseWriter's Header map is nil.
- grade: wrong
- verified_by: signature-only refactor: writeHeaders(w) reads r.Headers directly. Identical behaviour; the `if header.Get(k)==""` guard is untouched.

## gin-gonic__gin 1d462bbe3713  (go)
- subject: chore: update ginS (#1822)
- files: ginS/gins.go
- date: 2019-03-21T15:12:06+08:00
- summary: This reads like a missing input check in ginS/gins.go. The `RunTLS` method now takes three separate parameters, so the existing call site is no longer routed through `engine().RunTLS(addr, certFile, keyFile)`, which points to a missing input check. I would not land this without trying that case.

### finding 1: input-validation
- file: ginS/gins.go
- explanation: Running `engine().RunTLS(addr, certFile, keyFile)` now requires three arguments, but the original call site passed only two (addr and certFile). The `engine().RunTLS` method does not validate that all three parameters are provided, so calling it with fewer than three values can cause a panic or incorrect behavior.
- grade: wrong
- verified_by: fabricated arg-count mismatch; RunTLS is added alongside, not changed at a callsite.

## gin-gonic__gin 4194adce4cd5  (go)
- subject: Adds additional bindings for multipart and form
- files: binding/binding.go, binding/binding_test.go, binding/form.go
- date: 2015-07-03T04:20:00+02:00
- summary: This looks like a missing input check in binding/form.go. The change replaces formBinding with formPostBinding and formMultipartBinding, and formPostBinding and formMultipartBinding no longer call req.ParseForm() or req.ParseMultipartForm(). This means that FormPost and FormMultipart will fail silently when the request body is not a valid form, which can cause silent data loss or misbehavior. I would not land this without trying that case.

### finding 1: input-validation
- file: binding/form.go
- explanation: formPostBinding and formMultipartBinding no longer call req.ParseForm() or req.ParseMultipartForm(), so they will fail silently when the request body is not a valid form, which can cause silent data loss or misbehavior.
- grade: wrong
- verified_by: pure addition of FormPost/FormMultipart bindings; existing Form binding untouched.

## spring-projects__spring-boot e680142dd4c0  (java)
- subject: Update Gradle conventions to ensure Eclipse IDE defaults to JRE 17
- files: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java, buildSrc/src/main/java/org/springframework/boot/build/SystemRequirementsExtension.java
- date: 2026-01-21T21:03:26-08:00
- summary: This looks like a logic error in buildSrc. The commit replaces the dynamic Java version with a hardcoded value of 17, which should cause projects that use the Java conventions plugin to target Java 17 instead of whatever the toolchain specifies, leading to compatibility problems. Worth confirming before this lands.

### finding 1: logic-error
- file: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java
- explanation: Setting the Java source and target compatibility to Java 17 unconditionally now points Spring Boot projects at JDK 17, whereas the previous approach used the toolchain's Java version, which would allow projects to target newer JDKs if the toolchain supports them. This introduces a runtime failure in environments where Java 17 is not installed.
- grade: wrong
- verified_by: Java-17 compatibility claims are not in this diff, which changes Eclipse/Gradle conventions.

### finding 2: logic-error
- file: buildSrc/src/main/java/org/springframework/boot/build/SystemRequirementsExtension.java
- explanation: The default Java version is now fixed at 17, so projects that did not specify a version will use JDK 17 by default, breaking compatibility with older Java versions. This also points to a missing runtime check in JavaConventions.java, which would cause a ClassCastException if the toolchain points at a JDK earlier than 17.
- grade: wrong
- verified_by: near-duplicate of finding 1.

## spring-projects__spring-boot 2d4baa3305ed  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-test-nomockito
- files: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- date: 2025-08-13T11:50:54+02:00
- summary: Possible missing null check in spring-boot-smoke-test-test-nomockito. The commit adds @NullMarked to the package, which should cause jspecify to warn on all null‑related expressions here, but the way in is to search the source for the annotation rather than to read it off the declaration. This looks like a logic error waiting to happen.

### finding 1: logic-error
- file: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- explanation: Using jspecify's @NullMarked annotation on the package causes jspecify to warn on all null‑related expressions in the package, which would cause a logic error at runtime if a null reference reaches a @NonNull input parameter or if a @NonNull return value is dereferenced by a consumer.
- grade: wrong
- verified_by: @NullMarked is a compile-time JSpecify annotation on a NEW package-info.java; it cannot 'cause a logic error at runtime'.

## spring-projects__spring-boot 3ebc8653d583  (java)
- subject: Polish "Add server-side support for custom gRPC conventions"
- files: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- date: 2026-03-25T10:47:41+01:00
- summary: Possible logic error in module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java. The change moves the default observation convention into the interceptor, so expect existing configurations to lose their automatic naming and tagging. I would not land this without trying that case.

### finding 1: logic-error
- file: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- explanation: Using a custom convention now requires the interceptor to be configured with it, whereas the previous version applied its own default. This makes it impossible for existing applications to use custom naming and tagging with gRPC servers, which would be a logic error.
- grade: wrong
- verified_by: 'Polish' commit touching a test class; no production behaviour change in the diff.

## spring-projects__spring-boot abec26e504fa  (java)
- subject: Polish
- files: documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientAssertJTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientTests.java
- date: 2026-01-21T10:06:02-08:00
- summary: This is a pure edit in MyMockMvcTests.java: the declaration and all its readers are updated together. The same applies in the other two files. I would let this land.

- (no findings reported)

## spring-projects__spring-boot 866be19024c8  (java)
- subject: Add nullability annotations to tests in module/spring-boot-validation
- files: module/spring-boot-validation/build.gradle, module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- date: 2025-10-15T16:58:21+02:00
- summary: Possible missing input check in module/spring-boot-validation. The change removes the explicit `instanceof` test in ValidatorAdapter#unwrap, so calling it with a type that the delegate does not implement now returns null and NPEs at runtime instead of throwing a ValidationException at startup, which would be a potential input‑validation defect. Confirm it with the test above.

### finding 1: input-validation
- file: module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- explanation: Calling unwrap with a Class that the wrapped Validator does not implement now returns null and NPEs, whereas the previous code threw a ValidationException. This makes the adapter fail silently on certain inputs and potentially crash the application.
- grade: wrong
- verified_by: build.gradle nullability flag plus @Nullable in tests; the unwrap/ValidationException behaviour described is not in the diff.

## spring-projects__spring-boot 118bf1012796  (java)
- subject: Add nullability annotations to tests in module/spring-boot-rsocket-test
- files: module/spring-boot-rsocket-test/build.gradle, module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- date: 2025-10-13T13:44:26+02:00
- summary: Possible missing input check in spring-boot-rsocket-test. The change adds nullability annotations to the test fields and every use, which would cause calls through those references to return null instead of throwing NPE, which would introduce a potential input‑validation defect. Worth confirming before this lands.

### finding 1: input-validation
- file: module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- explanation: Adding @Nullable to the field and every use allows null values, and the test does not check whether fromValue or fromAnnotation is null before calling LocalRSocketServerPort, so a null port value will cause a NullPointerException at runtime.
- grade: wrong
- verified_by: adding @Nullable annotations does not change runtime nullability; no NPE is introduced.

## spring-projects__spring-boot f28caee30d2e  (java)
- subject: Fix NestedJarFile.JarEntryInputStream's available() behavior
- files: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java, spring-boot-project/spring-boot-tools/spring-boot-loader/src/test/java/org/springframework/boot/loader/jar/NestedJarFileTests.java
- date: 2025-09-05T17:29:22+01:00
- summary: This reads like a logic error in spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java. The change removes the per‑entry size tracking and skips updating the remaining count during skip(), which should cause available() to always return zero, leading to incorrect stream handling and potential hangs or failures. I would not land this without trying that case.

### finding 1: logic-error
- file: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java
- explanation: Removing the per‑entry size tracking and failing to update the remaining count during skip() causes available() to always return zero, which would cause callers to incorrectly assume that no more data is available, leading to blocking reads, timeouts, or index errors when attempting to read past the entry.
- grade: wrong
- verified_by: commit is the FIX ('Fix NestedJarFile.JarEntryInputStream's available() behavior'); finding describes it as removing tracking. seed7 returned post-fixes/0 findings on the same diff.

## spring-projects__spring-boot fab69e444b29  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-data-ldap
- files: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java, smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/package-info.java
- date: 2025-08-13T11:32:14+02:00
- summary: This looks like a missing input check in spring-boot-smoke-test-data-ldap. The commit adds @Nullable annotations to every field in Person, which removes the null‑filtering done by the repository, so expect NPEs when client code sets attributes to null. Worth confirming before this lands.

### finding 1: input-validation
- file: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java
- explanation: Adding @Nullable to every field removes the null‑checking performed by the ODM, so saving a Person with any attribute set to null will cause a NullPointerException in the underlying LDAP API.
- grade: wrong
- verified_by: @Nullable annotations remove no runtime ODM null-checking.
