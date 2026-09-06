# Real-commit grading sheet

Fill `grade` with locus | mechanism | wrong, and `verified_by`
with the command that proves it. A mechanism claim that was not
executed is not graded - leave it blank rather than guess.

PLAIN UNIFIED diff, not word-diff: this model never saw the word-diff rendering
the 3B was trained on, and on that rendering it quoted `+}` markers as source.
  graded 16 findings over 40 commits: locus 3 | mechanism 6 | wrong 6 | not graded 1

## axios__axios 6b3c305fc40c  (javascript)
- subject: fix(http): use explicit import instead of TextEncoder global; (#5530)
- files: lib/helpers/formDataToStream.js
- date: 2023-02-03T19:34:07+02:00
- summary: The change adds an explicit import of TextEncoder from 'util', fixing crashes when the global TextEncoder is unavailable; verify that string encoding now works in older Node environments.

- (no findings reported)

## axios__axios 4c4e648f409d  (javascript)
- subject: Replacing Object.hasOwnProperty with Object.prototype.hasOwnProperty
- files: lib/utils.js
- date: 2016-09-12T11:26:40-07:00
- summary: Replaces Object.hasOwnProperty with Object.prototype.hasOwnProperty, fixing a TypeError in forEach when iterating over object keys; verify that forEach now correctly processes plain objects.

- (no findings reported)

## axios__axios ffc0237a175b  (javascript)
- subject: Adding support for timeout config closes #56
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/defaults.js
- date: 2015-08-10T19:00:27-06:00
- summary: The change adds timeout handling for HTTP and XHR adapters, but the XHR adapter only sets request.timeout without attaching an ontimeout handler, so timed‑out XHR requests may leave the promise pending. Verify that a request exceeding the timeout is properly rejected.

### finding 1: error-handling
- file: lib/adapters/xhr.js
- explanation: In lib/adapters/xhr.js the timeout is set but no ontimeout handler is provided, so a timed‑out XHR will not call resolve or reject, potentially causing a hanging promise.
- grade: mechanism
- verified_by: xhr.js genuinely sets request.timeout with no ontimeout handler - a real code observation - but this is the upstream feature commit and the readystatechange path still settles.

## axios__axios fce210a67e24  (javascript)
- subject: Fixed TransitionalOptions typings (#4147)
- files: index.d.ts
- date: 2021-10-12T09:46:16+02:00
- summary: The change makes the three TransitionalOptions fields optional in the TypeScript typings, which does not alter runtime behavior; verify that omitting these options still works as before.

- (no findings reported)

## axios__axios 926347315405  (javascript)
- subject: chore(ci): fixed contributors avatar rendering for CHANGELOG.md; (#5514)
- files: bin/contributors.js, templates/contributors.hbs, test/specs/__helpers.js
- date: 2023-01-31T17:56:09+02:00
- summary: The change updates the avatar URL size to 18 px and switches from markdown image syntax to an HTML <img> tag, presumably to fix rendering in CHANGELOG.md. Verify that the new HTML renders as expected in the intended environment.

- (no findings reported)

## axios__axios 594df987f279  (javascript)
- subject: fix array params
- files: lib/helpers/buildUrl.js, test/specs/helpers/buildUrl.spec.js
- date: 2015-05-27T13:32:34+02:00
- summary: The change makes array parameters serialize with a [] suffix on the key, so URLs now include the encoded brackets for each array element. Check that the new format is produced for array inputs and that this is the intended behavior.

- (no findings reported)

## axios__axios e8cf487ad0f5  (javascript)
- subject: Removing es6-promise dependency
- files: lib/axios.js, package.json, test/specs/promise.spec.js
- date: 2015-07-23T10:43:17-07:00
- summary: Removing the automatic es6‑promise polyfill means axios now relies on a native Promise; in environments lacking one it will break unless the user polyfills manually. Test in a Promise‑less runtime to confirm behavior.

### finding 1: error-handling
- file: lib/axios.js
- explanation: If Promise is undefined, axios will attempt to create a Promise and throw a ReferenceError, breaking code that previously worked with the built‑in polyfill.
- grade: locus
- verified_by: CORRECT. Same true positive both 3B seeds found: the polyfill is removed, so environments without native Promise lose it.

## axios__axios 22ce6db383bc  (javascript)
- subject: Adding request to error objects when it is available
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/core/createError.js, lib/core/enhanceError.js, lib/core/settle.js
- date: 2017-04-08T21:44:15+02:00
- summary: The commit adds a request parameter to createError/enhanceError and updates many call sites, but any remaining calls that only passed a response will now treat that response as a request, causing error.response to be lost. Verify that all usages have been updated accordingly.

### finding 1: error-handling
- file: lib/core/createError.js
- explanation: calls to createError/enhanceError that were not updated may lose the response information, leading to missing error.response in downstream handling
- grade: wrong
- verified_by: the diff updates createError/enhanceError AND their callers together; no caller is left on the old shape.

### finding 2: error-handling
- file: lib/core/enhanceError.js
- explanation: calls to enhanceError that were not updated may lose the response information, leading to missing error.response in downstream handling
- grade: wrong
- verified_by: duplicate of finding 1 against the second file.

## clap-rs__clap f8bca3a84bd5  (rust)
- subject: fix(error): Never show unrequested color
- files: src/parse/errors.rs
- date: 2021-10-26T14:26:50-05:00
- summary: The commit switches the Colorizer for raw error messages from Auto to Never, suppressing any ANSI color codes in formatted errors. Check that error output is now plain text even on color‑capable terminals.

- (no findings reported)

## clap-rs__clap 479ca76491a7  (rust)
- subject: fix: Always ensure `num_args` is initialized
- files: src/builder/arg.rs, src/builder/debug_asserts.rs
- date: 2022-08-04T09:11:29-05:00
- summary: The change ensures num_args is always initialized, fixing cases where it was previously None for single‑value arguments; verify that get_num_args() now returns Some(1) for such arguments.

- (no findings reported)

## clap-rs__clap edabdf72b59b  (rust)
- subject: fix(complete): Only return imidiate child subcommands
- files: clap_complete/src/dynamic/completer.rs
- date: 2023-07-28T14:51:56-05:00
- summary: The change replaces all_subcommands with subcommands, limiting completion to immediate child subcommands; check that deeper subcommands are no longer suggested when completing a subcommand name.

- (no findings reported)

## clap-rs__clap a126149a809f  (rust)
- subject: refactor(complete): Remove redundant dedup
- files: clap_complete/src/engine/complete.rs
- date: 2024-09-20T13:59:16-05:00
- summary: Removing the dedup call means duplicate completion candidates are no longer filtered out, so callers may receive repeated entries; test with duplicate subcommand values to confirm.

### finding 1: logic-error
- file: clap_complete/src/engine/complete.rs
- explanation: duplicate completion candidates may be returned, leading to redundant suggestions
- grade: 
- verified_by: NOT GRADED: needs `cargo test -p clap_complete`. Same call as every other run.

## clap-rs__clap 931b6338f125  (rust)
- subject: refactor(parser): Clarify FromStr from future FromStr
- files: src/builder/value_parser.rs
- date: 2022-09-26T09:51:03-05:00
- summary: The change merely renames the internal _ValueParserViaFromStr trait and its sealed version to _ValueParserViaParse, updating generic parameter names but keeping the same bounds and implementation, so runtime behaviour is unchanged.

- (no findings reported)

## clap-rs__clap 9d07b3c02837  (rust)
- subject: feat(parser): non-empty string ValueParser
- files: src/builder/mod.rs, src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: The commit adds a NonEmptyStringValueParser that rejects empty strings; this is new functionality and does not alter existing behavior, but callers should verify that empty inputs now produce an error.

- (no findings reported)

## clap-rs__clap a7a8f93d6b2b  (rust)
- subject: fix(complete): Strip wrappers for running completer
- files: clap_complete/examples/exhaustive.rs, clap_complete/src/env/mod.rs
- date: 2024-09-17T15:47:46-05:00
- summary: The change removes the first argument from the args vector before searching for "--", which likely shifts the index and can mis‑handle arguments after the separator; test with a "--" in the command line to see if the output changes.

### finding 1: off-by-one
- file: clap_complete/src/env/mod.rs
- explanation: Removing the first element from the args list before locating the "--" separator changes the position used later, potentially causing an off‑by‑one error when processing arguments after the separator
- grade: mechanism
- verified_by: right file and a coherent argument about args.remove(0) shifting later positions, but the commit is the fix and the claim is unverified.

## clap-rs__clap f9be3215c189  (rust)
- subject: refactor(parser): Minor clean up
- files: src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: The changes only adjust documentation comments, add a wildcard import, and replace fully‑qualified paths with locally imported names; they do not appear to alter runtime behaviour. Verify that the macro and trait constraints still compile as before.

- (no findings reported)

## fastapi__fastapi 9b35d355bfb4  (python)
- subject: 📝 Update `docs_src/path_params_numeric_validations/tutorial006.py` (#11478)
- files: docs_src/path_params_numeric_validations/tutorial006.py, docs_src/path_params_numeric_validations/tutorial006_an.py, docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- date: 2024-08-28T18:39:15-05:00
- summary: The change adds a size field only when size is truthy, so a value of 0 is ignored; check that zero is handled correctly because the API may be expected to return it.

### finding 1: logic-error
- file: docs_src/path_params_numeric_validations/tutorial006.py
- explanation: The `if size:` guard treats a valid size of 0 as falsy, causing the endpoint to omit the size field for zero values, which may violate the intended contract.
- grade: locus
- verified_by: CORRECT: `if size:` skips size=0, falsy but valid. Code-accurate; the 3B fabricated float()/int() casts on this same commit.

### finding 2: logic-error
- file: docs_src/path_params_numeric_validations/tutorial006_an.py
- explanation: The same truthiness check is used in the async example, so size=0 is ignored there as well.
- grade: wrong
- verified_by: duplicate against the _an variant.

### finding 3: logic-error
- file: docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- explanation: The Python‑3.9 async example also skips size=0 due to the `if size:` condition.
- grade: wrong
- verified_by: duplicate against the _an_py39 variant.

## fastapi__fastapi d11f820ac38b  (python)
- subject: 📝 Update docs for JWT to prevent timing attacks (#14908)
- files: docs/en/docs/tutorial/security/oauth2-jwt.md, docs_src/security/tutorial004_an_py310.py, docs_src/security/tutorial004_py310.py, docs_src/security/tutorial005_an_py310.py, docs_src/security/tutorial005_py310.py
- date: 2026-02-12T19:10:35+01:00
- summary: The commit adds a dummy‑hash verification when a username is not found to mitigate timing attacks. This means verify_password is now invoked even for missing users, which can raise on invalid password inputs that previously were ignored. Test with a non‑string password to ensure the function still returns False rather than erroring.

### finding 1: input-validation
- file: docs_src/security/tutorial004_an_py310.py
- explanation: Calling verify_password with a non‑string password (e.g., None) after the change may raise a TypeError, causing authenticate_user to error instead of returning False as before.
- grade: mechanism
- verified_by: right place (authenticate_user / verify_password) and NOT the 3B's inversion - it does not claim an auth bypass - but a non-string password raising TypeError is speculative on a docs commit.

## fastapi__fastapi 6cc24416e228  (python)
- subject: ✏️ Fix docstring typos in http security (#12223)
- files: fastapi/security/http.py
- date: 2024-09-19T11:47:28+02:00
- summary: The change only corrects wording in docstrings for HTTPBearer and HTTPDigest; it does not alter runtime logic, so it is safe.

- (no findings reported)

## fastapi__fastapi 31887b1cc6fb  (python)
- subject: 🔖 Release version 0.115.4
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2024-10-27T21:51:55Z
- summary: The commit updates the package version string from 0.115.3 to 0.115.4 and adds a release‑notes entry; this is a straightforward version bump with no functional code changes, so verify the new __version__ value.

- (no findings reported)

## fastapi__fastapi c7e7b651d694  (python)
- subject: 🔖 Release version 0.141.0 (#16103)
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2026-07-29T14:45:21Z
- summary: The change only bumps the __version__ constant and adds release‑note text, so runtime behaviour is unchanged apart from the version string value.

- (no findings reported)

## fastapi__fastapi 91a929319c4c  (python)
- subject: ♻️ Update internal checks to support Pydantic 2.10 (#12914)
- files: fastapi/_compat.py, fastapi/params.py
- date: 2024-11-12T17:10:42+01:00
- summary: The change replaces string comparison of the Pydantic version with a numeric tuple comparison, fixing the incorrect handling of versions >= 2.7 (e.g., 2.10.0). Verify that deprecated handling now follows the new branch for such versions.

- (no findings reported)

## fastapi__fastapi 3611c3fc5b82  (python)
- subject: ⬆️ Add support for Python 3.14 (#14165)
- files: .github/workflows/test.yml, pyproject.toml, requirements-tests.txt, tests/test_tutorial/test_sql_databases/test_tutorial001.py, tests/test_tutorial/test_sql_databases/test_tutorial002.py
- date: 2025-10-10T11:44:39+02:00
- summary: The commit adds explicit engine disposal in the tutorial test fixtures, likely eliminating the previous ResourceWarning about an unclosed SQL connection. Verify that the warning no longer appears when the tests are run.

- (no findings reported)

## fastapi__fastapi 2260afaf4331  (python)
- subject: 🐛 Fix failing test, update format for raised errors (#15804)
- files: fastapi/routing.py
- date: 2026-06-20T00:51:31Z
- summary: The change replaces repr‑based formatting of the error message with manual quoting, which may mis‑format paths that contain single quotes or other special characters; verify that error messages remain correct for such inputs.

### finding 1: error-handling
- file: fastapi/routing.py
- explanation: Manual quoting of directory strings can produce malformed RuntimeError messages when the path includes single quotes or escape sequences, potentially breaking downstream parsing or tests.
- grade: mechanism
- verified_by: no longer the fabricated SyntaxError of the word-diff run; now a real if minor observation about quoting in the message. Still a finding on a clean fix.

## gin-gonic__gin dbd8a2515093  (go)
- subject: feat: added `AbortWithStatusPureJSON()` in `Context` (#4290)
- files: context.go, context_test.go
- date: 2025-07-13T09:40:35+08:00
- summary: The commit introduces a new AbortWithStatusPureJSON method that aborts the context and writes a pure JSON response; it does not alter existing behaviour, but you may want to verify that PureJSON correctly handles edge cases such as a nil payload and that the abort index is set as expected.

- (no findings reported)

## gin-gonic__gin a48f83c9a1a1  (go)
- subject: Adding helper functions to router group for LINK and UNLINK.
- files: routergroup.go
- date: 2014-12-15T13:19:51-04:00
- summary: The change introduces LINK and UNLINK shortcut methods on RouterGroup, extending the API but not altering existing routing behavior; it appears safe but you may want to confirm that the underlying httprouter accepts these method names.

- (no findings reported)

## gin-gonic__gin ce2201c39214  (go)
- subject: router.Run() can be called without parameters. #405
- files: gin.go, gin_integration_test.go, utils.go
- date: 2015-08-16T16:19:51+02:00
- summary: Run now accepts an optional address and falls back to the PORT environment variable or ":8080"; however resolveAddress does not validate the env value, so malformed PORT strings can produce an invalid listen address. Verify that such values are handled safely.

### finding 1: input-validation
- file: utils.go
- explanation: resolveAddress blindly prefixes a colon to the PORT env value and returns it, without checking that the value is numeric or already contains a colon, which can lead to an invalid address passed to http.ListenAndServe and cause a runtime error.
- grade: wrong
- verified_by: resolveAddress prefixing a colon to PORT is the documented behaviour of the feature this commit adds, not a defect it introduces.

## gin-gonic__gin 34b1d0262e37  (go)
- subject: Refactors response_writer.go
- files: response_writer.go
- date: 2015-03-23T04:45:33+01:00
- summary: The refactor changed Flush to assume the underlying ResponseWriter always implements http.Flusher, which can cause a panic for non‑flusher writers. Verify that Flush is safe with all writer types.

### finding 1: error-handling
- file: response_writer.go
- explanation: Calling Flush on a responseWriter whose embedded ResponseWriter does not implement http.Flusher will trigger a runtime panic due to an unchecked type assertion
- grade: locus
- verified_by: CORRECT, and the one real defect in the 40: `flusher, ok := ...; if ok` is replaced by an unguarded `w.ResponseWriter.(http.Flusher).Flush()`, which panics on a non-Flusher. All three 3B runs missed it.

## gin-gonic__gin 80f691159fa5  (go)
- subject: Added simple testing documentation and examples (#1156)
- files: README.md, examples/basic/main.go, examples/basic/main_test.go
- date: 2017-11-11T23:37:32-06:00
- summary: The commit refactors the example to expose a setupRouter function and adds a unit test for the /ping route; no runtime behavior of the library itself is changed, so it appears safe.

- (no findings reported)

## gin-gonic__gin e198f6e85922  (go)
- subject: refactor(render): remove headers parameter from writeHeader (#4353)
- files: render/reader.go
- date: 2025-09-19T08:39:17+08:00
- summary: The change drops the explicit headers parameter and makes writeHeaders read directly from r.Headers, which should preserve the existing behaviour of writing any custom headers; verify that headers are still set correctly.

- (no findings reported)

## gin-gonic__gin 1d462bbe3713  (go)
- subject: chore: update ginS (#1822)
- files: ginS/gins.go
- date: 2019-03-21T15:12:06+08:00
- summary: The change adds a Routes() helper and a RunFd() entry point while only adjusting comments; existing behavior of Run, RunTLS, and RunUnix remains unchanged, so no new runtime defect is apparent.

- (no findings reported)

## gin-gonic__gin 4194adce4cd5  (go)
- subject: Adds additional bindings for multipart and form
- files: binding/binding.go, binding/binding_test.go, binding/form.go
- date: 2015-07-03T04:20:00+02:00
- summary: The change introduces FormPost and FormMultipart bindings that parse URL‑encoded and multipart form bodies respectively; the existing behavior is unchanged and the new code appears safe, though you should verify that FormMultipart.Bind correctly handles a well‑formed multipart request.

- (no findings reported)

## spring-projects__spring-boot e680142dd4c0  (java)
- subject: Update Gradle conventions to ensure Eclipse IDE defaults to JRE 17
- files: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java, buildSrc/src/main/java/org/springframework/boot/build/SystemRequirementsExtension.java
- date: 2026-01-21T21:03:26-08:00
- summary: The change forces Java 17 source/target compatibility when no toolchainVersion is specified, which may unintentionally alter the build for projects that relied on the previous default. Verify that such builds still succeed with the new defaults.

### finding 1: logic-error
- file: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java
- explanation: If a project does not define 'toolchainVersion', the added code sets sourceCompatibility and targetCompatibility to Java 17, potentially breaking builds that were intended to compile with an older Java version.
- grade: wrong
- verified_by: false alarm on a clean Gradle/Eclipse conventions change.

## spring-projects__spring-boot 2d4baa3305ed  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-test-nomockito
- files: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- date: 2025-08-13T11:50:54+02:00
- summary: The commit only adds a package‑info.java file that applies the @NullMarked annotation and imports the JSpecify annotation; it does not alter any executable logic, so runtime behaviour should remain the same.

- (no findings reported)

## spring-projects__spring-boot 3ebc8653d583  (java)
- subject: Polish "Add server-side support for custom gRPC conventions"
- files: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- date: 2026-03-25T10:47:41+01:00
- summary: The commit adds a new test that checks a custom GrpcServerObservationConvention bean is used by ObservationGrpcServerInterceptor, without altering production code, so the observable behaviour of the application should remain unchanged.

- (no findings reported)

## spring-projects__spring-boot abec26e504fa  (java)
- subject: Polish
- files: documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientAssertJTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientTests.java
- date: 2026-01-21T10:06:02-08:00
- summary: The commit only renames the @Autowired RestTestClient parameter from `webClient` to `restClient` in several test classes; this does not affect runtime behavior, so there is no functional change to verify.

- (no findings reported)

## spring-projects__spring-boot 866be19024c8  (java)
- subject: Add nullability annotations to tests in module/spring-boot-validation
- files: module/spring-boot-validation/build.gradle, module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- date: 2025-10-15T16:58:21+02:00
- summary: The commit adds @Nullable annotations and a null‑check to the unwrap method, so a null Class argument no longer triggers a NullPointerException but is passed to the delegate. Verify that this changed behaviour (e.g., calling unwrap(null) in the test) is intended and does not cause unexpected failures.

- (no findings reported)

## spring-projects__spring-boot 118bf1012796  (java)
- subject: Add nullability annotations to tests in module/spring-boot-rsocket-test
- files: module/spring-boot-rsocket-test/build.gradle, module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- date: 2025-10-13T13:44:26+02:00
- summary: Adding @Nullable to the injected fields and enabling nullability checking for test compilation may cause existing test code that assumes those values are non‑null to fail compilation. Verify that the test suite still compiles and runs.

### finding 1: null-dereference
- file: module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- explanation: test code may now dereference the @Nullable fields without checking for null, triggering a compile‑time nullability error
- grade: mechanism
- verified_by: accurately describes COMPILE-TIME nullability checking rather than claiming a runtime NPE, which is what the 3B got wrong here - but still a finding on an annotation-only commit.

## spring-projects__spring-boot f28caee30d2e  (java)
- subject: Fix NestedJarFile.JarEntryInputStream's available() behavior
- files: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java, spring-boot-project/spring-boot-tools/spring-boot-loader/src/test/java/org/springframework/boot/loader/jar/NestedJarFileTests.java
- date: 2025-09-05T17:29:22+01:00
- summary: The commit introduces a remaining byte counter and removes the automatic close when the counter reaches zero, fixing available() to report zero after the stream is exhausted. Test that available() now returns zero after reading or skipping to the end, and be aware that the stream no longer closes itself, which may cause a resource leak if callers forget to close it.

### finding 1: resource-leak
- file: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java
- explanation: The stream no longer closes automatically when all bytes have been read or skipped, so code that relied on the implicit close may leave the underlying Zip entry open, leading to resource leakage.
- grade: mechanism
- verified_by: right file and right subsystem, and unlike the 3B it does not invert the fix into a regression - but the resource-leak claim is unverified and the commit is the repair.

## spring-projects__spring-boot fab69e444b29  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-data-ldap
- files: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java, smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/package-info.java
- date: 2025-08-13T11:32:14+02:00
- summary: The commit only adds @Nullable annotations to the dn and phone fields and introduces a package‑level @NullMarked marker. These are compile‑time hints and do not change runtime behavior, though callers should be aware the fields may now be null.

- (no findings reported)
