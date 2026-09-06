# Real-commit grading sheet

Fill `grade` with locus | mechanism | wrong, and `verified_by`
with the command that proves it. A mechanism claim that was not
executed is not graded - leave it blank rather than guess.

## axios__axios 6b3c305fc40c  (javascript)
- subject: fix(http): use explicit import instead of TextEncoder global; (#5530)
- files: lib/helpers/formDataToStream.js
- date: 2023-02-03T19:34:07+02:00
- summary: Reworks conditional handling for `TextEncoder` in lib/helpers/formDataToStream.js within the existing structure.

- (no findings reported)

## axios__axios 4c4e648f409d  (javascript)
- subject: Replacing Object.hasOwnProperty with Object.prototype.hasOwnProperty
- files: lib/utils.js
- date: 2016-09-12T11:26:40-07:00
- summary: Refines the guard on `call` in lib/utils.js without changing what the branches do.

- (no findings reported)

## axios__axios ffc0237a175b  (javascript)
- subject: Adding support for timeout config closes #56
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/defaults.js
- date: 2015-08-10T19:00:27-06:00
- summary: Refines the guard on `setTimeout`, `abort` in lib/adapters/http.js without changing what the branches do.

- (no findings reported)

## axios__axios fce210a67e24  (javascript)
- subject: Fixed TransitionalOptions typings (#4147)
- files: index.d.ts
- date: 2021-10-12T09:46:16+02:00
- summary: Refines the guard on `silentJSONParsing`, `forcedJSONParsing` in index.d.ts without changing what the branches do.

- (no findings reported)

## axios__axios 926347315405  (javascript)
- subject: chore(ci): fixed contributors avatar rendering for CHANGELOG.md; (#5514)
- files: bin/contributors.js, templates/contributors.hbs, test/specs/__helpers.js
- date: 2023-01-31T17:56:09+02:00
- summary: Refines the guard on `avatar_url_sm`, `avatar_url` in bin/contributors.js without changing what the branches do.

- (no findings reported)

## axios__axios 594df987f279  (javascript)
- subject: fix array params
- files: lib/helpers/buildUrl.js, test/specs/helpers/buildUrl.spec.js
- date: 2015-05-27T13:32:34+02:00
- summary: Refines the guard on `isArray`, `key` in lib/helpers/buildUrl.js without changing what the branches do.

- (no findings reported)

## axios__axios e8cf487ad0f5  (javascript)
- subject: Removing es6-promise dependency
- files: lib/axios.js, package.json, test/specs/promise.spec.js
- date: 2015-07-23T10:43:17-07:00
- summary: Refines the guard on `P`, `require` in lib/axios.js without changing what the branches do.

- (no findings reported)

## axios__axios 22ce6db383bc  (javascript)
- subject: Adding request to error objects when it is available
- files: lib/adapters/http.js, lib/adapters/xhr.js, lib/core/createError.js, lib/core/enhanceError.js, lib/core/settle.js
- date: 2017-04-08T21:44:15+02:00
- summary: Refines the guard on `createError`, `reject` in lib/adapters/http.js without changing what the branches do.

- (no findings reported)

## clap-rs__clap f8bca3a84bd5  (rust)
- subject: fix(error): Never show unrequested color
- files: src/parse/errors.rs
- date: 2021-10-26T14:26:50-05:00
- summary: src/parse/errors.rs grows `Colorizer`, `new`; the file's existing entry points are untouched.

- (no findings reported)

## clap-rs__clap 479ca76491a7  (rust)
- subject: fix: Always ensure `num_args` is initialized
- files: src/builder/arg.rs, src/builder/debug_asserts.rs
- date: 2022-08-04T09:11:29-05:00
- summary: Adds `get_value_names`, `unwrap_or`, `len` as a new definition in src/builder/arg.rs; existing callers keep their previous entry points.

- (no findings reported)

## clap-rs__clap edabdf72b59b  (rust)
- subject: fix(complete): Only return imidiate child subcommands
- files: clap_complete/src/dynamic/completer.rs
- date: 2023-07-28T14:51:56-05:00
- summary: Refines the guard on `all_subcommands`, `subcommands` in clap_complete/src/dynamic/completer.rs without changing what the branches do.

- (no findings reported)

## clap-rs__clap a126149a809f  (rust)
- subject: refactor(complete): Remove redundant dedup
- files: clap_complete/src/engine/complete.rs
- date: 2024-09-20T13:59:16-05:00
- summary: Refines the guard on `dedup` in clap_complete/src/engine/complete.rs without changing what the branches do.

- (no findings reported)

## clap-rs__clap 931b6338f125  (rust)
- subject: refactor(parser): Clarify FromStr from future FromStr
- files: src/builder/value_parser.rs
- date: 2022-09-26T09:51:03-05:00
- summary: Refines the guard on `_ValueParserViaParse`, `fn` in src/builder/value_parser.rs without changing what the branches do.

- (no findings reported)

## clap-rs__clap 9d07b3c02837  (rust)
- subject: feat(parser): non-empty string ValueParser
- files: src/builder/mod.rs, src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: Adds `NonEmptyStringValueParser`, `parse_ref` to src/builder/mod.rs as additional surface rather than a change to existing surface.

- (no findings reported)

## clap-rs__clap a7a8f93d6b2b  (rust)
- subject: fix(complete): Strip wrappers for running completer
- files: clap_complete/examples/exhaustive.rs, clap_complete/src/env/mod.rs
- date: 2024-09-17T15:47:46-05:00
- summary: Refines the guard on `completer`, `with_factory` in clap_complete/examples/exhaustive.rs without changing what the branches do.

- (no findings reported)

## clap-rs__clap f9be3215c189  (rust)
- subject: refactor(parser): Minor clean up
- files: src/builder/value_parser.rs
- date: 2022-05-16T15:08:47-05:00
- summary: Adds `parser`, `AutoValueParser` to src/builder/value_parser.rs as additional surface rather than a change to existing surface.

- (no findings reported)

## fastapi__fastapi 9b35d355bfb4  (python)
- subject: 📝 Update `docs_src/path_params_numeric_validations/tutorial006.py` (#11478)
- files: docs_src/path_params_numeric_validations/tutorial006.py, docs_src/path_params_numeric_validations/tutorial006_an.py, docs_src/path_params_numeric_validations/tutorial006_an_py39.py
- date: 2024-08-28T18:39:15-05:00
- summary: Reworks conditional handling for `update` in docs_src/path_params_numeric_validations/tutorial006.py within the existing structure.

- (no findings reported)

## fastapi__fastapi d11f820ac38b  (python)
- subject: 📝 Update docs for JWT to prevent timing attacks (#14908)
- files: docs/en/docs/tutorial/security/oauth2-jwt.md, docs_src/security/tutorial004_an_py310.py, docs_src/security/tutorial004_py310.py, docs_src/security/tutorial005_an_py310.py, docs_src/security/tutorial005_py310.py
- date: 2026-02-12T19:10:35+01:00
- summary: Adds `DUMMY_HASH`, `verify_password`, `hash` as a new definition in docs/en/docs/tutorial/security/oauth2-jwt.md; existing callers keep their previous entry points.

- (no findings reported)

## fastapi__fastapi 6cc24416e228  (python)
- subject: ✏️ Fix docstring typos in http security (#12223)
- files: fastapi/security/http.py
- date: 2024-09-19T11:47:28+02:00
- summary: Reorders the assignments around `Doc` in fastapi/security/http.py inside the same block.

- (no findings reported)

## fastapi__fastapi 31887b1cc6fb  (python)
- subject: 🔖 Release version 0.115.4
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2024-10-27T21:51:55Z
- summary: Reworks conditional handling for `version` in docs/en/docs/release-notes.md within the existing structure.

- (no findings reported)

## fastapi__fastapi c7e7b651d694  (python)
- subject: 🔖 Release version 0.141.0 (#16103)
- files: docs/en/docs/release-notes.md, fastapi/__init__.py
- date: 2026-07-29T14:45:21Z
- summary: Reworks conditional handling for `version` in docs/en/docs/release-notes.md within the existing structure.

- (no findings reported)

## fastapi__fastapi 91a929319c4c  (python)
- subject: ♻️ Update internal checks to support Pydantic 2.10 (#12914)
- files: fastapi/_compat.py, fastapi/params.py
- date: 2024-11-12T17:10:42+01:00
- summary: Refines the guard on `tuple`, `int` in fastapi/_compat.py without changing what the branches do.

- (no findings reported)

## fastapi__fastapi 3611c3fc5b82  (python)
- subject: ⬆️ Add support for Python 3.14 (#14165)
- files: .github/workflows/test.yml, pyproject.toml, requirements-tests.txt, tests/test_tutorial/test_sql_databases/test_tutorial001.py, tests/test_tutorial/test_sql_databases/test_tutorial002.py
- date: 2025-10-10T11:44:39+02:00
- summary: Adds `dispose` as a new definition in .github/workflows/test.yml; existing callers keep their previous entry points.

- (no findings reported)

## fastapi__fastapi 2260afaf4331  (python)
- subject: 🐛 Fix failing test, update format for raised errors (#15804)
- files: fastapi/routing.py
- date: 2026-06-20T00:51:31Z
- summary: Reorders the assignments around `get_resolved_absolute_path` in fastapi/routing.py inside the same block.

- (no findings reported)

## gin-gonic__gin dbd8a2515093  (go)
- subject: feat: added `AbortWithStatusPureJSON()` in `Context` (#4290)
- files: context.go, context_test.go
- date: 2025-07-13T09:40:35+08:00
- summary: Adds `AbortWithStatusPureJSON`, `TestContextAbortWithStatusPureJSON` as a new definition in context.go; existing callers keep their previous entry points.

- (no findings reported)

## gin-gonic__gin a48f83c9a1a1  (go)
- subject: Adding helper functions to router group for LINK and UNLINK.
- files: routergroup.go
- date: 2014-12-15T13:19:51-04:00
- summary: Refines the guard on `LINK`, `UNLINK` in routergroup.go without changing what the branches do.

- (no findings reported)

## gin-gonic__gin ce2201c39214  (go)
- subject: router.Run() can be called without parameters. #405
- files: gin.go, gin_integration_test.go, utils.go
- date: 2015-08-16T16:19:51+02:00
- summary: Refines the guard on `TestRun`, `testRequest` in gin.go without changing what the branches do.

- (no findings reported)

## gin-gonic__gin 34b1d0262e37  (go)
- subject: Refactors response_writer.go
- files: response_writer.go
- date: 2015-03-23T04:45:33+01:00
- summary: Refines the guard on `NoWritten`, `DefaultStatus` in response_writer.go without changing what the branches do.

- (no findings reported)

## gin-gonic__gin 80f691159fa5  (go)
- subject: Added simple testing documentation and examples (#1156)
- files: README.md, examples/basic/main.go, examples/basic/main_test.go
- date: 2017-11-11T23:37:32-06:00
- summary: Adds `setupRouter`, `main` to README.md as additional surface rather than a change to existing surface.

- (no findings reported)

## gin-gonic__gin e198f6e85922  (go)
- subject: refactor(render): remove headers parameter from writeHeader (#4353)
- files: render/reader.go
- date: 2025-09-19T08:39:17+08:00
- summary: Refines the guard on `writeHeaders`, `range` in render/reader.go without changing what the branches do.

- (no findings reported)

## gin-gonic__gin 1d462bbe3713  (go)
- subject: chore: update ginS (#1822)
- files: ginS/gins.go
- date: 2019-03-21T15:12:06+08:00
- summary: Reworks conditional handling for `Routes`, `Run` in ginS/gins.go within the existing structure.

- (no findings reported)

## gin-gonic__gin 4194adce4cd5  (go)
- subject: Adds additional bindings for multipart and form
- files: binding/binding.go, binding/binding_test.go, binding/form.go
- date: 2015-07-03T04:20:00+02:00
- summary: Adds `createFormPostRequest`, `createFormMultipartRequest` as a new definition in binding/binding.go; existing callers keep their previous entry points.

- (no findings reported)

## spring-projects__spring-boot e680142dd4c0  (java)
- subject: Update Gradle conventions to ensure Eclipse IDE defaults to JRE 17
- files: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java, buildSrc/src/main/java/org/springframework/boot/build/SystemRequirementsExtension.java
- date: 2026-01-21T21:03:26-08:00
- summary: buildSrc/src/main/java/org/springframework/boot/build/JavaConventions.java grows `JavaPluginExtension`, `JavaVersion`; the file's existing entry points are untouched.

- (no findings reported)

## spring-projects__spring-boot 2d4baa3305ed  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-test-nomockito
- files: smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java
- date: 2025-08-13T11:50:54+02:00
- summary: Adds `NullMarked`, `package` as a new definition in smoke-test/spring-boot-smoke-test-test-nomockito/src/main/java/smoketest/testnomockito/package-info.java; existing callers keep their previous entry points.

- (no findings reported)

## spring-projects__spring-boot 3ebc8653d583  (java)
- subject: Polish "Add server-side support for custom gRPC conventions"
- files: module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java
- date: 2026-03-25T10:47:41+01:00
- summary: Adds `whenCustomConventionBeanIsPresentThenInterceptorUsesIt`, `mock` as a new definition in module/spring-boot-grpc-server/src/test/java/org/springframework/boot/grpc/server/autoconfigure/GrpcServerObservationAutoConfigurationTests.java; existing callers keep their previous entry points.

- (no findings reported)

## spring-projects__spring-boot abec26e504fa  (java)
- subject: Polish
- files: documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientAssertJTests.java, documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withrunningserver/MyRandomPortRestTestClientTests.java
- date: 2026-01-21T10:06:02-08:00
- summary: Reworks conditional handling for `testWithRestTestClient`, `testWithRestTestClientAssertJ` in documentation/spring-boot-docs/src/main/java/org/springframework/boot/docs/testing/springbootapplications/withmockenvironment/MyMockMvcTests.java within the existing structure.

- (no findings reported)

## spring-projects__spring-boot 866be19024c8  (java)
- subject: Add nullability annotations to tests in module/spring-boot-validation
- files: module/spring-boot-validation/build.gradle, module/spring-boot-validation/src/test/java/org/springframework/boot/validation/autoconfigure/ValidatorAdapterTests.java
- date: 2025-10-15T16:58:21+02:00
- summary: Adds `named`, `checking` to module/spring-boot-validation/build.gradle as additional surface rather than a change to existing surface.

- (no findings reported)

## spring-projects__spring-boot 118bf1012796  (java)
- subject: Add nullability annotations to tests in module/spring-boot-rsocket-test
- files: module/spring-boot-rsocket-test/build.gradle, module/spring-boot-rsocket-test/src/test/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPortTests.java
- date: 2025-10-13T13:44:26+02:00
- summary: Adds `named`, `checking` as a new definition in module/spring-boot-rsocket-test/build.gradle; existing callers keep their previous entry points.

- (no findings reported)

## spring-projects__spring-boot f28caee30d2e  (java)
- subject: Fix NestedJarFile.JarEntryInputStream's available() behavior
- files: spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java, spring-boot-project/spring-boot-tools/spring-boot-loader/src/test/java/org/springframework/boot/loader/jar/NestedJarFileTests.java
- date: 2025-09-05T17:29:22+01:00
- summary: Adds `readingToEndOfStoredContentCausesAvailableToReachZero`, `readingToEndOfDeflatedContentCausesAvailableToReachZero` as a new definition in spring-boot-project/spring-boot-tools/spring-boot-loader/src/main/java/org/springframework/boot/loader/jar/NestedJarFile.java; existing callers keep their previous entry points.

- (no findings reported)

## spring-projects__spring-boot fab69e444b29  (java)
- subject: Add nullability annotations to smoke-test/spring-boot-smoke-test-data-ldap
- files: smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java, smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/package-info.java
- date: 2025-08-13T11:32:14+02:00
- summary: Adds `Person`, `toString` to smoke-test/spring-boot-smoke-test-data-ldap/src/main/java/smoketest/data/ldap/Person.java as additional surface rather than a change to existing surface.

- (no findings reported)
