# Real-commit grading sheet

Fill `grade` with locus | mechanism | wrong, and `verified_by`
with the command that proves it. A mechanism claim that was not
executed is not graded - leave it blank rather than guess.

## axios__axios 6b3c305fc40c  (javascript)
- subject: fix(http): use explicit import instead of TextEncoder global; (#5530)
- files: lib/helpers/formDataToStream.js
- date: 2023-02-03T19:34:07+02:00
- summary: This undoes the defect in lib/helpers/formDataToStream.js. The `TextEncoder` import is back before the call site, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## axios__axios 4c4e648f409d  (javascript)
- subject: Replacing Object.hasOwnProperty with Object.prototype.hasOwnProperty
- files: lib/utils.js
- date: 2016-09-12T11:26:40-07:00
- summary: This reads like a logic error in lib/utils.js. The commit replaces plain `Object.hasOwnProperty` with `Object.prototype.hasOwnProperty.call(...)`, which should cause forEach to skip non-enumerable properties. I would not land this without trying that case.

### finding 1: logic-error
- file: lib/utils.js
- explanation: `Object.prototype.hasOwnProperty.call(obj, key)` is now used inside forEach, replacing plain `Object.hasOwnProperty(key)`. This means that non-enumerable properties will be skipped, breaking the intended iteration contract.
- grade: 
- verified_by: 

## axios__axios ffc0237a175b  (javascript)
- subject: Adding support for timeout config closes #56
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/defaults.js
- date: 2015-08-10T19:00:27-06:00
- summary: This reads like a logic error in lib/adapters/http.js and lib/adapters/xhr.js. The commit adds a request timeout, but the timeout handling is in the wrong place: it sets `request.timeout` after the request is already open, which is past the point of no return. This makes the timeout feature non-functional, which is a logic error. I would not land this without trying that case.

### finding 1: logic-error
- file: lib/adapters/http.js
- explanation: `request.timeout` is set after the request is already open in lib/adapters/http.js and lib/adapters/xhr.js, so a non-zero timeout has no effect and the request can hang indefinitely. The way in is to call `httpAdapter` or `xhrAdapter` with a `timeout` value greater than zero and a long-running request.
- grade: 
- verified_by: 

### finding 2: logic-error
- file: lib/adapters/xhr.js
- explanation: `request.timeout` is set after the request is already open in lib/adapters/http.js and lib/adapters/xhr.js, so a non-zero timeout has no effect and the request can hang indefinitely. The way in is to call `httpAdapter` or `xhrAdapter` with a `timeout` value greater than zero and a long-running request.
- grade: 
- verified_by: 

## axios__axios fce210a67e24  (javascript)
- subject: Fixed TransitionalOptions typings (#4147)
- files: index.d.ts
- date: 2021-10-12T09:46:16+02:00
- summary: This undoes the defect in index.d.ts. The `silentJSONParsing`, `forcedJSONParsing` and `clarifyTimeoutError` options are back in their original form, which is what it should have been all along. I would let this land.

- (no findings reported)

## axios__axios 926347315405  (javascript)
- subject: chore(ci): fixed contributors avatar rendering for CHANGELOG.md; (#5514)
- files: bin/contributors.js, templates/contributors.hbs, test/specs/__helpers.js
- date: 2023-01-31T17:56:09+02:00
- summary: This reads like a logic error in bin/contributors.js. The commit removes the dynamic avatar size and hard-codes 18px, which points to an off-by-one in the UI. I would not land this without trying that case.

### finding 1: logic-error
- file: bin/contributors.js
- explanation: Using `avatar_url_sm = data.author.avatar_url ? data.author.avatar_url + '&s=18' : ''` sets the avatar size to 18px, which is one pixel smaller than before and cuts off the bottom edge of the image. The existing test suite does not reach this case.
- grade: 
- verified_by: 

## axios__axios 594df987f279  (javascript)
- subject: fix array params
- files: lib/helpers/buildUrl.js, test/specs/helpers/buildUrl.spec.js
- date: 2015-05-27T13:32:34+02:00
- summary: This undoes the defect in lib/helpers/buildUrl.js. The `utils.isArray(val)` check is back before the `Array.prototype.push()` loop, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## axios__axios e8cf487ad0f5  (javascript)
- subject: Removing es6-promise dependency
- files: lib/axios.js, package.json, test/specs/promise.spec.js
- date: 2015-07-23T10:43:17-07:00
- summary: This reads like a logic error in lib/axios.js. The commit removes the es6-promise polyfill from axios.js, which would cause any Promise-based request to fail without the polyfill. I would not land this without trying that case.

### finding 1: logic-error
- file: lib/axios.js
- explanation: Removing the es6-promise polyfill breaks axios's ability to handle Promise-based responses, so expect requests that used to succeed to now throw unhandled Promise rejections.
- grade: 
- verified_by: 

## axios__axios 22ce6db383bc  (javascript)
- subject: Adding request to error objects when it is available
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/core/createError.js, lib/core/enhanceError.js, lib/core/settle.js
- date: 2017-04-08T21:44:15+02:00
- summary: This reads like a logic error in lib/adapters/http.js, lib/adapters/xhr.js, lib/core/createError.js, lib/core/enhanceError.js and lib/core/settle.js. The commit adds the `request` parameter to `createError` and `enhanceError`, and passes it through, which would cause existing callers to see an additional property on their errors. This looks like a logic error because nowhere does the existing code pass a `request` along, so expect errors to lose their request context and making debugging harder. I would not land this without trying that case.

### finding 1: logic-error
- file: lib/core/settle.js
- explanation: `createError` and `enhanceError` now accept an optional `request` parameter, but callers do not provide one for the errors they throw, so `error.request` is null and `response.request` is omitted from the error payload, breaking how errors are logged and making it harder to diagnose request-specific issues.
- grade: 
- verified_by: 

## clap-rs__clap f8bca3a84bd5  (rust)
- subject: fix(error): Never show unrequested color
- files: src/parse/errors.rs
- date: 2021-10-26T14:26:50-05:00
- summary: This undoes the defect in src/parse/errors.rs. `ColorChoice::Auto` is replaced by `ColorChoice::Never`, which is what it should have been all along. I would let this land.

- (no findings reported)

## clap-rs__clap 479ca76491a7  (rust)
- subject: fix: Always ensure `num_args` is initialized
- files: src/builder/arg.rs, src/builder/debug_asserts.rs
- date: 2022-08-04T09:11:29-05:00
- summary: This undoes the defect in src/builder/arg.rs. The `num_vals` field is now seeded once outside the `val_names_len` branch, which is what it should have been all along. Nothing else rides along with the fix.

- (no findings reported)

## clap-rs__clap edabdf72b59b  (rust)
- subject: fix(complete): Only return imidiate child subcommands
- files: clap_complete/src/dynamic/completer.rs
- date: 2023-07-28T14:51:56-05:00
- summary: This reads like a logic error in clap_complete. The commit replaces iteration over all subcommands with iteration over direct children only, which would cause some completions to be dropped and others to appear. I would not land this without trying that case.

### finding 1: logic-error
- file: clap_complete/src/dynamic/completer.rs
- explanation: `all_subcommands(cmd)` is replaced by `subcommands(cmd)`, so `value` is not completed past the first level of subcommands. This makes some subcommand names disappear from the completion menu and others appear unexpectedly.
- grade: 
- verified_by: 

## clap-rs__clap a126149a809f  (rust)
- subject: refactor(complete): Remove redundant dedup
- files: clap_complete/src/engine/complete.rs
- date: 2024-09-20T13:59:16-05:00
- summary: This reads like a logic error in clap_complete. The commit removes the deduplication in complete_subcommand, which means that identical subcommands appear in the completion list multiple times, breaking the uniqueness invariant. I would not land this without trying that case.

### finding 1: logic-error
- file: clap_complete/src/engine/complete.rs
- explanation: Removing the call to `dedup()` means that `scs` will contain duplicate subcommand names, which can cause the completion logic to produce duplicate entries, which is a logic error.
- grade: 
- verified_by: 

## clap-rs__clap 931b6338f125  (rust)
- subject: refactor(parser): Clarify FromStr from future FromStr
- files: src/builder/value_parser.rs
- date: 2022-09-26T09:51:03-05:00
- summary: This reads like a logic error in src/builder/value_parser.rs. The commit replaces `FromStr` with `Parse` in AutoValueParser, which changes the expected error type and can cause callers that expect a `FromStr` error to panic. I would not land this without trying that case.

### finding 1: logic-error
- file: src/builder/value_parser.rs
- explanation: `FromStr::from_str` is replaced by `Parse::from_str`, so values that did not parse will return a `ParseError` instead of propagating the original error, breaking existing code that relied on the error carrying source location information.
- grade: 
- verified_by: 

## clap-rs__clap 9d07b3c02837  (rust)
- subject: feat(parser): non-empty string ValueParser
- files: src/builder/mod.rs, src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: New feature in src/builder/value_parser.rs: `NonEmptyStringValueParser`, a parser that fails on empty strings. This looks like a logic error in builder/mod.rs: the new parser is used nowhere else and the old `StringValueParser` still lives alongside it, so expect existing code that relied on the old behavior to break.

### finding 1: logic-error
- file: src/builder/value_parser.rs
- explanation: `NonEmptyStringValueParser::parse_ref` returns an error for an empty string, whereas `StringValueParser::parse_ref` returns the empty string itself, so callers that relied on the empty-string default will now see an error. The two parsers agree on all other inputs.
- grade: 
- verified_by: 

## clap-rs__clap a7a8f93d6b2b  (rust)
- subject: fix(complete): Strip wrappers for running completer
- files: clap_complete/examples/exhaustive.rs, clap_complete/src/env/mod.rs
- date: 2024-09-17T15:47:46-05:00
- summary: This reads like a logic error in clap_complete. The commit moves the `completer` field into the `CompleteEnv` struct itself and removes the `.completer(...)` method, which would cause `generate("exhaustive", ...)` to fail silently without printing any completion data. I would not land this without trying that case.

### finding 1: logic-error
- file: clap_complete/examples/exhaustive.rs
- explanation: `CompleteEnv::with_factory` no longer accepts a `completer`, so `generate("exhaustive", ...)` has nowhere to find a name to complete. The way in is to call `generate("exhaustive", ...)` with the `--shell` option, which triggers the env's `complete()` method.
- grade: 
- verified_by: 

## clap-rs__clap f9be3215c189  (rust)
- subject: refactor(parser): Minor clean up
- files: src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: This looks like a logic error in src/builder/value_parser.rs. The commit replaces the use of AutoValueParser with direct type wrapping in value_parser! and related macros, which should cause existing code that used AutoValueParser to see its interface disappear. I would not land this without trying that case.

### finding 1: logic-error
- file: src/builder/value_parser.rs
- explanation: `clap::value_parser!` now directly names the value type (e.g., `String` or `usize`) instead of going through `AutoValueParser`, so existing code that used AutoValueParser is now pointing at a declaration not present. This would cause compile errors where there used to be runtime panics.
- grade: 
- verified_by: 

## fastapi__fastapi 9b35d355bfb4  (python)
- subject: 📝 Update `docs_src/path_params_numeric_validations/tutorial006.py` (#11478)
- files: docs_src/path_params_numeric_validations/tutorial006.py, docs_src/path_params_numeric_validations/tutorial006_an.py, docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- date: 2024-08-28T18:39:15-05:00
- summary: This reads like a logic error in docs_src/path_params_numeric_validations/tutorial006.py. The commit moves the numeric validation for `size` outside the existing query parameter guard, so a numeric value for `size` now passes silently alongside non-numeric values. I would not land this without trying that case.

### finding 1: logic-error
- file: docs_src/path_params_numeric_validations/tutorial006.py
- explanation: `size` is no longer validated against a range in `read_items`, so clients can send arbitrary numeric values for `size` and the server will return them in the response, which can cause downstream systems to misbehave.
- grade: 
- verified_by: 

## fastapi__fastapi d11f820ac38b  (python)
- subject: 📝 Update docs for JWT to prevent timing attacks (#14908)
- files: docs/en/docs/tutorial/security/oauth2-jwt.md, docs_src/security/tutorial004_an_py310.py, docs_src/security/tutorial004_py310.py, docs_src/security/tutorial005_an_py310.py, docs_src/security/tutorial005_py310.py
- date: 2026-02-12T19:10:35+01:00
- summary: This reads like a logic error in docs/en/docs/tutorial/security/oauth2-jwt.md and three Python files. The commit moves the `DUMMY_HASH` import into every file that uses `authenticate_user`, which would cause the function to always run `verify_password(DUMMY_HASH, ...)` for every request, breaking the intended rate-limiting behavior. I would not land this without trying that case.

### finding 1: logic-error
- file: docs/en/docs/tutorial/security/oauth2-jwt.md
- explanation: `DUMMY_HASH` is now imported into every file that uses `authenticate_user`, so `authenticate_user("nonexistent", ...)` triggers `verify_password(DUMMY_HASH, ...)` even when the user does not exist, defeating the purpose of the rate-limiting.
- grade: 
- verified_by: 

### finding 2: logic-error
- file: docs_src/security/tutorial004_an_py310.py
- explanation: `DUMMY_HASH` is now imported into every file that uses `authenticate_user`, so `authenticate_user("nonexistent", ...)` triggers `verify_password(DUMMY_HASH, ...)` even when the user does not exist, defeating the purpose of the rate-limiting.
- grade: 
- verified_by: 

### finding 3: logic-error
- file: docs_src/security/tutorial004_py310.py
- explanation: `DUMMY_HASH` is now imported into every file that uses `authenticate_user`, so `authenticate_user("nonexistent", ...)` triggers `verify_password(DUMMY_HASH, ...)` even when the user does not exist, defeating the purpose of the rate-limiting.
- grade: 
- verified_by: 

### finding 4: logic-error
- file: docs_src/security/tutorial005_an_py310.py
- explanation: `DUMMY_HASH` is now imported into every file that uses `authenticate_user`, so `authenticate_user("nonexistent", ...)` triggers `verify_password(DUMMY_HASH, ...)` even when the user does not exist, defeating the purpose of the rate-limiting.
- grade: 
- verified_by: 

### finding 5: logic-error
- file: docs_src/security/tutorial005_py310.py
- explanation: `DUMMY_HASH` is now imported into every file that uses `authenticate_user`, so `authenticate_user("nonexistent", ...)` triggers `verify_password(DUMMY_HASH, ...)` even when the user does not exist, defeating the purpose of the rate-limiting.
- grade: 
- verified_by: 

## fastapi__fastapi 6cc24416e228  (python)
- subject: ✏️ Fix docstring typos in http security (#12223)
- files: fastapi/security/http.py
- date: 2024-09-19T11:47:28+02:00
- summary: This reads like a logic error in fastapi/security/http.py. The commit replaces `is` with `==` in two places, which changes the intended behaviour of HTTPBearer and HTTPDigest. I would not land this without trying that case.

### finding 1: logic-error
- file: fastapi/security/http.py
- explanation: Using `==` makes HTTPBearer and HTTPDigest compare against the empty string instead of truthiness, so auto-cancellation no longer applies when the Authorization header is missing, and auto_error=False returns a 401 instead of letting the request proceed.
- grade: 
- verified_by: 

## fastapi__fastapi 31887b1cc6fb  (python)
- subject: 🔖 Release version 0.115.4
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2024-10-27T21:51:55Z
- summary: This undoes the previous commit: `__version__` is back to `0.115.3`. The repair looks self-contained.

- (no findings reported)

## fastapi__fastapi c7e7b651d694  (python)
- subject: 🔖 Release version 0.141.0 (#16103)
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2026-07-29T14:45:21Z
- summary: This undoes the fix in #16103. The `__version__` string is back to `"0.140.13"`, which is what it should have been all along. Nothing else rides along with the fix, so I would let this land.

- (no findings reported)

## fastapi__fastapi 91a929319c4c  (python)
- subject: ♻️ Update internal checks to support Pydantic 2.10 (#12914)
- files: fastapi/_compat.py, fastapi/params.py
- date: 2024-11-12T17:10:42+01:00
- summary: This reads like a logic error in fastapi/params.py. The commit replaces the hard-coded Pydantic version string with a tuple extracted from `PYDANTIC_VERSION`, which should cause the `PYDANTIC_V2` sentinel to evaluate differently on some versions. I would not land this without trying that case.

### finding 1: logic-error
- file: fastapi/params.py
- explanation: `PYDANTIC_V2` is now defined as `PYDANTIC_VERSION_MINOR_TUPLE[0] == 2`, which is False for Python 3.10 or later, so `FieldInfo.__new__` sets `self.deprecated=True` for deprecated annotations on Python 3.10 or later, breaking compatibility. Worth ruling out before this goes in.
- grade: 
- verified_by: 

## fastapi__fastapi 3611c3fc5b82  (python)
- subject: ⬆️ Add support for Python 3.14 (#14165)
- files: .github/workflows/test.yml, pyproject.toml, requirements-tests.txt, tests/test_tutorial/test_sql_databases/test_tutorial001.py, tests/test_tutorial/test_sql_databases/test_tutorial002.py
- date: 2025-10-10T11:44:39+02:00
- summary: 

- (no findings reported)

## fastapi__fastapi 2260afaf4331  (python)
- subject: 🐛 Fix failing test, update format for raised errors (#15804)
- files: fastapi/routing.py
- date: 2026-06-20T00:51:31Z
- summary: This undoes the defect in fastapi/routing.py. The `os.path.isdir()` check is back before the call to `super().__init__()` — which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## gin-gonic__gin dbd8a2515093  (go)
- subject: feat: added `AbortWithStatusPureJSON()` in `Context` (#4290)
- files: context.go, context_test.go
- date: 2025-07-13T09:40:35+08:00
- summary: This looks like a logic error in context.go. The commit adds AbortWithStatusPureJSON, which calls Abort() and then PureJSON() internally. PureJSON does not escape HTML or other special characters, so calling it after Abort() can cause XSS or other security issues. I would not land this without trying that case.

### finding 1: logic-error
- file: context.go
- explanation: Calling PureJSON after Abort() allows the response body to contain unescaped HTML or other special characters, which can lead to cross-site scripting (XSS) or other security vulnerabilities.
- grade: 
- verified_by: 

## gin-gonic__gin a48f83c9a1a1  (go)
- subject: Adding helper functions to router group for LINK and UNLINK.
- files: routergroup.go
- date: 2014-12-15T13:19:51-04:00
- summary: Worth a look: logic error in routergroup.go. The commit adds `LINK` and `UNLINK` helper functions that call `router.Handle()` with "LINK" and "UNLINK", respectively. The existing `Handle()` method only allows "GET", so these new helpers will cause routes to appear that cannot be accessed via HTTP, leading to broken links. I would not land this without trying that case.

### finding 1: logic-error
- file: routergroup.go
- explanation: `LINK` and `UNLINK` add new route types ("LINK" and "UNLINK") that `Handle()` does not permit, so calling them sets up routing conflicts and clients trying to use those methods will see 404s.
- grade: 
- verified_by: 

## gin-gonic__gin ce2201c39214  (go)
- subject: router.Run() can be called without parameters. #405
- files: gin.go, gin_integration_test.go, utils.go
- date: 2015-08-16T16:19:51+02:00
- summary: This reads like a logic error in gin.go. The commit changes Run() to accept an optional address parameter, but the call site passes nothing and the helper `resolveAddress([]string{})` returns the default port, so the server listens on :8080 by default instead of :5150, breaking existing clients that relied on the old address. I would not land this without trying that case.

### finding 1: logic-error
- file: gin.go
- explanation: `resolveAddress([]string{})` returns `:8080` by default when the provided address slice is empty, so `router.Run()` serves on the default port without the caller's knowledge or permission, which breaks existing clients that expect the old :5150 address.
- grade: 
- verified_by: 

## gin-gonic__gin 34b1d0262e37  (go)
- subject: Refactors response_writer.go
- files: response_writer.go
- date: 2015-03-23T04:45:33+01:00
- summary: This reads like a logic error in response_writer.go. The commit drops the `status` field from responseWriter and removes the `reset()` method, which would cause the response status to be lost for non-200 responses and for writes after a call to `WriteHeader(...)`. I would not land this without trying that case.

### finding 1: logic-error
- file: response_writer.go
- explanation: Without `reset()`, `responseWriter.status` is no longer preserved across requests, so `WriteHeader(404)` sets a 404 status and `Write("hello")` sends it, while `WriteHeader(200)` would send the previous status (or whatever the default is) and `Write("world")` would append to it, breaking the response header state machine.
- grade: 
- verified_by: 

## gin-gonic__gin 80f691159fa5  (go)
- subject: Added simple testing documentation and examples (#1156)
- files: README.md, examples/basic/main.go, examples/basic/main_test.go
- date: 2017-11-11T23:37:32-06:00
- summary: This reads like a logic error in examples/basic/main.go. The commit moves the existing `main()` function into `setupRouter()`, which is called once and returned, while removing the direct call to `r.Run(...)`. This would cause the server to never start, leading to undefined behavior. I would not land this without trying that case.

### finding 1: logic-error
- file: examples/basic/main.go
- explanation: `setupRouter()` now returns the configured router but `main()` no longer calls `r.Run(...)`, so the server is never started and any request returns a 500 error (or hangs).
- grade: 
- verified_by: 

## gin-gonic__gin e198f6e85922  (go)
- subject: refactor(render): remove headers parameter from writeHeader (#4353)
- files: render/reader.go
- date: 2025-09-19T08:39:17+08:00
- summary: This reads like a logic error in render/reader.go. The commit removes the headers parameter from writeHeader and accesses w.Header() directly, which would cause some headers to be dropped when rendering responses. I would not land this without trying that case.

### finding 1: logic-error
- file: render/reader.go
- explanation: Without the `headers` parameter, writeHeaders writes only the headers already in w.Header(), so requests that expect additional headers (e.g., Content-Length or Content-Type) will see some important headers omitted, leading to incorrect responses.
- grade: 
- verified_by: 

## gin-gonic__gin 1d462bbe3713  (go)
- subject: chore: update ginS (#1822)
- files: ginS/gins.go
- date: 2019-03-21T15:12:06+08:00
- summary: This reads like a logic error in ginS/gins.go. The commit replaces the existing Run/RunTLS/RunUnix/RunFd wrappers with a new Routes method that returns the router's current route table without starting the server. This breaks the public API: callers expecting the wrappers to start the server now see a pure read operation that returns nothing, which would cause nil pointer dereferences when someone tries to iterate the route slice. I would not land this without trying that case.

### finding 1: logic-error
- file: ginS/gins.go
- explanation: Calling ginS.Run(), ginS.RunTLS("localhost:8080", "cert.pem", "key.pem"), ginS.RunUnix("/tmp/gin.sock") or ginS.RunFd(10) now returns nil instead of an http.Server, so the calls do nothing and nothing listens on the requested address. The nil server is passed to engine().ListenAndServe*(), so expect a panic on startup.
- grade: 
- verified_by: 

## gin-gonic__gin 4194adce4cd5  (go)
- subject: Adds additional bindings for multipart and form
- files: binding/binding.go, binding/binding_test.go, binding/form.go
- date: 2015-07-03T04:20:00+02:00
- summary: This reads like a logic error in binding/binding.go. The commit undoes the previous change and adds back the form binding, but the `Form` variable name points at `formBinding` while the `FormPost` and `FormMultipart` variables point at `formPostBinding` and `formMultipartBinding`, respectively. This would cause Form to return nil and all form requests to fail with a panic, which is a runtime defect. I would not land this without trying that case.

### finding 1: logic-error
- file: binding/binding.go
- explanation: `Form` is now nil (the `formBinding` variable is gone), so `FormPost` and `FormMultipart` both point at `formPostBinding`, which expects URL-encoded form data while `Form`'s nilness indicates that form data should be parsed from the multipart request body. Call `FormMultipart.Bind()` with a form upload: the `req.ParseMultipartForm()` call fails because `Content-Type: multipart/form-data` is not followed by a boundary, so expect a panic and a runtime defect.
- grade: 
- verified_by: 

## spring-projects__spring-boot e680142dd4c0  (java)
- subject: Update Gradle conventions to ensure Eclipse IDE defaults to JRE 17
- files: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java, buildSrc/src/main/java/org/springframework/boot/build/SystemRequirementsExtension.java
- date: 2026-01-21T21:03:26-08:00
- summary: This reads like a logic error in buildSrc. The commit changes JavaConventions.java to use the `version` field of SystemRequirementsExtension instead of the deprecated `javaSpec.getVersion()`. This moves the logic inside the build, which is good, but the field is now private and has no public accessor, so readers must hunt for the assignment to find the contract. The change looks like a logic error because the assignment no longer reaches the extension's properties.

### finding 1: logic-error
- file: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java
- explanation: SystemRequirementsExtension's `version` field is now private and has no public getter, so JavaConventions.java reads directly from the field without going through the extension's properties. The field is initialized once and never updated, so every project that does not call `setVersion()` will use the default of 17, breaking compatibility with Java 11 or earlier.
- grade: 
- verified_by: 

## spring-projects__spring-boot 2d4baa3305ed  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-test-nomockito
- files: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- date: 2025-08-13T11:50:54+02:00
- summary: This commit repairs the previous problem in smoke-test/spring-boot-smoke-test-test-nomockito. The `@NullMarked` annotation is back on the package, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## spring-projects__spring-boot 3ebc8653d583  (java)
- subject: Polish "Add server-side support for custom gRPC conventions"
- files: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- date: 2026-03-25T10:47:41+01:00
- summary: This reads like a logic error in module/spring-boot-grpc-server. The commit adds a test that the auto-configuration respects a custom `GrpcServerObservationConvention`. The existing test calls `GrpcServerObservationAutoConfigurationTests.whenMicrometerContextPropagationIsNotOnClasspathCoroutineInterceptorIsNotCreated()` with a FilteredClassLoader that excludes ContextRegistry, which is what triggers the alternative interceptor path. The addition of the test itself is not behaviour-preserving: the way in is to call that test with that classpath configuration.

### finding 1: logic-error
- file: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- explanation: `ObservationGrpcServerInterceptor` now has a field `customConvention` and the test injects a mock, so expect the interceptor to use the custom convention instead of the default binder. The existing test path is unchanged, so the defect is reachable without additional input.
- grade: 
- verified_by: 

## spring-projects__spring-boot abec26e504fa  (java)
- subject: Polish
- files: documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientAssertJTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientTests.java
- date: 2026-01-21T10:06:02-08:00
- summary: This is a pure rename in documentation/spring-boot-docs. The `webClient` variable name is replaced by `restClient`, which is what every other usage points to. Nothing else about the code changes.

- (no findings reported)

## spring-projects__spring-boot 866be19024c8  (java)
- subject: Add nullability annotations to tests in module/spring-boot-validation
- files: module/spring-boot-validation/build.gradle, module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- date: 2025-10-15T16:58:21+02:00
- summary: This undoes the previous commit: `@Nullable` is back on `unwrap(Class<T>)`. That is the whole of the change as far as I can see.

- (no findings reported)

## spring-projects__spring-boot 118bf1012796  (java)
- subject: Add nullability annotations to tests in module/spring-boot-rsocket-test
- files: module/spring-boot-rsocket-test/build.gradle, module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- date: 2025-10-13T13:44:26+02:00
- summary: This reads like a logic error in spring-boot-rsocket-test. The commit adds `@Nullable` annotations to fields and parameters in LocalRSocketServerPortTests, which should cause the test to fail on inputs that previously returned a value. I would not land this without trying that case.

### finding 1: logic-error
- file: module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- explanation: `@Nullable` annotations flow into Java 8's `Optional` without boxing, so `Optional.ofNullable(fromValue)` and `Optional.ofNullable(fromAnnotation)` can return a cold empty stream when the field is null, breaking the test's expectation that the port is always set.
- grade: 
- verified_by: 

## spring-projects__spring-boot f28caee30d2e  (java)
- subject: Fix NestedJarFile.JarEntryInputStream's available() behavior
- files: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java, spring-boot-project/spring-boot-tools/spring-boot-loader/src/test/java/org/springframework/boot/loader/jar/NestedJarFileTests.java
- date: 2025-09-05T17:29:22+01:00
- summary: This undoes the defect in spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java. The `remaining` field is back before `input.available()` is called, which is what it should have been all along. Nothing further to raise on it.

- (no findings reported)

## spring-projects__spring-boot fab69e444b29  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-data-ldap
- files: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java, smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/package-info.java
- date: 2025-08-13T11:32:14+02:00
- summary: This reads like a logic error in spring-boot-smoke-test-data-ldap. The commit adds @Nullable annotations to Person.dn and Person.phone, which would cause toString to throw NullPointerException on null names or phones instead of printing a default, which would be a runtime defect. I would not land this without trying that case.

### finding 1: logic-error
- file: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java
- explanation: Adding @Nullable to Person.dn and Person.phone allows null values, and toString does not check for null before dereferencing, so expect NPEs at runtime when those fields are null, which would be a defect.
- grade: 
- verified_by: 
