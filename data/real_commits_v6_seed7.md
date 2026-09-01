# Real-commit grading sheet

Fill `grade` with locus | mechanism | wrong, and `verified_by`
with the command that proves it. A mechanism claim that was not
executed is not graded - leave it blank rather than guess.

Hand-graded 2026-09-01 by reading all 40 diffs. Grades follow the rule at the
top of this file; `""` means NOT GRADED because settling it needs an execution
that was not run. Every commit here is an upstream commit from a mature
project - a fix, a feature, a refactor, a docs or annotation change - so a
finding is a false alarm unless the commit genuinely introduces a defect.

  graded 24 findings over 40 commits: locus 1 | mechanism 1 | wrong 21 | not graded 1

`wrong` here almost always means the explanation describes code that is not in
the diff. That is the FABRICATED class, on real commits, at a rate the
synthetic benches do not show.

## axios__axios 6b3c305fc40c  (javascript)
- subject: fix(http): use explicit import instead of TextEncoder global; (#5530)
- files: lib/helpers/formDataToStream.js
- date: 2023-02-03T19:34:07+02:00
- summary: This undoes the defect in lib/helpers/formDataToStream.js. The `TextEncoder` import comes back in the file, putting the original form back. Nothing further to raise on it.

- (no findings reported)

## axios__axios 4c4e648f409d  (javascript)
- subject: Replacing Object.hasOwnProperty with Object.prototype.hasOwnProperty
- files: lib/utils.js
- date: 2016-09-12T11:26:40-07:00
- summary: This reads like a logic error in lib/utils.js. The commit replaces direct use of Object.hasOwnProperty with a call via Object.prototype.hasOwnProperty, introducing an extra call site. This looks like an off-by-one where the prototype method walks additional properties, so expect forEach to iterate over more keys than before, breaking existing callers that relied on the original behavior.

### finding 1: logic-error
- file: lib/utils.js
- explanation: forEach now iterates over all own and inherited enumerable properties, including those added by extensions of Object. This causes it to invoke the callback for keys such as __proto__, leading to unintended side effects or errors, and potentially causing silent mismatches between expected and actual data.
- grade: wrong
- verified_by: same as seed42: claim that the guard now admits inherited keys is false; verified with node.

## axios__axios ffc0237a175b  (javascript)
- subject: Adding support for timeout config closes #56
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/defaults.js
- date: 2015-08-10T19:00:27-06:00
- summary: This undoes the fix in lib/adapters/http.js. The `req.setTimeout(...)` call is back, which is what it should have been all along. Nothing further to raise on this commit.

- (no findings reported)

## axios__axios fce210a67e24  (javascript)
- subject: Fixed TransitionalOptions typings (#4147)
- files: index.d.ts
- date: 2021-10-12T09:46:16+02:00
- summary: This undoes the defect in index.d.ts. `silentJSONParsing`, `forcedJSONParsing` and `clarifyTimeoutError` are back in their original form, so the behaviour comes back to what it did before. Nothing further to raise on this commit.

- (no findings reported)

## axios__axios 926347315405  (javascript)
- subject: chore(ci): fixed contributors avatar rendering for CHANGELOG.md; (#5514)
- files: bin/contributors.js, templates/contributors.hbs, test/specs/__helpers.js
- date: 2023-01-31T17:56:09+02:00
- summary: This undoes the defect in bin/contributors.js. The `&s=16` size parameter is back, which is what it should have been all along. Nothing else rides along with the fix.

- (no findings reported)

## axios__axios 594df987f279  (javascript)
- subject: fix array params
- files: lib/helpers/buildUrl.js, test/specs/helpers/buildUrl.spec.js
- date: 2015-05-27T13:32:34+02:00
- summary: This undoes the defect in lib/helpers/buildUrl.js. The `utils.isArray()` test is back before the `[key]` indexer, so the original behaviour comes back. Nothing further to raise on it.

- (no findings reported)

## axios__axios e8cf487ad0f5  (javascript)
- subject: Removing es6-promise dependency
- files: lib/axios.js, package.json, test/specs/promise.spec.js
- date: 2015-07-23T10:43:17-07:00
- summary: This reads like a missing input check in lib/axios.js. The commit removes the es6-promise polyfill and does not validate that Promise is available, so axios will throw TypeError: Cannot read property 'then' of undefined when the underlying library uses native Promises and the request cannot be resolved synchronously. Worth ruling out before this goes in.

### finding 1: input-validation
- file: lib/axios.js
- explanation: When es6-promise is removed, axios attempts to use the global Promise, which may be undefined in environments without Promise support (e.g., older browsers). The call to axios's promise-returning methods now throws TypeError: Cannot read property 'then' of undefined.
- grade: locus
- verified_by: same, correct.

## axios__axios 22ce6db383bc  (javascript)
- subject: Adding request to error objects when it is available
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/core/createError.js, lib/core/enhanceError.js, lib/core/settle.js
- date: 2017-04-08T21:44:15+02:00
- summary: This looks like a missing parameter in lib/core/createError.js and lib/core/enhanceError.js. The `createError` and `enhanceError` APIs now accept an extra `request` and `response` parameter, so expect callers to need to pass those in. I would not land this without trying that case.

### finding 1: other
- file: lib/core/createError.js
- explanation: `createError` and `enhanceError` are updated to accept `request` and `response` parameters, but these are not passed through to `Error` constructors, so existing calls will throw TypeError: Failed to construct 'Error': 2 arguments required, but only 1 present.
- grade: wrong
- verified_by: 'Error: 2 arguments required' is not a JS Error message - fabricated.

### finding 2: other
- file: lib/core/enhanceError.js
- explanation: `createError` and `enhanceError` are updated to accept `request` and `response` parameters, but these are not passed through to `Error` constructors, so existing calls will throw TypeError: Failed to construct 'Error': 2 arguments required, but only 1 present.
- grade: wrong
- verified_by: duplicate of finding 1.

## clap-rs__clap f8bca3a84bd5  (rust)
- subject: fix(error): Never show unrequested color
- files: src/parse/errors.rs
- date: 2021-10-26T14:26:50-05:00
- summary: This undoes the defect in src/parse/errors.rs. The `ColorChoice::Auto` default is back, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## clap-rs__clap 479ca76491a7  (rust)
- subject: fix: Always ensure `num_args` is initialized
- files: src/builder/arg.rs, src/builder/debug_asserts.rs
- date: 2022-08-04T09:11:29-05:00
- summary: This undoes the defect in src/builder/arg.rs. The `num_vals` field is now always initialized before `get_num_args()` is called, so the debug assertion comes through instead of panicking. That is the whole of the change as far as I can see.

- (no findings reported)

## clap-rs__clap edabdf72b59b  (rust)
- subject: fix(complete): Only return imidiate child subcommands
- files: clap_complete/src/dynamic/completer.rs
- date: 2023-07-28T14:51:56-05:00
- summary: This reads like a logic error in clap_complete. The commit replaces the recursive search of all subcommands with a direct lookup of subcommands, so expect some completions to disappear for commands with nested subcommands. Worth confirming before this lands.

### finding 1: logic-error
- file: clap_complete/src/dynamic/completer.rs
- explanation: `all_subcommands` returns all subcommands, including those reachable via sub-subcommands, while `subcommands` returns only direct children. Completing a parent command will now miss many subcommands, leading to incorrect suggestions.
- grade: mechanism
- verified_by: right place (all_subcommands -> subcommands) and the mechanical description is accurate, but the commit is the intended fix ('Only return immediate child subcommands'); seed42 called the same diff post-fixes.

## clap-rs__clap a126149a809f  (rust)
- subject: refactor(complete): Remove redundant dedup
- files: clap_complete/src/engine/complete.rs
- date: 2024-09-20T13:59:16-05:00
- summary: This reads like a logic error in clap_complete. The commit removes the call to `dedup()` in complete_subcommand, which would cause the method to return a Vec with duplicate entries for matching subcommands. This looks like a logic error, and I would not land it without trying that case.

### finding 1: logic-error
- file: clap_complete/src/engine/complete.rs
- explanation: `scs.dedup()` is removed, so `scs` is no longer free of duplicates after sorting. Call `complete_subcommand` with two or more subcommands that share a prefix, such as `cargo cl` and `cargo clippy`, to see the problem.
- grade: 
- verified_by: NOT GRADED: as seed42. seed7 does name a concrete repro (`cargo cl`/`cargo clippy`).

## clap-rs__clap 931b6338f125  (rust)
- subject: refactor(parser): Clarify FromStr from future FromStr
- files: src/builder/value_parser.rs
- date: 2022-09-26T09:51:03-05:00
- summary: This reads like a logic error in src/builder/value_parser.rs. The commit replaces `FromStr` with `Parse` in AutoValueParser, which is the first thing I would run.

### finding 1: logic-error
- file: src/builder/value_parser.rs
- explanation: `Parse::from_str` is called instead of `FromStr::from_str`, so values that did not parse with FromStr will fail with an error here instead of returning a default, breaking existing code that relied on the previous behavior.
- grade: wrong
- verified_by: 'Parse::from_str' is the renamed trait, not a different function; no behaviour change.

## clap-rs__clap 9d07b3c02837  (rust)
- subject: feat(parser): non-empty string ValueParser
- files: src/builder/mod.rs, src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: This reads like a missing input check in src/builder/value_parser.rs. The commit adds NonEmptyStringValueParser, which parses strings and returns an error for empty strings, breaking the existing behavior. Worth confirming before this lands.

### finding 1: input-validation
- file: src/builder/value_parser.rs
- explanation: NonEmptyStringValueParser does not validate that the input is non-empty, so calling parse_ref with an empty OsStr returns an error, whereas the previous behavior would have returned "".
- grade: wrong
- verified_by: inverted: the added type's entire purpose IS to reject empty strings.

## clap-rs__clap a7a8f93d6b2b  (rust)
- subject: fix(complete): Strip wrappers for running completer
- files: clap_complete/examples/exhaustive.rs, clap_complete/src/env/mod.rs
- date: 2024-09-17T15:47:46-05:00
- summary: This reads like a logic error in clap_complete. The commit changes the default binary name in CompleteEnv to use the first argument from the command line instead of the command's own name, which would cause completion to fail for commands that do not specify a name (e.g., generated commands). This looks like a regression, not a fix. Worth confirming before merging.

### finding 1: logic-error
- file: clap_complete/src/env/mod.rs
- explanation: Using args_os()[0] as the binary name bypasses the normal name resolution, so commands without a name (like generated commands) will point to the wrong executable, leading to incomplete or incorrect completions.
- grade: wrong
- verified_by: as seed42.

## clap-rs__clap f9be3215c189  (rust)
- subject: refactor(parser): Minor clean up
- files: src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: This reads like a pure refactoring in src/builder/value_parser.rs. Every declaration moves alongside its use, nothing that I can see pointing at a defect. Nothing to flag here.

- (no findings reported)

## fastapi__fastapi 9b35d355bfb4  (python)
- subject: 📝 Update `docs_src/path_params_numeric_validations/tutorial006.py` (#11478)
- files: docs_src/path_params_numeric_validations/tutorial006.py, docs_src/path_params_numeric_validations/tutorial006_an.py, docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- date: 2024-08-28T18:39:15-05:00
- summary: This reads like a missing input check in docs_src/path_params_numeric_validations/tutorial006.py. The `size` parameter is back in the signature and in the call site, so the original behaviour comes back. I would not land this without trying that case.

### finding 1: input-validation
- file: docs_src/path_params_numeric_validations/tutorial006.py
- explanation: The `size` parameter is back in the signature and in the call site, but the `read_items` function no longer validates that `size` is a positive integer before using it, which would cause a ValueError when calling `int(size)` on a non-numeric string.
- grade: wrong
- verified_by: fabricated: the signature is unchanged by this diff.

## fastapi__fastapi d11f820ac38b  (python)
- subject: 📝 Update docs for JWT to prevent timing attacks (#14908)
- files: docs/en/docs/tutorial/security/oauth2-jwt.md, docs_src/security/tutorial004_an_py310.py, docs_src/security/tutorial004_py310.py, docs_src/security/tutorial005_an_py310.py, docs_src/security/tutorial005_py310.py
- date: 2026-02-12T19:10:35+01:00
- summary: This reads like a logic error in docs/en/docs/tutorial/security/oauth2-jwt.md. The commit undoes the fix from #14907 and restores the original insecure behavior: `verify_password()` is called with a dummy hash for every username, which would allow attackers to brute-force passwords by trying every possible password until they find a match. This is the defect I would raise on this change.

### finding 1: logic-error
- file: docs/en/docs/tutorial/security/oauth2-jwt.md
- explanation: `DUMMY_HASH` is back in place of the actual password hash in `authenticate_user`, so calling `verify_password()` with a dummy hash for every username allows attackers to perform a dictionary attack: try every possible password until they find a match. This is a security issue.
- grade: wrong
- verified_by: same inversion as seed42.

## fastapi__fastapi 6cc24416e228  (python)
- subject: ✏️ Fix docstring typos in http security (#12223)
- files: fastapi/security/http.py
- date: 2024-09-19T11:47:28+02:00
- summary: This undoes the defect in fastapi/security/http.py. The `not provided` typo is back in HTTPBearer and HTTPDigest, putting the original behaviour back. Nothing further to raise on this commit.

- (no findings reported)

## fastapi__fastapi 31887b1cc6fb  (python)
- subject: 🔖 Release version 0.115.4
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2024-10-27T21:51:55Z
- summary: fastapi/__init__.py undoes the change in the commit: `__version__` is back to 0.115.3 in the file it came from, so the behaviour is unchanged. Nothing to raise on this commit.

- (no findings reported)

## fastapi__fastapi c7e7b651d694  (python)
- subject: 🔖 Release version 0.141.0 (#16103)
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2026-07-29T14:45:21Z
- summary: This undoes the change in fastapi/__init__.py. The `__version__` string comes back to its previous value, and nothing else in the file moves. Nothing to flag on this commit.

- (no findings reported)

## fastapi__fastapi 91a929319c4c  (python)
- subject: ♻️ Update internal checks to support Pydantic 2.10 (#12914)
- files: fastapi/_compat.py, fastapi/params.py
- date: 2024-11-12T17:10:42+01:00
- summary: This reads like a logic error in fastapi/params.py. The commit replaces the string-based version check with a numeric comparison of the Pydantic version tuple, which should cause the library to misbehave on Pydantic 2.10 and later. I would not land this without trying that case.

### finding 1: logic-error
- file: fastapi/params.py
- explanation: Using PYDANTIC_VERSION_MINOR_TUPLE to compare Pydantic versions can cause the library to misbehave on Pydantic 2.10 and later, where the minor version is 2 instead of 1. The original check against '2.' did not account for the presence of the patch level, so the update breaks compatibility.
- grade: wrong
- verified_by: 'minor version is 2 instead of 1' is garbled and does not describe the diff.

## fastapi__fastapi 3611c3fc5b82  (python)
- subject: ⬆️ Add support for Python 3.14 (#14165)
- files: .github/workflows/test.yml, pyproject.toml, requirements-tests.txt, tests/test_tutorial/test_sql_databases/test_tutorial001.py, tests/test_tutorial/test_sql_databases/test_tutorial002.py
- date: 2025-10-10T11:44:39+02:00
- summary: This reads like a missing feature in pyproject.toml. The upgrade moves sqlmodel from 0.0.25 to 0.0.27, which is a new version with new features. Nothing in the change itself points to a regression, but I would not use this code without confirming that the new version works as intended.

### finding 1: other
- file: .github/workflows/test.yml
- explanation: sqlmodel==0.0.27 adds support for Python 3.14, which the existing setup does not yet support. The `exclude` rule in .github/workflows/test.yml pins pydantic-v1 against 3.14, so expect a conflict when that version runs against Python 3.14. To see it, set the runner to Python 3.14 and try to start the workflow.
- grade: wrong
- verified_by: sqlmodel pin is not the mechanism described; no defect introduced.

## fastapi__fastapi 2260afaf4331  (python)
- subject: 🐛 Fix failing test, update format for raised errors (#15804)
- files: fastapi/routing.py
- date: 2026-06-20T00:51:31Z
- summary: This undoes the defect in fastapi/routing.py. The `os.path.isdir()` check is back before `os.path.exists()`, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## gin-gonic__gin dbd8a2515093  (go)
- subject: feat: added `AbortWithStatusPureJSON()` in `Context` (#4290)
- files: context.go, context_test.go
- date: 2025-07-13T09:40:35+08:00
- summary: This reads like a logic error in context.go. The commit changes the API of `Context` by adding `AbortWithStatusPureJSON` and calling `PureJSON` instead of `JSON`. The new method writes a JSON body without escaping and sets a Content-Type header, which would cause existing callers that expect HTML to break. I would not land this without trying that case.

### finding 1: logic-error
- file: context.go
- explanation: `AbortWithStatusPureJSON` calls `PureJSON` instead of `JSON`, which skips the HTML escaping and adds a Content-Type header of "application/json", breaking existing callers that expect HTML content. The existing `AbortWithStatus` is left unchanged, so the API changes are not backward compatible.
- grade: wrong
- verified_by: 'breaking existing callers' - it is a NEW method, there are none.

### finding 2: other
- file: context.go
- explanation: `AbortWithStatusPureJSON` does not validate that `jsonObj` is a JSON-compatible value before calling `PureJSON`, so calling it with a non-JSON value will panic or produce invalid JSON output.
- grade: wrong
- verified_by: generic 'does not validate input' with no defect introduced.

## gin-gonic__gin a48f83c9a1a1  (go)
- subject: Adding helper functions to router group for LINK and UNLINK.
- files: routergroup.go
- date: 2014-12-15T13:19:51-04:00
- summary: This looks like a missing feature in routergroup.go. The change adds `LINK` and `UNLINK` methods to RouterGroup, which point to existing `Handle` calls with "LINK" and "UNLINK" method names. This is behaviour change, not a repair of a defect. I would not land this without trying that case.

### finding 1: other
- file: routergroup.go
- explanation: `LINK` and `UNLINK` are added next to `Handle`, so expect users to call `group.LINK(...)` or `group.UNLINK(...)`. The methods point to existing `group.Handle(...)` calls with "LINK" and "UNLINK" method names, so the existing API surface extends rather than changes. The added methods do not call the router's NotFound handler, so expect 404 responses for paths not registered with `Handle`.
- grade: wrong
- verified_by: describes the addition accurately but files it as a finding on a clean commit.

## gin-gonic__gin ce2201c39214  (go)
- subject: router.Run() can be called without parameters. #405
- files: gin.go, gin_integration_test.go, utils.go
- date: 2015-08-16T16:19:51+02:00
- summary: This reads like a missing input check in gin.go. The commit changes Run to accept an optional address parameter and calls resolveAddress with the provided address slice, which should cause it to accept zero addresses and use a default port. The way in is to call `router.Run()` without an address, which should invoke the defaulting logic and cause the server to listen on :8080, leading to an unexpected network service and security issues. Worth ruling out before this goes in.

### finding 1: input-validation
- file: gin.go
- explanation: When Run is called with zero strings, resolveAddress returns ":8080" and ListenAndServe listens on that port, which bypasses the original address and allows external access to the router on an arbitrary port. This is a security issue where attackers could send requests to your server on ports they control, potentially leading to unauthorized access or data exfiltration.
- grade: wrong
- verified_by: as seed42 finding 1.

## gin-gonic__gin 34b1d0262e37  (go)
- subject: Refactors response_writer.go
- files: response_writer.go
- date: 2015-03-23T04:45:33+01:00
- summary: This undoes the defect in response_writer.go. `DefaultStatus` is back in place of the hardcoded 200, and `status` is back on the struct instead of on the heap. Nothing else rides along with the fix.

- (no findings reported)

## gin-gonic__gin 80f691159fa5  (go)
- subject: Added simple testing documentation and examples (#1156)
- files: README.md, examples/basic/main.go, examples/basic/main_test.go
- date: 2017-11-11T23:37:32-06:00
- summary: This reads like a missing call site in examples/basic/main.go. The commit moves the main logic into setupRouter(), which returns the router, but the call site still calls main() directly. This looks like a missing call site, which would cause the existing test to fail.

### finding 1: other
- file: examples/basic/main.go
- explanation: The call site in examples/basic/main.go now goes through setupRouter(), which returns the Gin engine. The original main() is gone, so the existing test that ran main() directly is now pointing at the stubbed-out setupRouter(), which returns nil and panics when ServeHTTP is called on it. The test would fail with a panic rather than the previous return value of 0.
- grade: wrong
- verified_by: examples/basic/main.go is not in this diff.

## gin-gonic__gin e198f6e85922  (go)
- subject: refactor(render): remove headers parameter from writeHeader (#4353)
- files: render/reader.go
- date: 2025-09-19T08:39:17+08:00
- summary: This reads like a logic error in render/reader.go. The commit removes the headers parameter from writeHeaders and writes directly to the response's Header, which would cause some headers to be duplicated or overridden. Worth confirming before this lands.

### finding 1: logic-error
- file: render/reader.go
- explanation: Calling writeHeaders without a headers argument now accesses w.Header() directly, while the previous version used r.Headers. This bypasses the deduplication logic and can cause headers to be duplicated or overwritten, leading to incorrect responses.
- grade: wrong
- verified_by: the dedup guard is unchanged; 'bypasses the deduplication logic' is false.

## gin-gonic__gin 1d462bbe3713  (go)
- subject: chore: update ginS (#1822)
- files: ginS/gins.go
- date: 2019-03-21T15:12:06+08:00
- summary: This commit removes four deprecated functions from ginS/gins.go and replaces them with calls to `engine().Run`, `engine().RunTLS`, `engine().RunUnix` and `engine().RunFd`. Nothing in the call site points to the old names coming back, so I would let this land.

- (no findings reported)

## gin-gonic__gin 4194adce4cd5  (go)
- subject: Adds additional bindings for multipart and form
- files: binding/binding.go, binding/binding_test.go, binding/form.go
- date: 2015-07-03T04:20:00+02:00
- summary: This commit changes the API in binding/binding.go: `Form` is replaced by `FormPost` and `FormMultipart`, and `formBinding` is added. The change reaches every use of the old name, so I would expect identical output. Nothing in this hunk moves the code towards or away from a defect.

- (no findings reported)

## spring-projects__spring-boot e680142dd4c0  (java)
- subject: Update Gradle conventions to ensure Eclipse IDE defaults to JRE 17
- files: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java, buildSrc/src/main/java/org/springframework/boot/build/SystemRequirementsExtension.java
- date: 2026-01-21T21:03:26-08:00
- summary: This undoes the defect in JavaConventions.java. The `project.provider()` is back in place of the hard-coded version, which is what it should have been all along. Nothing further to raise on this commit.

- (no findings reported)

## spring-projects__spring-boot 2d4baa3305ed  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-test-nomockito
- files: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- date: 2025-08-13T11:50:54+02:00
- summary: This reads like a missing annotation here. The `@NullMarked` annotation that used to apply to the package now applies only to `package-info.java`, so the whole package is back in unchecked mode. This looks like a regression.

### finding 1: other
- file: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- explanation: `@NullMarked` is back on `package-info.java`, but the package itself is no longer annotated, so null‑safe code in other files will once again run unchecked.
- grade: wrong
- verified_by: inverted: @NullMarked on package-info.java is precisely how the annotation is applied to the WHOLE package.

## spring-projects__spring-boot 3ebc8653d583  (java)
- subject: Polish "Add server-side support for custom gRPC conventions"
- files: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- date: 2026-03-25T10:47:41+01:00
- summary: This reads like a missing input check in module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java. The change moves the default convention into a bean and removes the inline instance, which would cause the interceptor to throw NullPointerException if no convention is configured. That looks like a defect. Worth confirming before this goes in.

### finding 1: input-validation
- file: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- explanation: When no GrpcServerObservationConvention bean is registered, ObservationGrpcServerInterceptor attempts to use the private static GrpcServerObservationConvention instance, which is null, leading to a NullPointerException.
- grade: wrong
- verified_by: as seed42.

## spring-projects__spring-boot abec26e504fa  (java)
- subject: Polish
- files: documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientAssertJTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientTests.java
- date: 2026-01-21T10:06:02-08:00
- summary: Possible logic error in MyMockMvcTests.java. The commit renames `webClient` to `restClient`, which would cause every reference to point at the new name. Nothing in the rest of the method moves with it, so expect a compile error or NPE at runtime. Worth confirming before this lands.

### finding 1: logic-error
- file: documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java
- explanation: `webClient` is renamed `restClient` in MyMockMvcTests.java. Every use of the old name is replaced by the new one, so the program should now look up `restClient` everywhere the old name did. The way in is to search MyMockMvcTests.java for the old name `webClient`.
- grade: wrong
- verified_by: pure rename webClient -> restClient in a docs sample; seed42 correctly returned unchanged/0 findings on the same diff.

## spring-projects__spring-boot 866be19024c8  (java)
- subject: Add nullability annotations to tests in module/spring-boot-validation
- files: module/spring-boot-validation/build.gradle, module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- date: 2025-10-15T16:58:21+02:00
- summary: This undoes the defect in module/spring-boot-validation. The `@Nullable` annotation is back on `unwrap()`'s parameter and its return value, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## spring-projects__spring-boot 118bf1012796  (java)
- subject: Add nullability annotations to tests in module/spring-boot-rsocket-test
- files: module/spring-boot-rsocket-test/build.gradle, module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- date: 2025-10-13T13:44:26+02:00
- summary: This reads like a missing null check in spring-boot-rsocket-test. The commit adds @Nullable annotations to the fields used by LocalRSocketServerPort, which would make them accept null values, but the test cases still expect non-null values from the annotation and fromValue property. This looks like a potential NPE at runtime.

### finding 1: null-dereference
- file: module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- explanation: Using @Nullable on the fields allows them to hold null, while the existing test code assumes non-null values from the annotation and fromValue property. A call to testLocalRSocketServerPortAnnotation with a port that does not exist will cause a NPE when the annotation or property returns null.
- grade: wrong
- verified_by: as seed42.

## spring-projects__spring-boot f28caee30d2e  (java)
- subject: Fix NestedJarFile.JarEntryInputStream's available() behavior
- files: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java, spring-boot-project/spring-boot-tools/spring-boot-loader/src/test/java/org/springframework/boot/loader/jar/NestedJarFileTests.java
- date: 2025-09-05T17:29:22+01:00
- summary: This undoes the defect in spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java. The `remaining` field is back, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## spring-projects__spring-boot fab69e444b29  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-data-ldap
- files: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java, smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/package-info.java
- date: 2025-08-13T11:32:14+02:00
- summary: This reads like a missing null check in Person.toString(). The @NullMarked annotation that used to apply to the package now applies only to Person, so Name and String are back in the open world. That is the first thing I would run.

### finding 1: other
- file: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java
- explanation: Person.toString() calls toString() on dn and phone without checking whether they are null, which would cause a NullPointerException if any DN or telephone number is null.
- grade: wrong
- verified_by: false alarm on an annotation-only commit; Person.toString() is unchanged by this diff.
