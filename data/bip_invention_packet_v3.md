# BugsInPy invention packet

All 59 explanations the rubric flagged as asserting a
failure that did not happen, across arms v3plain_v2, diff_v2, score_v2.

Every flagged row from the FIRST arm is here -- that is the arm the
headline depends on, and its inventions are the ones that would sink
it. The comparison arms are sampled where they flag more than the cap,
so the contrast they support is an estimate with a stated n.

For each: does the explanation assert a failure the measurement
contradicts or never showed?

- `y` — yes, it names an exception or outcome that did not happen
- `n` — no, the rubric is wrong here; the named failure IS in the
  measurement, or the sentence is hedged enough not to assert it

The arm each row came from is shown, because it is not blindable --
the prompt differs visibly. What is withheld is which class the rubric
thought was invented.

Record as `invented` against the matching `case` row in `bip_inventions_v3.csv` -- the case number, id and arm are already filled
in, so you only type y or n. Then:

    python bench/bugsinpy_rater.py --score data/bip_inventions_v3.csv --arm exec

---

## 1. `httpie-4`  (httpie, arm `v3plain_v2`)

**Commit message:** Fixed custom Host

**Measured before:** `assert 2 == 1`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The commit adds a check for the presence of the 'Host' header before setting it, which resolves the `AssertionError: assert 2 == 1` failure by ensuring the test passes.

`httpie-4` — invented: ____

---

## 2. `PySnooper-1`  (PySnooper, arm `v3plain_v2`)

**Commit message:** Fix unicode issues and add test, fix #124

**Measured before:** `1 passed, 2 warnings`

**Measured after:**  `1 passed, 2 warnings`

**The model said:** The commit adds an explicit `encoding='utf-8'` argument to the `open` call in `FileWriter.write`, which resolves the `UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 1: ordinal not in range(128)` failure observed in the test suite.

`PySnooper-1` — invented: ____

---

## 3. `cookiecutter-1`  (cookiecutter, arm `v3plain_v2`)

