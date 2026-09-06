# BugsInPy invention packet

All 60 explanations the rubric flagged as asserting a
failure that did not happen, across all three arms. This is the whole
population, not a sample: the claim they support (2% for the arm given
measured values, 11% for the arm given only a risk score) is the
difference between these rows and nothing else.

For each: does the explanation assert a failure the measurement
contradicts or never showed?

- `y` — yes, it names an exception or outcome that did not happen
- `n` — no, the rubric is wrong here; the named failure IS in the
  measurement, or the sentence is hedged enough not to assert it

The arm each row came from is shown, because it is not blindable --
the prompt differs visibly. What is withheld is which class the rubric
thought was invented.

Record as `id,invented` in `bip_inventions.csv`, then:

    python bench/bugsinpy_rater.py --score /home/arp/Documents/oracle/data/bip_inventions.csv --arm exec

---

## 1. `httpie-1`  (httpie, arm `exec`)

**Commit message:** Fixed #451 - OSError: [Errno 36] File name too long

**Measured before:** `AttributeError: <module 'httpie.downloads' from '<repo>/httpie/downloads.py'> does not have the attribute 'get_filename_max_length'`

**Measured after:**  `11 passed`

**The model said:** The `get_filename_max_length` function was added to calculate the maximum file name length for the current directory, which resolves the `OSError: [Errno 36] File name too long` issue when attempting to create files with names exceeding the system's limit.

`httpie-1` — invented: ____

---

## 2. `black-1`  (black, arm `exec`)

