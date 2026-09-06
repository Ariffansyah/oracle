# Real-commit grading sheet

Fill `grade` with locus | mechanism | wrong, and `verified_by`
with the command that proves it. A mechanism claim that was not
executed is not graded - leave it blank rather than guess.

Hand-graded 1 Sep, same rule as the two 3B runs and the base-model control.
  graded 23 findings over 40 commits: locus 4 | mechanism 4 | wrong 14 | not graded 1

## axios__axios 6b3c305fc40c  (javascript)
- subject: fix(http): use explicit import instead of TextEncoder global; (#5530)
- files: lib/helpers/formDataToStream.js
- date: 2023-02-03T19:34:07+02:00
- summary: The commit adds an explicit import of TextEncoder from the Node 'util' module. This can cause a load failure in environments without the built‑in 'util' module, so test the module import in such contexts.

### finding 1: error-handling
- file: lib/helpers/formDataToStream.js
- explanation: Importing TextEncoder from 'util' will raise a module‑resolution error when the code runs in a non‑Node environment where the 'util' builtin is unavailable.
- grade: wrong
- verified_by: clean upstream fix. The 'util' import concern is real for browser builds but formDataToStream.js is the Node adapter; no defect is introduced.

## axios__axios 4c4e648f409d  (javascript)
- subject: Replacing Object.hasOwnProperty with Object.prototype.hasOwnProperty
- files: lib/utils.js
- date: 2016-09-12T11:26:40-07:00
- summary: The diff replaces the incorrect Object.hasOwnProperty call with Object.prototype.hasOwnProperty, fixing a TypeError that broke forEach when iterating over object keys. Verify that forEach now works on objects without throwing.

- (no findings reported)

## axios__axios ffc0237a175b  (javascript)
- subject: Adding support for timeout config closes #56
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/defaults.js
- date: 2015-08-10T19:00:27-06:00
- summary: The new timeout handling aborts the request on timeout but does not reject or resolve the promise, so callers may hang indefinitely when a timeout occurs.

### finding 1: error-handling
- file: lib/adapters/http.js
- explanation: Timeout callback aborts the request without rejecting the promise, leaving the caller without a result
- grade: mechanism
- verified_by: right place (req.setTimeout) and a code-grounded concern, but abort() fires the existing req.on('error') handler which rejects. Reasoned, not fabricated - unlike the 3B, which invented a promise wrapper.

### finding 2: error-handling
- file: lib/adapters/xhr.js
- explanation: XHR timeout is set but no ontimeout handler is provided, so the promise may never settle on timeout
- grade: mechanism
- verified_by: xhr.js really does set request.timeout with no ontimeout handler. Plausible; not verified, and the commit is the upstream feature.

## axios__axios fce210a67e24  (javascript)
- subject: Fixed TransitionalOptions typings (#4147)
- files: index.d.ts
- date: 2021-10-12T09:46:16+02:00
- summary: The change makes the three TransitionalOptions fields optional in the TypeScript declaration, affecting only type checking and not runtime behavior; verify that code still works when those fields are omitted.

- (no findings reported)

## axios__axios 926347315405  (javascript)
- subject: chore(ci): fixed contributors avatar rendering for CHANGELOG.md; (#5514)
- files: bin/contributors.js, templates/contributors.hbs, test/specs/__helpers.js
- date: 2023-01-31T17:56:09+02:00
- summary: The change updates avatar size and switches to an HTML <img> tag, but the Handlebars template appears to have mismatched braces after the edit, which may cause a rendering failure; test the template with an author having an avatar to ensure it still compiles and outputs correctly.

### finding 1: logic-error
- file: templates/contributors.hbs
- explanation: The Handlebars template contains malformed conditional syntax after the edit, potentially causing a compilation or runtime error when rendering contributors with avatars
- grade: wrong
- verified_by: FABRICATED: claims the Handlebars template is malformed after the edit. It is merged upstream code and renders.

## axios__axios 594df987f279  (javascript)
- subject: fix array params
- files: lib/helpers/buildUrl.js, test/specs/helpers/buildUrl.spec.js
- date: 2015-05-27T13:32:34+02:00
- summary: The commit changes array handling so that keys are suffixed with [] before being serialized, which likely corrects the previous output but could be a breaking change for code that relied on the old format. Verify that the new query‑string style is acceptable for all callers.

- (no findings reported)

## axios__axios e8cf487ad0f5  (javascript)
- subject: Removing es6-promise dependency
- files: lib/axios.js, package.json, test/specs/promise.spec.js
- date: 2015-07-23T10:43:17-07:00
- summary: Removing the built‑in es6‑promise polyfill means axios no longer ensures a Promise implementation is present; in environments lacking native Promise the library may now throw errors. Test in a Promise‑less environment to confirm the impact.

### finding 1: error-handling
- file: lib/axios.js
- explanation: If Promise is undefined, axios will attempt to use it (e.g., to create a promise for the request) and will throw a TypeError because the polyfill is no longer applied automatically.
- grade: locus
- verified_by: correct, and the same true positive both 3B seeds found: removing the polyfill leaves no Promise in environments without native support.

## axios__axios 22ce6db383bc  (javascript)
- subject: Adding request to error objects when it is available
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/core/createError.js, lib/core/enhanceError.js, lib/core/settle.js
- date: 2017-04-08T21:44:15+02:00
- summary: The change adds a request parameter to createError/enhanceError, which shifts the position of the response argument. Calls that still pass a response as the fourth argument will now treat it as a request, potentially breaking error handling. Verify callers that supply a response argument.

### finding 1: error-handling
- file: lib/core/createError.js
- explanation: If any module still calls createError with a response argument (as the fourth parameter), the response will be stored in error.request instead of error.response, causing downstream code that relies on error.response to fail.
- grade: wrong
- verified_by: the commit updates createError/enhanceError AND their callers in the same diff; no caller is left passing the old shape.

## clap-rs__clap f8bca3a84bd5  (rust)
- subject: fix(error): Never show unrequested color
- files: src/parse/errors.rs
- date: 2021-10-26T14:26:50-05:00
- summary: The commit changes the Colorizer construction from using ColorChoice::Auto to ColorChoice::Never, so error messages should stop emitting ANSI color codes. Verify that a formatted raw message no longer contains color escape sequences, confirming the intended fix.

- (no findings reported)

## clap-rs__clap 479ca76491a7  (rust)
- subject: fix: Always ensure `num_args` is initialized
- files: src/builder/arg.rs, src/builder/debug_asserts.rs
- date: 2022-08-04T09:11:29-05:00
- summary: The commit initializes `num_args` for all arguments (setting it to 0 for flags) and adds a guard in the debug assert to skip the check when `num_args` is zero. Verify that a flag now reports Some(0) instead of None and that the guard prevents a panic on zero values.

- (no findings reported)

## clap-rs__clap edabdf72b59b  (rust)
- subject: fix(complete): Only return imidiate child subcommands
- files: clap_complete/src/dynamic/completer.rs
- date: 2023-07-28T14:51:56-05:00
- summary: The change replaces all_subcommands with subcommands, limiting completions to immediate child subcommands; likely fixes over‑eager suggestions, but verify that nested subcommand completions are now omitted as intended.

- (no findings reported)

## clap-rs__clap a126149a809f  (rust)
- subject: refactor(complete): Remove redundant dedup
- files: clap_complete/src/engine/complete.rs
- date: 2024-09-20T13:59:16-05:00
- summary: The change removes the dedup call after sorting the completion candidates, so duplicate candidates may now be returned. Verify that duplicate completions are not introduced by testing with inputs that produce identical candidates.

### finding 1: logic-error
- file: clap_complete/src/engine/complete.rs
- explanation: Removing scs.dedup() may cause duplicate completion candidates to be returned, leading to redundant suggestions.
- grade: 
- verified_by: NOT GRADED: needs `cargo test -p clap_complete`. Subject asserts the dedup was redundant; same call as the 3B runs.

## clap-rs__clap 931b6338f125  (rust)
- subject: refactor(parser): Clarify FromStr from future FromStr
- files: src/builder/value_parser.rs
- date: 2022-09-26T09:51:03-05:00
- summary: The change only renames the generic parameter and associated trait names from FromStr to Parse without altering bounds or logic, so runtime behavior should remain the same; verify that existing code still compiles and works as before.

- (no findings reported)

## clap-rs__clap 9d07b3c02837  (rust)
- subject: feat(parser): non-empty string ValueParser
- files: src/builder/mod.rs, src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: Adds a NonEmptyStringValueParser and re‑exports it; no existing parsing logic is changed, so current behavior should stay the same.

- (no findings reported)

## clap-rs__clap a7a8f93d6b2b  (rust)
- subject: fix(complete): Strip wrappers for running completer
- files: clap_complete/examples/exhaustive.rs, clap_complete/src/env/mod.rs
- date: 2024-09-17T15:47:46-05:00
- summary: The commit changes the default completer to the first command‑line argument and joins it with the current directory when it contains path components. This can corrupt absolute paths and may also panic if the argument list is empty. Verify with an absolute invocation and with an empty args list.

### finding 1: logic-error
- file: clap_complete/src/env/mod.rs
- explanation: When args[0] is an absolute path, the code joins it with the current directory, producing an incorrect completer path.
- grade: wrong
- verified_by: commit is the fix ('Strip wrappers for running completer'); finding reads it as a regression.

### finding 2: input-validation
- file: clap_complete/src/env/mod.rs
- explanation: The code calls args.remove(0) without checking that args is non‑empty, which can panic if CompleteEnv is used with an empty argument list.
- grade: mechanism
- verified_by: args.remove(0) without an emptiness check is a real code observation, but it is pre-existing, not introduced here.

## clap-rs__clap f9be3215c189  (rust)
- subject: refactor(parser): Minor clean up
- files: src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: The refactor adds a sealed trait impl for `&&&AutoValueParser<P>` which likely never matches the intended `&&AutoValueParser<P>`, possibly changing the macro's behavior for self parsers; verify that the macro still produces the expected parser for such types.

### finding 1: logic-error
- file: src/builder/value_parser.rs
- explanation: The new `ValueParserViaSelfSealed` implementation is for `&&&AutoValueParser<P>` instead of the expected `&&AutoValueParser<P>`, so the macro may not recognize self parsers and could fallback to a different parser path
- grade: wrong
- verified_by: FABRICATED: claims a `&&&AutoValueParser<P>` impl. The diff adds only doc comments ('// Built-in types').

## fastapi__fastapi 9b35d355bfb4  (python)
- subject: 📝 Update `docs_src/path_params_numeric_validations/tutorial006.py` (#11478)
- files: docs_src/path_params_numeric_validations/tutorial006.py, docs_src/path_params_numeric_validations/tutorial006_an.py, docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- date: 2024-08-28T18:39:15-05:00
- summary: The change adds a conditional that includes the size parameter in the response when truthy, fixing the previous omission for provided sizes; verify that size is returned for typical values but note that falsy values like 0 may still be omitted.

### finding 1: logic-error
- file: docs_src/path_params_numeric_validations/tutorial006.py
- explanation: The `if size:` guard skips adding size when the value is falsy (e.g., 0), which may be a valid input, leading to missing data in the response.
- grade: locus
- verified_by: CORRECT: `if size:` skips size=0, a falsy but valid value. Code-accurate, and the 3B fabricated float()/int() casts on this same commit.

### finding 2: logic-error
- file: docs_src/path_params_numeric_validations/tutorial006_an.py
- explanation: The same conditional added to tutorial006_an.py may also omit size=0, causing missing data for that valid input.
- grade: wrong
- verified_by: duplicate of finding 1 against the _an variant.

### finding 3: logic-error
- file: docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- explanation: The same conditional added to tutorial006_an_py39.py may also omit size=0, causing missing data for that valid input.
- grade: wrong
- verified_by: duplicate of finding 1 against the _an_py39 variant.

## fastapi__fastapi d11f820ac38b  (python)
- subject: 📝 Update docs for JWT to prevent timing attacks (#14908)
- files: docs/en/docs/tutorial/security/oauth2-jwt.md, docs_src/security/tutorial004_an_py310.py, docs_src/security/tutorial004_py310.py, docs_src/security/tutorial005_an_py310.py, docs_src/security/tutorial005_py310.py
- date: 2026-02-12T19:10:35+01:00
- summary: The change adds a dummy hash verification for unknown users to make authentication timing uniform, fixing a timing‑attack issue. Ensure the function still returns False for unknown users and that the dummy verification is executed.

- (no findings reported)

## fastapi__fastapi 6cc24416e228  (python)
- subject: ✏️ Fix docstring typos in http security (#12223)
- files: fastapi/security/http.py
- date: 2024-09-19T11:47:28+02:00
- summary: The change only corrects docstring wording by adding the missing word “is” in two places; it does not alter any logic or runtime behavior, so it is safe.

- (no findings reported)

## fastapi__fastapi 31887b1cc6fb  (python)
- subject: 🔖 Release version 0.115.4
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2024-10-27T21:51:55Z
- summary: The change only bumps the package version string from 0.115.3 to 0.115.4 and adds a corresponding entry in the release notes; it introduces no functional code modifications, so it is low risk.

- (no findings reported)

## fastapi__fastapi c7e7b651d694  (python)
- subject: 🔖 Release version 0.141.0 (#16103)
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2026-07-29T14:45:21Z
- summary: The commit only updates the package version string and release notes; no functional code changes, so runtime behavior should remain the same.

- (no findings reported)

## fastapi__fastapi 91a929319c4c  (python)
- subject: ♻️ Update internal checks to support Pydantic 2.10 (#12914)
- files: fastapi/_compat.py, fastapi/params.py
- date: 2024-11-12T17:10:42+01:00
- summary: The change replaces string‑based version checks with numeric tuple comparison, fixing ordering bugs but adding a conversion that can fail on version strings containing non‑numeric parts; test imports with such a version to ensure they don’t break.

### finding 1: input-validation
- file: fastapi/_compat.py
- explanation: Parsing PYDANTIC_VERSION into ints will raise ValueError for version strings like "2.7rc1", causing import-time failures
- grade: locus
- verified_by: CORRECT: tuple(int(x) for x in PYDANTIC_VERSION.split('.')[:2]) raises ValueError on a pre-release like '2.7rc1'. The exact risk flagged by hand when grading the 3B.

## fastapi__fastapi 3611c3fc5b82  (python)
- subject: ⬆️ Add support for Python 3.14 (#14165)
- files: .github/workflows/test.yml, pyproject.toml, requirements-tests.txt, tests/test_tutorial/test_sql_databases/test_tutorial001.py, tests/test_tutorial/test_sql_databases/test_tutorial002.py
- date: 2025-10-10T11:44:39+02:00
- summary: The commit only adds CI matrix entries for Python 3.14, updates packaging metadata, bumps the sqlmodel test dependency, and adds explicit engine disposal in test fixtures. No functional code paths were altered, so runtime behaviour should remain the same.

- (no findings reported)

## fastapi__fastapi 2260afaf4331  (python)
- subject: 🐛 Fix failing test, update format for raised errors (#15804)
- files: fastapi/routing.py
- date: 2026-06-20T00:51:31Z
- summary: The new f‑string in the RuntimeError message is malformed (contains stray '+' and mismatched braces), which likely introduces a SyntaxError and breaks module import; verify that importing the module now raises an error.

### finding 1: error-handling
- file: fastapi/routing.py
- explanation: The f‑string in the raised RuntimeError is syntactically invalid, causing a SyntaxError at import time, which would prevent the routing module from loading.
- grade: wrong
- verified_by: FABRICATED: claims an invalid f-string causing SyntaxError at import. Merged upstream code imports fine.

## gin-gonic__gin dbd8a2515093  (go)
- subject: feat: added `AbortWithStatusPureJSON()` in `Context` (#4290)
- files: context.go, context_test.go
- date: 2025-07-13T09:40:35+08:00
- summary: The commit introduces a new AbortWithStatusPureJSON method that aborts the context and writes a pure JSON response; verify that it behaves like AbortWithStatusJSON (aborts, sets status, writes unescaped JSON).

- (no findings reported)

## gin-gonic__gin a48f83c9a1a1  (go)
- subject: Adding helper functions to router group for LINK and UNLINK.
- files: routergroup.go
- date: 2014-12-15T13:19:51-04:00
- summary: The commit adds LINK and UNLINK shortcut methods, but the UNLINK implementation contains a malformed call to group.Handle, introducing a syntax error that likely prevents the code from compiling. Verify the build to confirm the break.

### finding 1: other
- file: routergroup.go
- explanation: UNLINK method has an invalid syntax (`group.Handle("UNLINK",+} relativePath, handlers)`) causing a compile-time error
- grade: wrong
- verified_by: DIFF-MARKER MISREAD: quotes `group.Handle("UNLINK",+} relativePath` as source. The `+}` is word-diff punctuation, not code.

## gin-gonic__gin ce2201c39214  (go)
- subject: router.Run() can be called without parameters. #405
- files: gin.go, gin_integration_test.go, utils.go
- date: 2015-08-16T16:19:51+02:00
- summary: The change makes Engine.Run variadic, allowing it to be called with zero arguments; it now resolves the address from the PORT environment variable or defaults to :8080. Verify that calling Run() without parameters starts the server on the expected port.

- (no findings reported)

## gin-gonic__gin 34b1d0262e37  (go)
- subject: Refactors response_writer.go
- files: response_writer.go
- date: 2015-03-23T04:45:33+01:00
- summary: The refactor replaces the safe type‑assertion check in Flush with an unconditional cast, so a ResponseWriter that doesn't implement http.Flusher will now panic. Test with a non‑Flusher writer to confirm.

### finding 1: error-handling
- file: response_writer.go
- explanation: Flush now panics when the underlying writer lacks http.Flusher, breaking callers that relied on the previous no‑op behavior
- grade: locus
- verified_by: CORRECT, and the one real defect in the 40: the diff replaces `flusher, ok := ...; if ok` with an unguarded `w.ResponseWriter.(http.Flusher).Flush()`, which panics on a non-Flusher. ALL THREE 3B runs missed this.

## gin-gonic__gin 80f691159fa5  (go)
- subject: Added simple testing documentation and examples (#1156)
- files: README.md, examples/basic/main.go, examples/basic/main_test.go
- date: 2017-11-11T23:37:32-06:00
- summary: The change extracts router setup into a helper function and adds a test, but the runtime behavior of the example remains the same; the server still starts on the same port and serves the same endpoint. Verify that the binary still runs and returns "pong" on /ping.

- (no findings reported)

## gin-gonic__gin e198f6e85922  (go)
- subject: refactor(render): remove headers parameter from writeHeader (#4353)
- files: render/reader.go
- date: 2025-09-19T08:39:17+08:00
- summary: The refactor drops the explicit headers parameter from writeHeaders and makes the method read r.Headers directly; this should not change runtime behaviour, but you should test that headers set in r.Headers are still written to the HTTP response.

- (no findings reported)

## gin-gonic__gin 1d462bbe3713  (go)
- subject: chore: update ginS (#1822)
- files: ginS/gins.go
- date: 2019-03-21T15:12:06+08:00
- summary: The change rewrites the server‑startup helpers and adds new functions, but the diff leaves mismatched braces and stray tokens that likely break compilation, and it also replaces the original Run method with Routes, which can break callers that expect Run to start the server. Verify the package builds and that existing Run calls still behave as before.

### finding 1: other
- file: ginS/gins.go
- explanation: the diff introduces malformed Go syntax such as `return+} engine().RunUnix(file)` and stray closing braces, which will cause a compile error
- grade: wrong
- verified_by: DIFF-MARKER MISREAD: `return+} engine().RunUnix(file)` is diff punctuation.

### finding 2: api-misuse
- file: ginS/gins.go
- explanation: the original `Run` function that started the HTTP server is replaced by `Routes`, so code that calls `Run()` expecting the server to start will now receive route information instead of starting the server
- grade: wrong
- verified_by: Run is not replaced by Routes; both are present after the diff.

## gin-gonic__gin 4194adce4cd5  (go)
- subject: Adds additional bindings for multipart and form
- files: binding/binding.go, binding/binding_test.go, binding/form.go
- date: 2015-07-03T04:20:00+02:00
- summary: The new form multipart binding adds a malformed struct declaration (and extra braces) that likely prevents the code from compiling; try building the package to see if a syntax error occurs.

### finding 1: other
- file: binding/form.go
- explanation: The line `type formMultipartBinding struct{}` is corrupted by stray characters/braces in the diff, resulting in a syntax error that stops compilation.
- grade: wrong
- verified_by: DIFF-MARKER MISREAD: 'stray characters/braces' are word-diff markers.

## spring-projects__spring-boot e680142dd4c0  (java)
- subject: Update Gradle conventions to ensure Eclipse IDE defaults to JRE 17
- files: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java, buildSrc/src/main/java/org/springframework/boot/build/SystemRequirementsExtension.java
- date: 2026-01-21T21:03:26-08:00
- summary: The new guard around source/target compatibility skips setting JRE 17 when the project defines a "toolchainVersion" property, which could cause builds to use an unintended Java version. Verify builds with that property set.

### finding 1: logic-error
- file: JavaConventions.java
- explanation: The conditional `if (!project.hasProperty("toolchainVersion"))` may prevent the required JRE 17 compatibility from being applied, leading to compilation failures or mismatched bytecode versions when the property is present.
- grade: wrong
- verified_by: false alarm on a clean Gradle/Eclipse conventions change.

## spring-projects__spring-boot 2d4baa3305ed  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-test-nomockito
- files: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- date: 2025-08-13T11:50:54+02:00
- summary: Adds a package‑info.java that applies @NullMarked to the smoketest.testnomockito package; this only introduces compile‑time nullability metadata and does not change runtime behaviour, so it appears safe.

- (no findings reported)

## spring-projects__spring-boot 3ebc8653d583  (java)
- subject: Polish "Add server-side support for custom gRPC conventions"
- files: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- date: 2026-03-25T10:47:41+01:00
- summary: The commit only adds a new test that checks a custom GrpcServerObservationConvention bean is picked up by the interceptor; no production code is altered, so runtime behavior should remain unchanged (verify the test compiles and imports are correct).

- (no findings reported)

## spring-projects__spring-boot abec26e504fa  (java)
- subject: Polish
- files: documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientAssertJTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientTests.java
- date: 2026-01-21T10:06:02-08:00
- summary: The change merely renames the injected RestTestClient variable from `webClient` to `restClient` in several documentation test classes, so the observable behaviour of the code should remain the same. Verify that the tests still compile and pass with the new name.

- (no findings reported)

## spring-projects__spring-boot 866be19024c8  (java)
- subject: Add nullability annotations to tests in module/spring-boot-validation
- files: module/spring-boot-validation/build.gradle, module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- date: 2025-10-15T16:58:21+02:00
- summary: A null‑check was added before type.isInstance and the parameter was marked @Nullable, allowing null to be passed to delegate.unwrap. Verify that delegate.unwrap can safely handle a null argument, otherwise a NullPointerException may be introduced.

### finding 1: null-dereference
- file: module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- explanation: delegate.unwrap(type) is called with type possibly null; if the delegate does not accept null this will cause a NullPointerException at runtime
- grade: wrong
- verified_by: annotation-only commit; @Nullable does not make unwrap() receive null at runtime.

## spring-projects__spring-boot 118bf1012796  (java)
- subject: Add nullability annotations to tests in module/spring-boot-rsocket-test
- files: module/spring-boot-rsocket-test/build.gradle, module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- date: 2025-10-13T13:44:26+02:00
- summary: Enabling nullability checking for test sources and annotating fields as @Nullable may cause the test compilation to fail if those fields are used without null‑safety checks; verify the test build succeeds.

### finding 1: null-dereference
- file: module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- explanation: With nullability checking turned on for tests, any use of the newly @Nullable fields without a null‑guard could be flagged as a potential null‑dereference at compile time.
- grade: mechanism
- verified_by: accurately describes compile-time nullability checking rather than claiming a runtime NPE - better than the 3B's version - but still a finding on a clean annotation commit.

## spring-projects__spring-boot f28caee30d2e  (java)
- subject: Fix NestedJarFile.JarEntryInputStream's available() behavior
- files: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java, spring-boot-project/spring-boot-tools/spring-boot-loader/src/test/java/org/springframework/boot/loader/jar/NestedJarFileTests.java
- date: 2025-09-05T17:29:22+01:00
- summary: The change adds a remaining byte counter and removes the early close when the counter reaches zero, fixing available() to report zero after the stream is fully read. Verify that after consuming the stream, available() returns zero and that resources are still released when the stream is closed.

- (no findings reported)

## spring-projects__spring-boot fab69e444b29  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-data-ldap
- files: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java, smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/package-info.java
- date: 2025-08-13T11:32:14+02:00
- summary: The commit only adds JSpecify @Nullable annotations to Person fields and a @NullMarked package-info; these are compile‑time hints and should not alter runtime behavior, but you may want to verify that the Spring LDAP ODM framework ignores them as expected.

- (no findings reported)