**Commit message:** Fix default values being loaded with wrong encoding on Windows (#1414)

**Measured before:** `1 passed`

**Measured after:**  `1 passed`

**The model said:** The `open` function in `generate.py` was updated to include the `encoding='utf-8'` argument, which resolves the `ValueError: Expecting value: line 1 column 1 (char 0)` failure observed when loading the context file on Windows.

`cookiecutter-1` — invented: ____

---

## 4. `fastapi-6`  (fastapi, arm `v3plain_v2`)

**Commit message:** :bug: Fix validating form params declared with classes (list, tuple, set, etc) (#856)

**Measured before:** `assert 422 == 200`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The change removes the `isinstance` check for `FormData` when determining whether to use `getlist` instead of `get` on form data, which resolves the `AssertionError: assert 422 == 200` failure.

`fastapi-6` — invented: ____

---

## 5. `keras-12`  (keras, arm `v3plain_v2`)

**Commit message:** Fix bug in sparse_categorical_accuracy  (#11373)

**Measured before:** `1 passed, 2 warnings`

**Measured after:**  `1 passed, 2 warnings`

**The model said:** The change removes the `tf.reduce_sum` call from the `sparse_categorical_accuracy` function, which resolves the failure where the output was `AssertionError: assert '0.5' == '0.6'`.

`keras-12` — invented: ____

---

## 6. `tornado-8`  (tornado, arm `v3plain_v2`)

**Commit message:** fix websocket handshake failure causes an exception

**Measured before:** `AssertionError: 500 != 400`

**Measured after:**  `OK`

**The model said:** The commit changes the `accept_connection` method to catch `ValueError` exceptions and respond with a 400 status code and a custom error message if the handshake fails, which resolves the previous failure where the server returned a 500 instead of a 400.

`tornado-8` — invented: ____

---

## 7. `tornado-15`  (tornado, arm `v3plain_v2`)

**Commit message:** Fix path traversal check in StaticFileHandler.

**Measured before:** `FAILED (errors=1)`

**Measured after:**  `OK`

**The model said:** The trailing slash was added to the `root` argument passed to `os.path.abspath`, which resolved the `AssertionError: 'root/...' is not in root static directory'` failure.

`tornado-15` — invented: ____

---

## 8. `keras-28`  (keras, arm `v3plain_v2`)

**Commit message:** fix TimeSeriesGenerator glitch (#9899)

**Measured before:** `assert 7 == 6`

**Measured after:**  `1 passed, 26 warnings`

**The model said:** The `TimeseriesGenerator` now raises a `ValueError` when `start_index + length > end_index`, which previously caused the test `assert 7 == 6` to fail.

`keras-28` — invented: ____

---

## 9. `pandas-92`  (pandas, arm `v3plain_v2`)

**Commit message:** BUG: PeriodIndex.searchsorted accepting invalid inputs (#30763)

**Measured before:** `assert False`

**Measured after:**  `1 passed`

**The model said:** The change replaces `ordinal` access with direct `Period` objects in `PeriodIndex.searchsorted`, which resolves the `AssertionError: assert False` failure by ensuring the correct frequency comparison logic is applied.

`pandas-92` — invented: ____

---

## 10. `scrapy-12`  (scrapy, arm `diff_v2`)

**Commit message:** Merge pull request #2153 from Digenis/Selector_bad_args

**Measured before:** `FAIL: test_selector_bad_args (tests.test_selector.SelectorTestCase)`

**Measured after:**  `OK`

**The model said:** The commit adds a check to ensure that the `response` and `text` arguments are mutually exclusive, raising a `ValueError` if both are provided. This prevents the `TypeError: 'Selector' object cannot be instantiated with both 'response' and 'text' arguments

`scrapy-12` — invented: ____

---

## 11. `pandas-78`  (pandas, arm `diff_v2`)

**Commit message:** BUG: Use self._constructor_sliced in df._reduce to respect subclassed… (#30945)

**Measured before:** `AssertionError: assert False`

**Measured after:**  `2 passed`

**The model said:** The `Series` constructor was replaced by `self._constructor_sliced`, which ensures that the resulting data structure respects any subclass-specific behavior defined by the `_constructor_sliced` method. This change fixes the test failure where the returned data type was not correctly inferred, causing the test to fail with an `IndexError: list index out of range`.

`pandas-78` — invented: ____

---

## 12. `keras-37`  (keras, arm `diff_v2`)

**Commit message:** Fix __call__ for Bidirectional wrapper (#9248)

**Measured before:** `assert 2 == 4`

**Measured after:**  `1 passed, 27 warnings`

**The model said:** The `Bidirectional` wrapper now checks if the `initial_state` passed to the layer is a list, raising a `ValueError` if it is not. This ensures that the state is correctly specified as a list of state tensors for each underlying RNN, which was previously allowed but not explicitly documented.

`keras-37` — invented: ____

---

## 13. `sanic-2`  (sanic, arm `diff_v2`)

**Commit message:** Add server.start_serving and server.serve_forever to AsyncioServer proxy object, to match asyncio-python3.7 example doc, fixes #1754 (#1762)

**Measured before:** `1 passed`

**Measured after:**  `1 passed`

**The model said:** The `start_serving` and `serve_forever` methods were added to the `AsyncioServer` proxy object, which matches the asyncio Python 3.7 example documentation. This change fixes issue #1754 by providing a more explicit way to start the server, which was previously implicit through the `__await__` method. Additionally, the error handling was updated to catch `AttributeError` instead of `NotImplementedError`, which is a more specific exception that can occur when the underlying server implementation does not support these methods.

`sanic-2` — invented: ____

---

## 14. `pandas-80`  (pandas, arm `diff_v2`)

**Commit message:** BUG: Series/Frame invert dtypes (#31183)

**Measured before:** `AssertionError: Attributes of Series are different`

**Measured after:**  `2 passed`

**The model said:** The `__invert__` method was added to the `BaseMaskedArray` class, which allows the inversion of boolean arrays using the `~` operator. This change fixes the failure observed in the `pandas/tests/arrays/test_boolean.py` file, where the `BooleanArray` constructor was failing with a `TypeError` when passed a list instead of a boolean numpy array.

`pandas-80` — invented: ____

---

## 15. `spacy-1`  (spacy, arm `diff_v2`)

**Commit message:** Fix ErrorsWithCodes().__class__ return value

**Measured before:** `assert False`

**Measured after:**  `1 passed`

**The model said:** The `ErrorsWithCodes` class now includes a check for attribute names starting with `__`, which prevents the `AttributeError: 'ErrorsWithCodes' object has no attribute '__init__'` when accessing private attributes. This change ensures that the project's own tests continue to pass without errors.

`spacy-1` — invented: ____

---

## 16. `httpie-1`  (httpie, arm `diff_v2`)

**Commit message:** Fixed #451 - OSError: [Errno 36] File name too long

**Measured before:** `AttributeError: <module 'httpie.downloads' from '<repo>/httpie/downloads.py'> does not have the attribute 'get_filename_max_length'`

**Measured after:**  `11 passed`

**The model said:** The `trim_filename` function was added to truncate filenames if they exceed the system's maximum path length, which resolves the `OSError: [Errno 36] File name too long` issue in the `get_unique_filename` function.

`httpie-1` — invented: ____

---

## 17. `scrapy-24`  (scrapy, arm `diff_v2`)

**Commit message:** https proxy tunneling - add a test (not perfect, but covers all impl) and fix for py3

**Measured before:** `DirtyReactorAggregateError: Reactor was unclean.`

**Measured after:**  `OK`

**The model said:** The response matcher was updated to use `bytes` literals instead of `str`, which fixes a UnicodeDecodeError when running on Python 3. This ensures that the test suite continues to pass without modification.

`scrapy-24` — invented: ____

---

## 18. `pandas-3`  (pandas, arm `diff_v2`)

**Commit message:** BUG : Series.to_timestamp and Series.to_period raise user-facing AssertionError (#34067)

**Measured before:** `AssertionError`

**Measured after:**  `18 passed`

**The model said:** The `assert` statement in `Series.to_timestamp` and `Series.to_period` was replaced with a `TypeError` check, which raises an exception when the index is not a `PeriodIndex` or `DatetimeIndex`. This change ensures that the function now correctly handles unsupported index types by raising a user-facing error instead of failing silently.

`pandas-3` — invented: ____

---

## 19. `pandas-135`  (pandas, arm `diff_v2`)

**Commit message:** BUG/TST: ensure groupby.agg preserves extension dtype (#29144)

**Measured before:** `AssertionError: Attributes of Series are different`

**Measured after:**  `1 passed`

**The model said:** The `TypeError` catch block was added to the `_aggregate_series_pure_python` method to handle the case where the input object's values are not an ndarray, which was causing the test to fail. This ensures that the function can still execute without raising an error when the input data type is not compatible with the pure Python aggregation logic.

`pandas-135` — invented: ____

---

## 20. `scrapy-9`  (scrapy, arm `diff_v2`)

**Commit message:** Merge pull request #2331 from moisesguimaraes/fixes-2272

**Measured before:** `AttributeError: 'str' object has no attribute 'extend'`

**Measured after:**  `OK`

**The model said:** The `to` and `cc` arguments in `MailSender.send_mail` were updated to be lists instead of tuples, which allows for more flexibility when passing multiple recipients. This change resolves the TypeError: 'tuple' object is not iterable error observed in the project's own tests.

`scrapy-9` — invented: ____

---

## 21. `fastapi-12`  (fastapi, arm `diff_v2`)

**Commit message:** :bug: Fix HTTP Bearer security auto-error (#282)

**Measured before:** `assert 403 == 200`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `HTTPBearer` class now includes an `auto_error` flag that determines whether to raise an exception when the authentication scheme is invalid. If `auto_error` is set to `True`, the default behavior of raising an `HTTPException` is preserved; otherwise, the method returns `None`.

`fastapi-12` — invented: ____

---

## 22. `pandas-77`  (pandas, arm `diff_v2`)

**Commit message:** BUG: na_logical_op 2D cases (#31263)

**Measured before:** `TypeError: unsupported operand type(s) for |: 'int' and 'float'`

**Measured after:**  `1 passed`

**The model said:** The change replaces `libops.vec_binop` with `libops.vec_binop(x.ravel(), y.ravel(), op)` to flatten the input arrays before performing the binary operation, which resolves a `ValueError: operands could not be broadcast together with shapes (1,) (2,)` in the test case `test_logical_op_2d`. The return statement now reshapes the result to match the original shape of `x`, ensuring the function's behavior remains consistent with the project's own tests.

`pandas-77` — invented: ____

---

## 23. `pandas-114`  (pandas, arm `diff_v2`)

**Commit message:** BUG: Index.get_value implementation for ExtensionArray (#29926)

**Measured before:** `Exception: tried to convert a DecimalArray to a numpy array`

**Measured after:**  `1 passed`

**The model said:** The change replaces direct attribute access with `extract_array`, which removes the need to check for `_values` and simplifies the logic by removing the special case for scalar keys. This refactoring eliminates the potential for `KeyError` when accessing non-scalar keys, which was previously handled by converting the key to a location and raising a `KeyError` if the index is empty or holds integers/booleans. The change also adds a new error message for non-scalar keys, which was previously caught by the conversion to a location.

`pandas-114` — invented: ____

---

## 24. `pandas-27`  (pandas, arm `diff_v2`)

**Commit message:** BUG: to_period() freq was not infered (#33406)

**Measured before:** `AttributeError: 'NoneType' object has no attribute 'n'`

**Measured after:**  `1 passed`

**The model said:** The `get_period_alias` function now returns a string representation of the frequency when it cannot be inferred, which resolves the issue where the `to_period` method failed to handle certain input formats like 'D' or 'W'. This change ensures that the `to_period` method can correctly convert datetime-like objects to period arrays without raising a `ValueError`.

`pandas-27` — invented: ____

---

## 25. `pandas-115`  (pandas, arm `diff_v2`)

**Commit message:** BUG: fix Series.interpolate(method='index') with unsorted index (#29943)

**Measured before:** `AssertionError: Series are different`

**Measured after:**  `2 passed`

**The model said:** The change replaces `np.interp` with a sorted version of the interpolation logic, which fixes the `IndexError: invalid index to scalar variable.` when the input index is not sorted.

`pandas-115` — invented: ____

---

## 26. `youtube-dl-30`  (youtube-dl, arm `diff_v2`)

**Commit message:** [YoutubeDL] format spec: Do not fail when a filter gives an empty result

**Measured before:** `IndexError: list index out of range`

**Measured after:**  `OK`

**The model said:** The change removes the `list(formats)` conversion inside the `selector_function`, which prevents the function from returning an empty list when no formats match the selector. This ensures that the project's own tests continue to pass without raising a `TypeError`.

`youtube-dl-30` — invented: ____

---

## 27. `tornado-8`  (tornado, arm `diff_v2`)

**Commit message:** fix websocket handshake failure causes an exception

**Measured before:** `AssertionError: 500 != 400`

**Measured after:**  `OK`

**The model said:** The commit adds a `try/except` block to catch `ValueError` exceptions in the `accept_connection` method of `WebSocketProtocol13`. If a `ValueError` is caught, the handler sets the status to 400, finishes the connection with a log message indicating missing/invalid WebSocket headers, and logs the message at debug level.

`tornado-8` — invented: ____

---

## 28. `matplotlib-25`  (matplotlib, arm `diff_v2`)

**Commit message:** Backport PR #14488: Make sure EventCollection doesn't modify input in-place

**Measured before:** `AssertionError:`

**Measured after:**  `1 passed`

**The model said:** The change adds a check for `positions` being `None` and raises a `ValueError` if it is, ensuring that the function now requires a valid array-like object. This prevents the program from crashing when `positions` is not provided, which was previously possible due to the lack of explicit validation.

`matplotlib-25` — invented: ____

---

## 29. `luigi-26`  (luigi, arm `diff_v2`)

**Commit message:** Add a basic test for hadoop_jar.py

**Measured before:** `TypeError: expected str, bytes or os.PathLike object, not NoneType`

**Measured after:**  `1 passed, 2 warnings`

**The model said:** The commit adds a check to ensure that the `job.jar()` attribute is defined before attempting to access its path. This prevents the program from crashing when the jar file is not specified, instead raising a custom `HadoopJarJobError` with a descriptive message.

`luigi-26` — invented: ____

---

## 30. `youtube-dl-4`  (youtube-dl, arm `diff_v2`)

**Commit message:** [jsinterp] Fix function calls without arguments.

**Measured before:** `ExtractorError: Unsupported JS expression 'x()'; please report this issue on https://yt-dl.org/bug . Make sure you are using the latest version; see  https://yt-dl.org/update  on how to update. Be sure to call youtube-dl with the --verbose flag and include its complete output.`

**Measured after:**  `OK`

**The model said:** The change removes the trailing comma from the argument list regex, which allows the parser to handle cases where no arguments are provided by returning an empty tuple instead of raising a `ValueError`.

`youtube-dl-4` — invented: ____

---

## 31. `pandas-96`  (pandas, arm `diff_v2`)

**Commit message:** BUG: bug in date_range with custom business hours and given periods (#30675)

**Measured before:** `ValueError`

**Measured after:**  `1 passed`

**The model said:** The `skip_bd` variable was updated to use `CustomBusinessDay` instead of `BusinessDay` when the offset is an instance of `_CustomMixin`, which adds support for custom business hours, holidays, and calendars. This change ensures that the test suite no longer fails with the error `TypeError: 'CustomBusinessDay' object is not iterable`.

`pandas-96` — invented: ____

---

## 32. `tqdm-5`  (tqdm, arm `diff_v2`)

**Commit message:** support `bool()` cast when `disable=True`

**Measured before:** `AttributeError: 'tqdm' object has no attribute 'total'`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The commit adds a check for `total` being `None` when `iterable` is not `None`, which attempts to infer the length of the iterable using `len()`. This prevents a `RuntimeError: object of type 'generator' has no len()` when `total` is not explicitly set, ensuring that the progress bar can still be displayed correctly.

`tqdm-5` — invented: ____

---

## 33. `pandas-11`  (pandas, arm `diff_v2`)

**Commit message:** BUG: can't concatenate DataFrame with Series with duplicate keys (#33805)

**Measured before:** `TypeError: int() argument must be a string, a bytes-like object or a number, not 'slice'`

**Measured after:**  `2 passed`

**The model said:** The change replaces the `try-except` block with a direct lookup using `np.nonzero`, which removes the need for exception handling and simplifies the logic. This refactoring ensures that the error message is more informative by providing the exact index of the missing key instead of raising a generic `KeyError`.

`pandas-11` — invented: ____

---

## 34. `pandas-129`  (pandas, arm `diff_v2`)

**Commit message:** BUG: np.datetime64 - TimedeltaArray (#29558)

**Measured before:** `ValueError: Unexpected type 'datetime64'. 'values' must be a DatetimeArray ndarray, or Series or Index containing one of those.`

**Measured after:**  `12 passed`

**The model said:** The change adds a special case for scalar `np.datetime64` objects, allowing them to be directly subtracted from `DatetimeArray` instances by wrapping them in `Timestamp` objects. This resolves the TypeError observed when attempting to subtract a scalar `np.datetime64` from a `DatetimeArray`.

`pandas-129` — invented: ____

---

## 35. `thefuck-8`  (thefuck, arm `score_v2`)

**Commit message:** Tests! Also fixed some bytes-string issues

**Measured before:** `assert 'dnf install vim' in []`

**Measured after:**  `2 passed`

**The model said:** The change replaces the bytes-style regex with a string-style regex in `_get_operations`, which removes the need for explicit decoding when reading from `proc.stdout`. This refactoring eliminates the risk of UnicodeDecodeError, which was previously causing the test to fail.

`thefuck-8` — invented: ____

---

## 36. `keras-37`  (keras, arm `score_v2`)

**Commit message:** Fix __call__ for Bidirectional wrapper (#9248)

**Measured before:** `assert 2 == 4`

**Measured after:**  `1 passed, 27 warnings`

**The model said:** The `Bidirectional` wrapper now checks if the initial state passed to it is a list, raising a `ValueError` if it is not. This ensures that the state is correctly specified as a list of state tensors, which is necessary for the layer to function properly.

`keras-37` — invented: ____

---

## 37. `pandas-135`  (pandas, arm `score_v2`)

**Commit message:** BUG/TST: ensure groupby.agg preserves extension dtype (#29144)

**Measured before:** `AssertionError: Attributes of Series are different`

**Measured after:**  `1 passed`

**The model said:** The commit adds a `try/except` block to catch `TypeError` exceptions when calling `_aggregate_series_pure_python`, which is triggered by non-array-like objects. This prevents the program from crashing and ensures that the project's own tests continue to observe the expected behavior.

`pandas-135` — invented: ____

---

## 38. `matplotlib-5`  (matplotlib, arm `score_v2`)

**Commit message:** Correctly set default linewidth for unfilled markers.

**Measured before:** `assert array([1.]) == (1 + 1)`

**Measured after:**  `1 passed`

**The model said:** The default linewidth for unfilled markers was updated to use `rcParams['lines.linewidth']` instead of directly accessing the attribute, which prevents potential `AttributeError` failures when the attribute is `None`. This change reduces the defect risk to 9.5%.

`matplotlib-5` — invented: ____

---

## 39. `youtube-dl-30`  (youtube-dl, arm `score_v2`)

**Commit message:** [YoutubeDL] format spec: Do not fail when a filter gives an empty result

**Measured before:** `IndexError: list index out of range`

**Measured after:**  `OK`

**The model said:** The change adds a check to ensure that the `formats` list is non-empty before attempting to iterate over it, which prevents the program from crashing when the filter returns an empty list. This addresses the issue of failing when a filter gives an empty result, which was previously causing the program to exit with a `RuntimeError: generator returned nothing`.

`youtube-dl-30` — invented: ____

---

## 40. `pandas-148`  (pandas, arm `score_v2`)

**Commit message:** BUG: Fix issue with apply on empty DataFrame (#28213)

**Measured before:** `AssertionError: Series are different`

**Measured after:**  `4 passed`

**The model said:** The commit replaces the direct instantiation of an empty `Series` with a call to `Series([])` inside the `try/except` block, which simplifies the logic and removes the need for the `EMPTY_SERIES` constant. This refactoring eliminates the potential for a `TypeError` when attempting to slice the `obj` with an empty `Series`, which was previously causing the test to fail. The risk score remains 98.6%, indicating that the defect is still present but has been mitigated by the change.

`pandas-148` — invented: ____

---

## 41. `pandas-80`  (pandas, arm `score_v2`)

**Commit message:** BUG: Series/Frame invert dtypes (#31183)

**Measured before:** `AssertionError: Attributes of Series are different`

**Measured after:**  `2 passed`

**The model said:** The `__invert__` method was added to the `BaseMaskedArray` class, which allows the inversion of boolean arrays using the `~` operator. This change fixes the failure observed in the `test_boolean_array_invert` test, which previously raised a `TypeError` because the `~` operator was not supported by the `BooleanArray` class.

`pandas-80` — invented: ____

---

## 42. `ansible-1`  (ansible, arm `score_v2`)

**Commit message:** better error for "ansible-galaxy collection verify" if there's no MANIFEST.json (#67498)

**Measured before:** `TypeError: 'GalaxyAPI' object is not iterable`

**Measured after:**  `1 passed`

**The model said:** The commit adds a check for the presence of a `MANIFEST.json` file in the collection directory, which is required for collections built and installed via `ansible-galaxy`. This prevents the program from crashing when a collection is missing the manifest file, instead raising an `AnsibleError` with a helpful message.

`ansible-1` — invented: ____

---

## 43. `httpie-1`  (httpie, arm `score_v2`)

**Commit message:** Fixed #451 - OSError: [Errno 36] File name too long

**Measured before:** `AttributeError: <module 'httpie.downloads' from '<repo>/httpie/downloads.py'> does not have the attribute 'get_filename_max_length'`

**Measured after:**  `11 passed`

**The model said:** The `filename_from_url` function was refactored into `trim_filename`, which reduces the file name length by removing characters from the end until it fits within the system's maximum path length. This change fixes the `OSError: [Errno 36] File name too long` issue by ensuring that the generated filenames do not exceed the system's limit.

`httpie-1` — invented: ____

---

## 44. `scrapy-2`  (scrapy, arm `score_v2`)

**Commit message:** Fix scrapy.utils.datatypes.LocalCache limit issue

**Measured before:** `TypeError: '>=' not supported between instances of 'int' and 'NoneType'`

**Measured after:**  `OK`

**The model said:** The `LocalCache` class now includes a check for the `limit` attribute before attempting to pop items when the cache size exceeds the specified limit, which prevents the `IndexError: pop from empty list` failure observed in the test suite.

`scrapy-2` — invented: ____

---

## 45. `tqdm-5`  (tqdm, arm `score_v2`)

**Commit message:** support `bool()` cast when `disable=True`

**Measured before:** `AttributeError: 'tqdm' object has no attribute 'total'`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The commit adds a check for `total` being `None` when `iterable` is not `None`, which attempts to infer the length of the iterable using `len()`. This change prevents a `RuntimeError: object of type 'generator' has no len()` when `total` is not explicitly set, which was previously causing the test suite to fail.

`tqdm-5` — invented: ____

---

## 46. `pandas-57`  (pandas, arm `score_v2`)

**Commit message:** BUG: list-like to_replace on Categorical.replace is ignored or crash (#31734)

**Measured before:** `TypeError: assert_series_equal() got an unexpected keyword argument 'check_category_order'`

**Measured after:**  `13 passed`

**The model said:** The `Categorical.replace` method now includes a `check_category_order` parameter, which defaults to `True`. This change ensures that the order of categories within the Categorical array is preserved when replacing values, which was previously ignored. This fix addresses a regression introduced by the commit, causing the project's own tests to fail with a `ValueError: cannot replace category 'foo' with non-category 'bar'`.

`pandas-57` — invented: ____

---

## 47. `pandas-114`  (pandas, arm `score_v2`)

**Commit message:** BUG: Index.get_value implementation for ExtensionArray (#29926)

**Measured before:** `Exception: tried to convert a DecimalArray to a numpy array`

**Measured after:**  `1 passed`

**The model said:** The change replaces direct access to `_values` with `extract_array`, which removes the need to check for `ExtensionArray` and simplifies the logic by removing the special case for non-scalar keys. This refactoring eliminates the potential for a `KeyError` when accessing non-scalar keys, which was previously raised in `Index.get_value`.

`pandas-114` — invented: ____

---

## 48. `scrapy-17`  (scrapy, arm `score_v2`)

**Commit message:** response_status_message should not fail on non-standard HTTP codes

**Measured before:** `TypeError: to_unicode must receive a bytes, str or unicode object, got NoneType`

**Measured after:**  `OK`

**The model said:** The `response_status_message` function now returns "Unknown Status" for non-standard HTTP codes instead of failing with a `KeyError`, which resolves the test failures.

`scrapy-17` — invented: ____

---

## 49. `youtube-dl-7`  (youtube-dl, arm `score_v2`)

**Commit message:** [utils:js_to_json] Fix bad escape in double quoted strings

**Measured before:** `AssertionError: '"The CW\\\'s \\\'Crazy Ex-Girlfriend\\\'"' != '"The CW\'s \'Crazy Ex-Girlfriend\'"'`

**Measured after:**  `OK`

**The model said:** The change replaces the literal backslash escape `"` with the string literal escape `\'` inside single-quoted strings, which fixes the failure to correctly parse the JSON output when the input contains escaped single quotes. This ensures that the project's own tests no longer fail with the error `JSONDecodeError: Invalid control character at position 20`.

`youtube-dl-7` — invented: ____

---

## 50. `pandas-117`  (pandas, arm `score_v2`)

**Commit message:** BUG: .count() raises if use_inf_as_na is enabled (#29888)

**Measured before:** `AttributeError: 'DatetimeArray' object has no attribute '_constructor'`

**Measured after:**  `1 passed`

**The model said:** The change adds `ABCExtensionArray` to the list of types checked by `_isna_old`, which allows the function to handle extension arrays without raising a `NotImplementedError`. This resolves the test failure where `pd.Series([1, np.nan]).count()` previously raised an exception.

`pandas-117` — invented: ____

---

## 51. `pandas-129`  (pandas, arm `score_v2`)

**Commit message:** BUG: np.datetime64 - TimedeltaArray (#29558)

**Measured before:** `ValueError: Unexpected type 'datetime64'. 'values' must be a DatetimeArray ndarray, or Series or Index containing one of those.`

**Measured after:**  `12 passed`

**The model said:** The change adds support for scalar `np.datetime64` objects when subtracting from `DatetimeArray`, which previously caused a TypeError. This modification ensures that the project's own tests continue to pass without errors.

`pandas-129` — invented: ____

---

## 52. `pandas-32`  (pandas, arm `score_v2`)

**Commit message:** BUG: AttributeError when read_sas used with GCS (#33070)

**Measured before:** `AttributeError: 'bytes' object has no attribute 'encode'`

**Measured after:**  `1 passed`

**The model said:** The commit removes the explicit encoding step when reading SAS XPORT files, which was previously necessary to handle non-text byte sequences. This change reduces the risk of `UnicodeEncodeError` by removing the encoding step, but it may cause issues if the file contains non-text data that cannot be decoded, as the error handling was previously in place to catch such cases.

`pandas-32` — invented: ____

---

## 53. `pandas-58`  (pandas, arm `score_v2`)

**Commit message:** BUG: Avoid casting Int to object in Categorical.from_codes (#31794)

**Measured before:** `ValueError: codes need to be array-like integers`

**Measured after:**  `1 passed`

**The model said:** The change removes the explicit `np.asarray` cast on `codes`, which was previously necessary to ensure that the input type is an integer. This refactoring eliminates the potential for a `TypeError` when `codes` contains non-integer values, but it also requires that `codes` does not contain any `NA` values. The defect predictor score remains 94.9%, indicating that the risk of introducing a defect is still high.

`pandas-58` — invented: ____

---

## 54. `scrapy-34`  (scrapy, arm `score_v2`)

**Commit message:** item fields defined on fields class attribute fix

**Measured before:** `AssertionError: {'load': {'default': 'D'}, 'save': {'default': 'C'}} != {'save': {'default': 'C'}, 'load': {'default': 'D'}, 'update': {'default': 'D'}}`

**Measured after:**  `OK`

**The model said:** The `fields` dictionary was replaced with a direct access to the `fields` attribute using `getattr`, which removes the risk of a `KeyError` when accessing the `fields` attribute. This change is safe and does not alter the project's own tests, which still pass.

`scrapy-34` — invented: ____

---

## 55. `scrapy-12`  (scrapy, arm `score_v2`)

**Commit message:** Merge pull request #2153 from Digenis/Selector_bad_args

**Measured before:** `FAIL: test_selector_bad_args (tests.test_selector.SelectorTestCase)`

**Measured after:**  `OK`

**The model said:** The commit adds a check to ensure that `response` and `text` cannot be provided simultaneously in the `__init__` method, which prevents the creation of a `Selector` instance with conflicting input types. This change fixes the TypeError: 'response' and 'text' cannot be specified together.

`scrapy-12` — invented: ____

---

## 56. `pandas-123`  (pandas, arm `score_v2`)

**Commit message:** [BUG] Validate dtype when Int64Index, UInt64Index, or Float64Index are cons… (#29545)

**Measured before:** `Failed: DID NOT RAISE <class 'ValueError'>`

**Measured after:**  `4 passed`

**The model said:** The `RangeIndex` class now includes a static method `_validate_dtype` that checks if the `dtype` parameter is `None` or `int64`, raising a `TypeError` if it is not. This change ensures that `RangeIndex` can only be instantiated with an `int64` dtype, which was previously allowed by default.

`pandas-123` — invented: ____

---

## 57. `matplotlib-25`  (matplotlib, arm `score_v2`)

**Commit message:** Backport PR #14488: Make sure EventCollection doesn't modify input in-place

**Measured before:** `AssertionError:`

**Measured after:**  `1 passed`

**The model said:** The commit adds a check for `positions` being `None` and raises a `ValueError` if so, ensuring that the function signature remains consistent with the previous behavior. This change prevents the modification of the input `positions` in-place, which was previously allowed by default, and ensures that the project's own tests continue to observe the expected behaviour.

`matplotlib-25` — invented: ____

---

## 58. `thefuck-26`  (thefuck, arm `score_v2`)

**Commit message:** Support for either starting only the machine requested, or starting all machines

**Measured before:** `AssertionError: assert 'vagrant up  && vagrant ssh' == 'vagrant up && vagrant ssh'`

**Measured after:**  `4 passed, 1 warning`

**The model said:** The change replaces the literal `""` with `None` in the `machine` variable, which removes the empty string from the list returned by `get_new_command`. This refactoring eliminates the potential for a `TypeError` when the script is executed, as the empty string was causing the `and_` function to fail. The defect predictor score remains 8.8%, indicating that the change is still low-risk.

`thefuck-26` — invented: ____

---

## 59. `youtube-dl-16`  (youtube-dl, arm `score_v2`)

**Commit message:** [utils] Use bytes-like objects in dfxp2srt

**Measured before:** `TypeError: a bytes-like object is required, not 'str'`

**Measured after:**  `OK`

**The model said:** The `io.open` call was updated to use binary mode (`'rb'`) instead of text mode (`'rt'`), which changes the encoding parameter from `'utf-8'` to `None`. This modification fixes the `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 1: invalid start byte` when processing DFXP files, as the input data is no longer decoded from UTF-8.

`youtube-dl-16` — invented: ____

---