**Commit message:** permits black to run in AWS Lambda: (#1141)

**Measured before:** `AssertionError: 1 != 0 :`

**Measured after:**  `OK`

**The model said:** The commit adds a try/except block to handle the `OSError` that occurs when trying to create a `ProcessPoolExecutor` on systems that do not support multi-processing, such as AWS Lambda. This change ensures that the program can still run without crashing, and the test output changes from an assertion error to "OK".

`black-1` — invented: ____

---

## 3. `spacy-1`  (spacy, arm `exec`)

**Commit message:** Fix ErrorsWithCodes().__class__ return value

**Measured before:** `assert False`

**Measured after:**  `1 passed`

**The model said:** The `ErrorsWithCodes` class now includes a check for attribute names starting with `__`, which prevents the `AttributeError` when accessing private attributes. This change allows the project's own tests to pass again, as the assertion was previously failing.

`spacy-1` — invented: ____

---

## 4. `matplotlib-25`  (matplotlib, arm `exec`)

**Commit message:** Backport PR #14488: Make sure EventCollection doesn't modify input in-place

**Measured before:** `AssertionError:`

**Measured after:**  `1 passed`

**The model said:** The change adds a check for `positions` being `None` and raises a `ValueError` if so, ensuring that the input is always an array-like object. This prevents the original assertion error from failing, which now passes instead.

`matplotlib-25` — invented: ____

---

## 5. `youtube-dl-9`  (youtube-dl, arm `exec`)

**Commit message:** [YoutubeDL] format spec: Fix handling of '+' with '/'

**Measured before:** `ExtractorError: requested format not available`

**Measured after:**  `OK`

**The model said:** The change removes the `endwith` parameter from the `_parse_format_selection` function, which was used to handle the closing parenthesis `)` separately. This simplifies the parsing logic by removing an unnecessary check, which resolves the `ExtracterError: requested format not available` issue when the closing parenthesis is encountered.

`youtube-dl-9` — invented: ____

---

## 6. `keras-9`  (keras, arm `exec`)

**Commit message:** Fix Arguments display in Docs (#12007)

**Measured before:** `AssertionError: assert '<p>Base clas...e output.</p>' == '<p>Base clas....</li>\n</ul>'`

**Measured after:**  `1 passed`

**The model said:** The change updates the slice endpoint in `process_list_block` to use `section_end` instead of `None` when `ending_point` is -1, which prevents an `IndexError` and resolves the test failure.

`keras-9` — invented: ____

---

## 7. `httpie-1`  (httpie, arm `score`)

**Commit message:** Fixed #451 - OSError: [Errno 36] File name too long

**Measured before:** `AttributeError: <module 'httpie.downloads' from '<repo>/httpie/downloads.py'> does not have the attribute 'get_filename_max_length'`

**Measured after:**  `11 passed`

**The model said:** The `filename_from_url` function was refactored into `trim_filename`, which reduces the file name length by truncating the base name rather than the extension. This change fixes the `OSError: [Errno 36] File name too long` issue by ensuring that the file name is within the system's maximum path length limit.

`httpie-1` — invented: ____

---

## 8. `ansible-1`  (ansible, arm `score`)

**Commit message:** better error for "ansible-galaxy collection verify" if there's no MANIFEST.json (#67498)

**Measured before:** `TypeError: 'GalaxyAPI' object is not iterable`

**Measured after:**  `1 passed`

**The model said:** The commit adds a check for the presence of a `MANIFEST.json` file in the collection directory, which is required for collections built and installed via `ansible-galaxy`. If the file is missing, an `AnsibleError` is raised, providing guidance on how to resolve the issue.

`ansible-1` — invented: ____

---

## 9. `ansible-13`  (ansible, arm `score`)

**Commit message:** Fix using a URL for galaxy collection install (#65272)

**Measured before:** `AssertionError: assert [('https', '/...ar.gz', None)] == [('https://fo...', '*', None)]`

**Measured after:**  `1 passed`

**The model said:** The commit removes the `dummy` variable from the `collection_input.partition(':')` call, which was used to extract the collection name from a string with a colon separator. This change simplifies the logic by removing an unnecessary intermediate step, but it also introduces a potential bug where the script may fail to handle URLs without a colon separator correctly. The commit adds error handling to catch `URLError` exceptions when downloading collections from URLs, which should prevent the program from crashing and instead report a more informative error message.

`ansible-13` — invented: ____

---

## 10. `ansible-14`  (ansible, arm `score`)

**Commit message:** Fix up role version pagination for Galaxy install (#64373)

**Measured before:** `AssertionError: assert 'https://gala...&page_size=50' == 'https://gala...&page_size=50'`

**Measured after:**  `2 passed`

**The model said:** The `urllib.parse.urljoin` function was replaced with a custom `_urljoin` function that strips the `/api` prefix from the `self.api_server` URL when constructing the next page link. This change addresses an issue where the pagination logic was incorrectly joining the base URL with the relative path in `data['next_link']`, causing the API request to fail with a `TypeError: expected string or bytes-like object, got 'NoneType'`. The warning message was updated to reflect the new behavior.

`ansible-14` — invented: ____

---

## 11. `black-1`  (black, arm `score`)

**Commit message:** permits black to run in AWS Lambda: (#1141)

**Measured before:** `AssertionError: 1 != 0 :`

**Measured after:**  `OK`

**The model said:** The commit adds a try/except block to handle the `OSError` that occurs when trying to create a `ProcessPoolExecutor` on systems that do not support multi-processing, such as AWS Lambda. This change ensures that the program can gracefully fallback to a single-threaded execution path without crashing, thus reducing the risk of defects by 23.3%.

`black-1` — invented: ____

---

## 12. `black-7`  (black, arm `score`)

**Commit message:** Add parentheses around tuple unpack assignment (#832)

**Measured before:** `AssertionError: '(\n    sdfjklsdfsjldkflkjsf,\n    sdfjsdf[81 chars]3)\n' != 'sdfjklsdfsjldkflkjsf, sdfjsdfjlksdljkfsdl[74 chars]n)\n'`

**Measured after:**  `OK`

**The model said:** The commit adds parentheses around long tuple unpacking in assignments, which fixes a `SyntaxError: invalid syntax` when the unpacked expression is too long. The defect predictor score remains 38.7%, indicating no change in risk.

`black-7` — invented: ____

---

## 13. `black-23`  (black, arm `score`)

**Commit message:** Automatic detection of deprecated Python 2 forms of print and exec

**Measured before:** `AssertionError: '#!/u[39 chars]nt >>sys.stderr, "Warning:",\nprint >>sys.stde[214 chars]))\n' != '#!/u[39 chars]nt >> sys.stderr, "Warning:",\nprint >> sys.st[217 chars]))\n'`

**Measured after:**  `OK`

**The model said:** The commit removes the `try/except` block that previously caught `ParseError` exceptions when parsing source files, which could lead to more informative error messages. The new error message includes details about the specific Python version and the AST error message, which helps users understand why the file cannot be parsed with the `--safe` flag. This change reduces the risk of defects by providing more context about the parsing failure.

`black-23` — invented: ____

---

## 14. `fastapi-7`  (fastapi, arm `score`)

**Commit message:** :bug: Fix issue with exotic pydantic error serialization (#748)

**Measured before:** `TypeError: Object of type Decimal is not JSON serializable`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `RequestValidationError` handler now uses `jsonable_encoder` to serialize the error details, which ensures that the response is JSON-compatible and avoids issues with non-serializable data types.

`fastapi-7` — invented: ____

---

## 15. `scrapy-2`  (scrapy, arm `score`)

**Commit message:** Fix scrapy.utils.datatypes.LocalCache limit issue

**Measured before:** `TypeError: '>=' not supported between instances of 'int' and 'NoneType'`

**Measured after:**  `OK`

**The model said:** The `LocalCache` class now includes a check for the `limit` attribute before attempting to pop items when the cache size exceeds the specified limit, which prevents the `IndexError: pop from empty list` failure observed in the test suite.

`scrapy-2` — invented: ____

---

## 16. `luigi-21`  (luigi, arm `score`)

**Commit message:** Merge pull request #1059 from Tarrasch/fix-luigi-run-use-case

**Measured before:** `AttributeError: 'NoneType' object has no attribute 'insert'`

**Measured after:**  `1 passed, 2 warnings`

**The model said:** The commit adds a default argument for `cmdline_args` in `run`, which prevents the program from crashing when no arguments are passed. This change fixes the `IndexError: list index out of range` failure observed in the project's own tests.

`luigi-21` — invented: ____

---

## 17. `spacy-1`  (spacy, arm `score`)

**Commit message:** Fix ErrorsWithCodes().__class__ return value

**Measured before:** `assert False`

**Measured after:**  `1 passed`

**The model said:** The `ErrorsWithCodes` class now includes a check for attribute names starting with `__`, which prevents the `getattr` call from raising an `AttributeError` when accessing private attributes. This change reduces the risk of runtime errors in the project's tests, which previously failed due to missing attribute values.

`spacy-1` — invented: ____

---

## 18. `thefuck-8`  (thefuck, arm `score`)

**Commit message:** Tests! Also fixed some bytes-string issues

**Measured before:** `assert 'dnf install vim' in []`

**Measured after:**  `2 passed`

**The model said:** The change replaces the bytes-style regex with a string-style regex in `_get_operations`, which removes the need for explicit decoding when reading from `proc.stdout`. This refactoring eliminates the risk of UnicodeDecodeError, which was previously causing the test to fail.

`thefuck-8` — invented: ____

---

## 19. `thefuck-26`  (thefuck, arm `score`)

**Commit message:** Support for either starting only the machine requested, or starting all machines

**Measured before:** `AssertionError: assert 'vagrant up  && vagrant ssh' == 'vagrant up && vagrant ssh'`

**Measured after:**  `4 passed, 1 warning`

**The model said:** The change replaces the literal `""` with `None` in the `machine` variable, which removes the empty string from the list returned by `get_new_command`. This refactoring eliminates the potential for a `TypeError` when the script is executed, as the empty string was causing the `and_` function to fail. The defect predictor score remains 8.8%, indicating that the change is still low-risk.

`thefuck-26` — invented: ____

---

## 20. `scrapy-12`  (scrapy, arm `score`)

**Commit message:** Merge pull request #2153 from Digenis/Selector_bad_args

**Measured before:** `FAIL: test_selector_bad_args (tests.test_selector.SelectorTestCase)`

**Measured after:**  `OK`

**The model said:** The commit adds a check to ensure that `response` and `text` cannot be provided simultaneously in the `__init__` method, which prevents the creation of a `Selector` instance with conflicting input types. This change fixes the TypeError: 'response' and 'text' cannot be specified together.

`scrapy-12` — invented: ____

---

## 21. `matplotlib-5`  (matplotlib, arm `score`)

**Commit message:** Correctly set default linewidth for unfilled markers.

**Measured before:** `assert array([1.]) == (1 + 1)`

**Measured after:**  `1 passed`

**The model said:** The default linewidth for unfilled markers was updated to use `rcParams['lines.linewidth']` instead of directly accessing the attribute, which prevents potential `AttributeError` failures when the attribute is `None`. This change reduces the defect risk to 9.5%.

`matplotlib-5` — invented: ____

---

## 22. `scrapy-17`  (scrapy, arm `score`)

**Commit message:** response_status_message should not fail on non-standard HTTP codes

**Measured before:** `TypeError: to_unicode must receive a bytes, str or unicode object, got NoneType`

**Measured after:**  `OK`

**The model said:** The `response_status_message` function now returns "Unknown Status" for non-standard HTTP codes instead of failing with a `KeyError`, which addresses the test failure by ensuring that the response message is always present.

`scrapy-17` — invented: ____

---

## 23. `scrapy-24`  (scrapy, arm `score`)

**Commit message:** https proxy tunneling - add a test (not perfect, but covers all impl) and fix for py3

**Measured before:** `DirtyReactorAggregateError: Reactor was unclean.`

**Measured after:**  `OK`

**The model said:** The response matcher in `TunnelingTCP4ClientEndpoint` was updated to use bytes literals instead of string literals, which fixes a compatibility issue with Python 3. This change ensures that the module can handle byte strings without raising a `UnicodeDecodeError`, thereby improving the project's test coverage and stability.

`scrapy-24` — invented: ____

---

## 24. `scrapy-30`  (scrapy, arm `score`)

**Commit message:** PY3 fix test cmdline

**Measured before:** `TypeError: can only concatenate str (not "bytes") to str`

**Measured after:**  `OK`

**The model said:** The change replaces the string concatenation `self.out + self.err` with `self.out.decode(encoding) + self.err.decode(encoding)` to ensure that the output is decoded before concatenation, which resolves a UnicodeDecodeError when running the project's tests on Python 3. This defect was identified by the Just-In-Time defect model as having a 98.0% risk of introducing a defect.

`scrapy-30` — invented: ____

---

## 25. `scrapy-34`  (scrapy, arm `score`)

**Commit message:** item fields defined on fields class attribute fix

**Measured before:** `AssertionError: {'load': {'default': 'D'}, 'save': {'default': 'C'}} != {'save': {'default': 'C'}, 'load': {'default': 'D'}, 'update': {'default': 'D'}}`

**Measured after:**  `OK`

**The model said:** The `fields` dictionary was replaced with a direct access to the `fields` attribute using `getattr`, which removes the risk of a `KeyError` when accessing the `fields` attribute. This change is safe and does not alter the project's own tests, which still pass.

`scrapy-34` — invented: ____

---

## 26. `youtube-dl-4`  (youtube-dl, arm `score`)

**Commit message:** [jsinterp] Fix function calls without arguments.

**Measured before:** `ExtractorError: Unsupported JS expression 'x()'; please report this issue on https://yt-dl.org/bug . Make sure you are using the latest version; see  https://yt-dl.org/update  on how to update. Be sure to call youtube-dl with the --verbose flag and include its complete output.`

**Measured after:**  `OK`

**The model said:** The change removes the trailing comma from the argument list in the regular expression, which allows the parser to handle cases where the argument list is empty. This fix resolves the `IndexError: list index out of range` error when calling functions without arguments, ensuring that the project's own tests continue to pass.

`youtube-dl-4` — invented: ____

---

## 27. `matplotlib-25`  (matplotlib, arm `score`)

**Commit message:** Backport PR #14488: Make sure EventCollection doesn't modify input in-place

**Measured before:** `AssertionError:`

**Measured after:**  `1 passed`

**The model said:** The commit adds a check for `positions` being `None` and raises a `ValueError` if it is, ensuring that the function signature remains consistent with the previous behavior. This change prevents the modification of the input in-place, which was previously allowed by default, and ensures that the project's own tests continue to pass without any failures.

`matplotlib-25` — invented: ____

---

## 28. `youtube-dl-7`  (youtube-dl, arm `score`)

**Commit message:** [utils:js_to_json] Fix bad escape in double quoted strings

**Measured before:** `AssertionError: '"The CW\\\'s \\\'Crazy Ex-Girlfriend\\\'"' != '"The CW\'s \'Crazy Ex-Girlfriend\'"'`

**Measured after:**  `OK`

**The model said:** The change replaces the literal backslash escape `"` with the string literal escape `\'` inside single-quoted strings, which fixes the failure to correctly parse the JSON output when the input contains escaped single quotes. This ensures that the project's own tests no longer fail with the error `JSONDecodeError: Invalid control character at position 20`.

`youtube-dl-7` — invented: ____

---

## 29. `youtube-dl-16`  (youtube-dl, arm `score`)

**Commit message:** [utils] Use bytes-like objects in dfxp2srt

**Measured before:** `TypeError: a bytes-like object is required, not 'str'`

**Measured after:**  `OK`

**The model said:** The `io.open` call was updated to use binary mode (`'rb'`) instead of text mode (`'rt'`), which changes the encoding parameter from `'utf-8'` to `None`. This modification fixes the `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 1: invalid start byte` when processing DFXP files, as the input data is no longer decoded from UTF-8.

`youtube-dl-16` — invented: ____

---

## 30. `youtube-dl-17`  (youtube-dl, arm `score`)

**Commit message:** [utils] Skip missing params in cli_bool_option (closes #13865)

**Measured before:** `FAIL: test_cli_bool_option (test.test_utils.TestUtil)`

**Measured after:**  `OK`

**The model said:** The commit adds a check for `param` being `None`, returning an empty list instead of raising a `KeyError`. This prevents the project's own tests from failing when the required parameter is missing, which was previously causing a `KeyError`.

`youtube-dl-17` — invented: ____

---

## 31. `youtube-dl-21`  (youtube-dl, arm `score`)

**Commit message:** [utils] Process bytestrings in urljoin (closes #12369)

**Measured before:** `AssertionError: None != 'http://foo.de/a/b/c.txt'`

**Measured after:**  `OK`

**The model said:** The commit adds a `bytes` decoding step to the `urljoin` function, which ensures that byte strings passed as paths are properly decoded before being joined with the base URL. This change resolves a potential UnicodeDecodeError when passing byte strings to `urljoin`, which was previously causing the project's own tests to fail.

`youtube-dl-21` — invented: ____

---

## 32. `matplotlib-29`  (matplotlib, arm `score`)

**Commit message:** Backport PR #14598: Fix inversion of shared axes.

**Measured before:** `assert False`

**Measured after:**  `1 passed`

**The model said:** The `set_view_interval` method was removed from the `Axis` class, which causes the `set_inverted` method to raise a `NotImplementedError`. This change ensures that shared axes are updated when the view interval is inverted, but it also removes the ability to directly invert the axis limits via `set_view_interval`, which may lead to unexpected behavior in some applications.

`matplotlib-29` — invented: ____

---

## 33. `youtube-dl-30`  (youtube-dl, arm `score`)

**Commit message:** [YoutubeDL] format spec: Do not fail when a filter gives an empty result

**Measured before:** `IndexError: list index out of range`

**Measured after:**  `OK`

**The model said:** The change adds a check to ensure that the `formats` list is non-empty before attempting to iterate over it, which prevents the program from crashing when the filter returns an empty list. This addresses the issue of failing when a filter gives an empty result, which was previously causing the program to exit with a `RuntimeError: generator returned nothing`.

`youtube-dl-30` — invented: ____

---

## 34. `pandas-10`  (pandas, arm `score`)

**Commit message:** BUG: Fix Series.update ExtensionArray issue (#33984)

**Measured before:** `ValueError: NumPy boolean array indexing assignment cannot assign 2 input values to the 1 output values where the mask is true`

**Measured after:**  `3 passed`

**The model said:** The change replaces `isinstance(new, np.ndarray)` with `isinstance(new, (np.ndarray, ExtensionArray))` in the `ExtensionBlock` class, which allows the method to accept `ExtensionArray` objects as well as `numpy.ndarray`. This modification resolves a TypeError that occurs when an `ExtensionArray` is passed instead of a `numpy.ndarray`, ensuring that the project's own tests continue to pass without interruption.

`pandas-10` — invented: ____

---

## 35. `keras-9`  (keras, arm `score`)

**Commit message:** Fix Arguments display in Docs (#12007)

**Measured before:** `AssertionError: assert '<p>Base clas...e output.</p>' == '<p>Base clas....</li>\n</ul>'`

**Measured after:**  `1 passed`

**The model said:** The change updates the slice endpoint in `process_list_block` to use `section_end` instead of `None` when `ending_point` is -1, which prevents an IndexError by ensuring the slice always has a valid end point. This fix resolves the test failure where the slice index was out of bounds, causing the program to crash.

`keras-9` — invented: ____

---

## 36. `httpie-1`  (httpie, arm `diff`)

**Commit message:** Fixed #451 - OSError: [Errno 36] File name too long

**Measured before:** `AttributeError: <module 'httpie.downloads' from '<repo>/httpie/downloads.py'> does not have the attribute 'get_filename_max_length'`

**Measured after:**  `11 passed`

**The model said:** The `trim_filename` function was added to truncate filenames if they exceed the system's maximum path length, which resolves the `OSError: [Errno 36] File name too long` issue in the `get_unique_filename` function.

`httpie-1` — invented: ____

---

## 37. `ansible-1`  (ansible, arm `diff`)

**Commit message:** better error for "ansible-galaxy collection verify" if there's no MANIFEST.json (#67498)

**Measured before:** `TypeError: 'GalaxyAPI' object is not iterable`

**Measured after:**  `1 passed`

**The model said:** The commit adds a check for the presence of a `MANIFEST.json` file in the collection directory before attempting to load it. If the file is missing, an `AnsibleError` is raised, providing guidance on how to resolve the issue by ensuring the collection has been built and installed via `ansible-galaxy`.

`ansible-1` — invented: ____

---

## 38. `ansible-13`  (ansible, arm `diff`)

**Commit message:** Fix using a URL for galaxy collection install (#65272)

**Measured before:** `AssertionError: assert [('https', '/...ar.gz', None)] == [('https://fo...', '*', None)]`

**Measured after:**  `1 passed`

**The model said:** The commit removes the `dummy` variable from the `collection_input.partition(':')` call, which was used to extract the collection name from a string with a colon separator. This change simplifies the logic by removing an unnecessary intermediate step, but it also adds error handling to the `_download_file` call when downloading collections from URLs. The new error handling ensures that the script raises an `AnsibleError` with a descriptive message if the download fails, which helps developers diagnose issues more effectively.

`ansible-13` — invented: ____

---

## 39. `black-1`  (black, arm `diff`)

**Commit message:** permits black to run in AWS Lambda: (#1141)

**Measured before:** `AssertionError: 1 != 0 :`

**Measured after:**  `OK`

**The model said:** The commit adds a try/except block to handle the `OSError` that occurs when trying to create a `ProcessPoolExecutor` on systems that do not support multi-processing, such as AWS Lambda. This change ensures that the program can gracefully fallback to a single-threaded execution model without crashing, preserving the project's own tests that observe the correct behavior.

`black-1` — invented: ____

---

## 40. `luigi-4`  (luigi, arm `diff`)

**Commit message:** Allow NoneType columns in Redshift COPY job (#2303)

**Measured before:** `TypeError: object of type 'NoneType' has no len()`

**Measured after:**  `1 passed, 31 warnings`

**The model said:** The change removes the `len(self.columns) > 0` check from the `colnames` construction, allowing the loop to skip the empty list case. This eliminates the `IndexError: list index out of range` failure when the `columns` attribute is `None`.

`luigi-4` — invented: ____

---

## 41. `black-7`  (black, arm `diff`)

**Commit message:** Add parentheses around tuple unpack assignment (#832)

**Measured before:** `AssertionError: '(\n    sdfjklsdfsjldkflkjsf,\n    sdfjsdf[81 chars]3)\n' != 'sdfjklsdfsjldkflkjsf, sdfjsdfjlksdljkfsdl[74 chars]n)\n'`

**Measured after:**  `OK`

**The model said:** The change adds parentheses around long tuple unpacking in assignments, which fixes the `SyntaxError: invalid syntax` observed by the project's own tests.

`black-7` — invented: ____

---

## 42. `fastapi-7`  (fastapi, arm `diff`)

**Commit message:** :bug: Fix issue with exotic pydantic error serialization (#748)

**Measured before:** `TypeError: Object of type Decimal is not JSON serializable`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `RequestValidationError` handler now uses `jsonable_encoder` to serialize the errors, which ensures that the response is JSON-compliant and avoids issues with non-serializable data types.

`fastapi-7` — invented: ____

---

## 43. `fastapi-12`  (fastapi, arm `diff`)

**Commit message:** :bug: Fix HTTP Bearer security auto-error (#282)

**Measured before:** `assert 403 == 200`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `HTTPBearer` class now includes an `auto_error` flag that determines whether to raise an exception when the authentication scheme is invalid. If `auto_error` is set to `True`, the default behavior of raising an `HTTPException` is preserved; otherwise, the method returns `None`.

`fastapi-12` — invented: ____

---

## 44. `scrapy-2`  (scrapy, arm `diff`)

**Commit message:** Fix scrapy.utils.datatypes.LocalCache limit issue

**Measured before:** `TypeError: '>=' not supported between instances of 'int' and 'NoneType'`

**Measured after:**  `OK`

**The model said:** The `LocalCache` class now includes a check for the `limit` attribute before attempting to pop items when the cache size exceeds the specified limit, preventing the `IndexError: pop index out of range` failure.

`scrapy-2` — invented: ____

---

## 45. `sanic-2`  (sanic, arm `diff`)

**Commit message:** Add server.start_serving and server.serve_forever to AsyncioServer proxy object, to match asyncio-python3.7 example doc, fixes #1754 (#1762)

**Measured before:** `1 passed`

**Measured after:**  `1 passed`

**The model said:** Adds `start_serving` and `serve_forever` methods to the `AsyncioServer` proxy object, which mirror the corresponding methods in the asyncio Python 3.7 example documentation. This change ensures compatibility with newer versions of asyncio or uvloop by providing fallback implementations that raise `NotImplementedError` when the underlying server object does not support these methods.

`sanic-2` — invented: ____

---

## 46. `spacy-1`  (spacy, arm `diff`)

**Commit message:** Fix ErrorsWithCodes().__class__ return value

**Measured before:** `assert False`

**Measured after:**  `1 passed`

**The model said:** The `ErrorsWithCodes` class now includes a check for attribute names starting with `__`, which prevents the `AttributeError: 'ErrorsWithCodes' object has no attribute '__init__'` when accessing private attributes. This change ensures that the project's own tests continue to pass without errors.

`spacy-1` — invented: ____

---

## 47. `luigi-26`  (luigi, arm `diff`)

**Commit message:** Add a basic test for hadoop_jar.py

**Measured before:** `TypeError: expected str, bytes or os.PathLike object, not NoneType`

**Measured after:**  `1 passed, 2 warnings`

**The model said:** The commit adds a check to ensure that the `job.jar()` attribute is defined before attempting to access its path. This prevents the program from crashing when the jar file is not specified, instead raising a custom `HadoopJarJobError` with a descriptive message.

`luigi-26` — invented: ____

---

## 48. `thefuck-8`  (thefuck, arm `diff`)

**Commit message:** Tests! Also fixed some bytes-string issues

**Measured before:** `assert 'dnf install vim' in []`

**Measured after:**  `2 passed`

**The model said:** The change replaces the bytes-style regex with a string-style regex in `_get_operations`, which fixes the `UnicodeDecodeError` when reading the help text from `dnf --help`.

`thefuck-8` — invented: ____

---

## 49. `pandas-3`  (pandas, arm `diff`)

**Commit message:** BUG : Series.to_timestamp and Series.to_period raise user-facing AssertionError (#34067)

**Measured before:** `AssertionError`

**Measured after:**  `18 passed`

**The model said:** The `assert` statement in `Series.to_timestamp` and `Series.to_period` was replaced with a `TypeError` check, which raises an exception when the index is not a `PeriodIndex` or `DatetimeIndex`. This change ensures that the function now correctly handles unsupported index types by raising a user-facing error instead of failing silently.

`pandas-3` — invented: ____

---

## 50. `scrapy-9`  (scrapy, arm `diff`)

**Commit message:** Merge pull request #2331 from moisesguimaraes/fixes-2272

**Measured before:** `AttributeError: 'str' object has no attribute 'extend'`

**Measured after:**  `OK`

**The model said:** The `to` and `cc` arguments in `MailSender.send_mail` were updated to be lists instead of tuples, which allows for more flexibility when passing multiple recipients. This change resolves the TypeError: 'tuple' object is not iterable error observed in the project's own tests.

`scrapy-9` — invented: ____

---

## 51. `scrapy-12`  (scrapy, arm `diff`)

**Commit message:** Merge pull request #2153 from Digenis/Selector_bad_args

**Measured before:** `FAIL: test_selector_bad_args (tests.test_selector.SelectorTestCase)`

**Measured after:**  `OK`

**The model said:** The commit adds a check to ensure that the `response` and `text` arguments are mutually exclusive, raising a `ValueError` if both are provided. This prevents the `TypeError: 'Selector' object cannot be interpreted as an integer` that was previously observed when both arguments were passed.

`scrapy-12` — invented: ____

---

## 52. `scrapy-17`  (scrapy, arm `diff`)

**Commit message:** response_status_message should not fail on non-standard HTTP codes

**Measured before:** `TypeError: to_unicode must receive a bytes, str or unicode object, got NoneType`

**Measured after:**  `OK`

**The model said:** The `response_status_message` function now returns "Unknown Status" for non-standard HTTP codes instead of failing with a `KeyError`, which is a more robust approach that avoids breaking existing tests that rely on the default message. This change ensures that the project's own tests continue to pass without modification.

`scrapy-17` — invented: ____

---

## 53. `scrapy-24`  (scrapy, arm `diff`)

**Commit message:** https proxy tunneling - add a test (not perfect, but covers all impl) and fix for py3

**Measured before:** `DirtyReactorAggregateError: Reactor was unclean.`

**Measured after:**  `OK`

**The model said:** The response matcher was updated to use `bytes` literals instead of `str`, which fixes a UnicodeDecodeError when running on Python 3. This ensures that the test suite continues to pass without modification.

`scrapy-24` — invented: ____

---

## 54. `youtube-dl-4`  (youtube-dl, arm `diff`)

**Commit message:** [jsinterp] Fix function calls without arguments.

**Measured before:** `ExtractorError: Unsupported JS expression 'x()'; please report this issue on https://yt-dl.org/bug . Make sure you are using the latest version; see  https://yt-dl.org/update  on how to update. Be sure to call youtube-dl with the --verbose flag and include its complete output.`

**Measured after:**  `OK`

**The model said:** The change removes the trailing comma from the argument list regex, which allows the parser to handle cases where no arguments are provided by returning an empty tuple instead of raising a `ValueError`.

`youtube-dl-4` — invented: ____

---

## 55. `matplotlib-25`  (matplotlib, arm `diff`)

**Commit message:** Backport PR #14488: Make sure EventCollection doesn't modify input in-place

**Measured before:** `AssertionError:`

**Measured after:**  `1 passed`

**The model said:** The change adds a check for `positions` being `None` and raises a `ValueError` if it is, ensuring that the input is always an array-like object. This prevents the modification of the input in-place, which was previously allowed by removing the explicit copy statement.

`matplotlib-25` — invented: ____

---

## 56. `youtube-dl-30`  (youtube-dl, arm `diff`)

**Commit message:** [YoutubeDL] format spec: Do not fail when a filter gives an empty result

**Measured before:** `IndexError: list index out of range`

**Measured after:**  `OK`

**The model said:** The change removes the `list(formats)` conversion inside the `selector_function`, which prevents the function from returning an empty list when no formats match the selector. This ensures that the project's own tests continue to pass without raising a `TypeError`.

`youtube-dl-30` — invented: ____

---

## 57. `pandas-9`  (pandas, arm `diff`)

**Commit message:** BUG: CategoricalIndex.__contains__ incorrect NaTs (#33947)

**Measured before:** `AssertionError: assert numpy.timedelta64('NaT') not in [NaT, 2016-01-01, 2016-01-02, 2016-01-03, 2016-01-04, ..., 2016-04-05, 2016-04-06, 2016-04-07, 2016-04-08, 2016-04-09]...-01-02, 2016-01-03, 2016-01-04, ..., 2016-04-06,\n                                   2016-04-07, 2016-04-08, 2016-04-09]`

**Measured after:**  `2 passed`

**The model said:** The change replaces `hash(key)` with `is_valid_nat_for_dtype(key, self.categories.dtype)` in the `CategoricalIndex.__contains__` method, which ensures that the index correctly handles NaT values when checking for membership. This resolves a bug where the index would raise a `TypeError: unhashable type: 'NaT'` when attempting to check for membership with a NaT value.

`pandas-9` — invented: ____

---

## 58. `keras-8`  (keras, arm `diff`)

**Commit message:** Fixed loading bug for shared layers accross multiple depths (#11588)

**Measured before:** `ValueError: A `Concatenate` layer requires inputs with matching shapes except for the concat axis. Got inputs shapes: [(None, 12), (None, 1, 12)]`

**Measured after:**  `1 passed, 14 warnings`

**The model said:** The `process_node` function now raises a `LookupError` if the corresponding layer node has not yet been created, which prevents the program from crashing when attempting to process a node that requires an inbound layer that has not yet been built. This change ensures that the program can handle incomplete models without failing, allowing the user to debug and fix the issue.

`keras-8` — invented: ____

---

## 59. `keras-9`  (keras, arm `diff`)

**Commit message:** Fix Arguments display in Docs (#12007)

**Measured before:** `AssertionError: assert '<p>Base clas...e output.</p>' == '<p>Base clas....</li>\n</ul>'`

**Measured after:**  `1 passed`

**The model said:** The change updates the slice endpoint in `process_list_block` to use `section_end` instead of `None` when `ending_point` is -1, which prevents an IndexError by ensuring the slice always has a valid end point. This fix resolves the test failure where the list block was not properly extracted, causing the documentation generation to break.

`keras-9` — invented: ____

---

## 60. `pandas-11`  (pandas, arm `diff`)

**Commit message:** BUG: can't concatenate DataFrame with Series with duplicate keys (#33805)

**Measured before:** `TypeError: int() argument must be a string, a bytes-like object or a number, not 'slice'`

**Measured after:**  `2 passed`

**The model said:** The change replaces the `try-except` block with a direct lookup using `np.nonzero`, which removes the need for exception handling and simplifies the logic. This refactoring ensures that the error message is more informative by providing the exact index of the missing key instead of raising a generic `KeyError`.

`pandas-11` — invented: ____

---
