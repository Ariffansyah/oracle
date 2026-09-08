# BugsInPy rater packet

50 cases drawn from the `v3plain_fix_v2` arm with seed 7.

Each case shows a real commit from a real project, what the project's
own failing test reported before and after the change, and what the
model said about it. **The before/after is ground truth** -- it was
obtained by running the test at the parent commit and again with the
fix applied. You are not checking the measurement. You are checking
the sentence against it.

For each case, two judgements:

- **grounded** — `y` if the explanation states what the program
  actually did: it names the real failure, or quotes a distinctive
  part of the real message. `n` if it is vague, generic, or talks
  only about the code without saying what the run reported.
- **invented** — `y` if it asserts a failure that did not happen
  (names an exception nothing raised, claims an outcome the run
  contradicts). `n` otherwise.
- **direction** — `y` if it gets the direction of the change right.
  `n` if it states the edit backwards: says a value moved from A to B
  when the diff moves it from B to A, says something was added that
  was removed, or names the pre-change behaviour as the post-change
  one. Read the diff for this one; an explanation can quote the real
  failure and still describe the edit in reverse.

An explanation can be a perfectly sensible code review and still be
`grounded=n`. That is the intended reading: the question is whether it
committed to the measured behaviour, not whether it is a good comment.

Leave a cell blank if unsure. A blank is data; a guess is noise.

Record answers in `bip_rater_v3.csv` as `id,grounded,invented,direction`, then:

    python bench/bugsinpy_rater.py --score data/bip_rater_v3.csv

The rubric's own verdict is not in this file.

---

## 1. `matplotlib-3`  (matplotlib)

**Commit message:** Markers with fillstyle 'none' should return False for is_filled()

**Test run:** `pytest lib/matplotlib/tests/test_marker.py::test_marker_fillstyle`

```diff
diff --git a/lib/matplotlib/markers.py b/lib/matplotlib/markers.py
index afa8c105e..e9c5fbc21 100644
--- a/lib/matplotlib/markers.py
+++ b/lib/matplotlib/markers.py
@@ -232,7 +232,10 @@ class MarkerStyle:
         self._snap_threshold = None
         self._joinstyle = 'round'
         self._capstyle = 'butt'
-        self._filled = True
+        # Initial guess: Assume the marker is filled unless the fillstyle is
+        # set to 'none'. The marker function will override this for unfilled
+        # markers.
+        self._filled = self._fillstyle != 'none'
         self._marker_function()
 
     def __bool__(self):
```

**Measured before:** `assert not True`

**Measured after:**  `1 passed`

**The model said:** The default value of `self._filled` was changed to match the `self._fillstyle` property, which resolves the failure where the assertion `assert not True` previously failed.

`matplotlib-3` — grounded: ____   invented: ____   direction: ____

---

## 2. `spacy-5`  (spacy)

**Commit message:** Fix bug in Language.evaluate for components without .pipe (#4662)

**Test run:** `py.test spacy/tests/test_language.py::test_evaluate_no_pipe`

```diff
diff --git a/spacy/language.py b/spacy/language.py
index 72044a0c5..266a1727d 100644
--- a/spacy/language.py
+++ b/spacy/language.py
@@ -678,7 +678,7 @@ class Language(object):
             kwargs = component_cfg.get(name, {})
             kwargs.setdefault("batch_size", batch_size)
             if not hasattr(pipe, "pipe"):
-                docs = _pipe(pipe, docs, kwargs)
+                docs = _pipe(docs, pipe, kwargs)
             else:
                 docs = pipe.pipe(docs, **kwargs)
         for doc, gold in zip(docs, golds):
```

**Measured before:** `TypeError: 'function' object is not iterable`

**Measured after:**  `1 passed`

**The model said:** The change replaces `docs = _pipe(pipe, docs, kwargs)` with `docs = _pipe(docs, pipe, kwargs)`, which corrects the failure `TypeError: 'function' object is not iterable'` by ensuring the input is an iterable rather than a function.

`spacy-5` — grounded: ____   invented: ____   direction: ____

---

## 3. `ansible-11`  (ansible)

**Commit message:** allowing banner without stripping spaces (#62573)

**Test run:** `pytest test/units/modules/network/ios/test_ios_banner.py::TestIosBannerModule::test_ios_banner_nochange`

```diff
diff --git a/lib/ansible/modules/network/ios/ios_banner.py b/lib/ansible/modules/network/ios/ios_banner.py
index be85781058..c28838407c 100644
--- a/lib/ansible/modules/network/ios/ios_banner.py
+++ b/lib/ansible/modules/network/ios/ios_banner.py
@@ -89,10 +89,9 @@ commands:
     - string
 """
 from ansible.module_utils.basic import AnsibleModule
-from ansible.module_utils.connection import exec_command
-from ansible.module_utils.network.ios.ios import load_config
+from ansible.module_utils.network.ios.ios import get_config, load_config
 from ansible.module_utils.network.ios.ios import ios_argument_spec
-import re
+from re import search, M
 
 
 def map_obj_to_commands(updates, module):
@@ -107,7 +106,7 @@ def map_obj_to_commands(updates, module):
         if want['text'] and (want['text'] != have.get('text')):
             banner_cmd = 'banner %s' % module.params['banner']
             banner_cmd += ' @\n'
-            banner_cmd += want['text'].strip()
+            banner_cmd += want['text'].strip('\n')
             banner_cmd += '\n@'
             commands.append(banner_cmd)
 
@@ -115,17 +114,21 @@ def map_obj_to_commands(updates, module):
 
 
 def map_config_to_obj(module):
-    rc, out, err = exec_command(module, 'show banner %s' % module.params['banner'])
-    if rc == 0:
-        output = out
-    else:
-        rc, out, err = exec_command(module,
-                                    'show running-config | begin banner %s'
-                                    % module.params['banner'])
-        if out:
-            output = re.search(r'\^C(.*?)\^C', out, re.S).group(1).strip()
+    """
+    This function gets the banner config without stripping any whitespaces,
+    and then fetches the required banner from it.
+    :param module:
+    :return: banner config dict object.
+    """
+    out = get_config(module, flags='| begin banner %s' % module.params['banner'])
+    if out:
+        regex = 'banner ' + module.params['banner'] + ' ^C\n'
+        if search('banner ' + module.params['banner'], out, M):
+            output = str((out.split(regex))[1].split("^C\n")[0])
         else:
             output = None
+    else:
+        output = None
     obj = {'banner': module.params['banner'], 'state': 'absent'}
     if output:
         obj['text'] = output
@@ -135,9 +138,6 @@ def map_config_to_obj(module):
 
 def map_params_to_obj(module):
     text = module.params['text']
-    if text:
-        text = str(text).strip()
-
     return {
         'banner': mod
... (truncated)
```

**Measured before:** `AttributeError: <module 'ansible.modules.network.ios.ios_banner' from '<repo>/lib/ansible/modules/network/ios/ios_banner.py'> does not have the attribute 'get_config'`

**Measured after:**  `1 passed`

**The model said:** The commit adds the `get_config` function to the `ios_banner` module, which resolves the `AttributeError: <module 'ansible.modules.network.ios.ios_banner' from '<repo>/lib/ansible/modules/network/ios/ios_banner.py'> does not have the attribute 'get_config'` failure by providing a way to retrieve the banner configuration without stripping whitespace.

`ansible-11` — grounded: ____   invented: ____   direction: ____

---

## 4. `pandas-38`  (pandas)

**Commit message:** BUG: Multiple unstack using row index level labels and multi level columns DataFrame (#32990)

**Test run:** `pytest pandas/tests/frame/test_reshape.py::TestDataFrameReshape::test_unstack_long_index`

```diff
diff --git a/pandas/core/reshape/reshape.py b/pandas/core/reshape/reshape.py
index 14c2a05e5..88e61d239 100644
--- a/pandas/core/reshape/reshape.py
+++ b/pandas/core/reshape/reshape.py
@@ -338,7 +338,7 @@ def _unstack_multiple(data, clocs, fill_value=None):
     comp_ids, obs_ids = compress_group_index(group_index, sort=False)
     recons_codes = decons_obs_group_ids(comp_ids, obs_ids, shape, ccodes, xnull=False)
 
-    if rlocs == []:
+    if not rlocs:
         # Everything is in clocs, so the dummy df has a regular index
         dummy_index = Index(obs_ids, name="__placeholder__")
     else:
@@ -363,7 +363,7 @@ def _unstack_multiple(data, clocs, fill_value=None):
             for i in range(len(clocs)):
                 val = clocs[i]
                 result = result.unstack(val, fill_value=fill_value)
-                clocs = [v if i > v else v - 1 for v in clocs]
+                clocs = [v if v < val else v - 1 for v in clocs]
 
             return result
```

**Measured before:** `ValueError: 2 is not in list`

**Measured after:**  `1 passed`

**The model said:** The change replaces the `if rlocs == []` check with `if not rlocs:` to fix the `ValueError: 2 is not in list` failure, which occurs when the row index levels are empty.

`pandas-38` — grounded: ____   invented: ____   direction: ____

---

## 5. `pandas-60`  (pandas)

**Commit message:** BUG: Fix raw parameter not being respected in groupby.rolling.apply (#31842)

**Test run:** `pytest pandas/tests/window/test_grouper.py::TestGrouperGrouping::test_groupby_rolling`

```diff
diff --git a/pandas/core/window/rolling.py b/pandas/core/window/rolling.py
index 580c7cc05..8506b2ff6 100644
--- a/pandas/core/window/rolling.py
+++ b/pandas/core/window/rolling.py
@@ -1296,13 +1296,14 @@ class _Rolling_and_Expanding(_Rolling):
             raise ValueError("engine must be either 'numba' or 'cython'")
 
         # TODO: Why do we always pass center=False?
-        # name=func for WindowGroupByMixin._apply
+        # name=func & raw=raw for WindowGroupByMixin._apply
         return self._apply(
             apply_func,
             center=False,
             floor=0,
             name=func,
             use_numba_cache=engine == "numba",
+            raw=raw,
         )
 
     def _generate_cython_apply_func(self, args, kwargs, raw, offset, func):
```

**Measured before:** `AssertionError: Series are different`

**Measured after:**  `2 passed`

**The model said:** The `raw` parameter was added to the `_Rolling_and_Expanding._apply` method, which resolved the `AssertionError: Series are different` by ensuring the window calculation respects the raw data alignment.

`pandas-60` — grounded: ____   invented: ____   direction: ____

---

## 6. `keras-11`  (keras)

**Commit message:** Improve type-check for Sequence (#11468)

**Test run:** `pytest tests/integration_tests/test_image_data_tasks.py::test_image_data_generator_training`

```diff
diff --git a/keras/engine/training_generator.py b/keras/engine/training_generator.py
index 55e817a1..f74eddf8 100644
--- a/keras/engine/training_generator.py
+++ b/keras/engine/training_generator.py
@@ -7,6 +7,7 @@ from __future__ import print_function
 import warnings
 import numpy as np
 
+from .training_utils import is_sequence
 from .training_utils import iter_sequence_infinite
 from .. import backend as K
 from ..utils.data_utils import Sequence
@@ -40,15 +41,15 @@ def fit_generator(model,
     if do_validation:
         model._make_test_function()
 
-    is_sequence = isinstance(generator, Sequence)
-    if not is_sequence and use_multiprocessing and workers > 1:
+    use_sequence_api = is_sequence(generator)
+    if not use_sequence_api and use_multiprocessing and workers > 1:
         warnings.warn(
             UserWarning('Using a generator with `use_multiprocessing=True`'
                         ' and multiple workers may duplicate your data.'
                         ' Please consider using the`keras.utils.Sequence'
                         ' class.'))
     if steps_per_epoch is None:
-        if is_sequence:
+        if use_sequence_api:
             steps_per_epoch = len(generator)
         else:
             raise ValueError('`steps_per_epoch=None` is only valid for a'
@@ -59,10 +60,11 @@ def fit_generator(model,
 
     # python 2 has 'next', 3 has '__next__'
     # avoid any explicit version checks
+    val_use_sequence_api = is_sequence(validation_data)
     val_gen = (hasattr(validation_data, 'next') or
                hasattr(validation_data, '__next__') or
-               isinstance(validation_data, Sequence))
-    if (val_gen and not isinstance(validation_data, Sequence) and
+               val_use_sequence_api)
+    if (val_gen and not val_use_sequence_api and
             not validation_steps):
         raise ValueError('`validation_steps=None` is only valid for a'
                          ' generator based on the `keras.utils.Sequence`'
@@ -108,7 +110,7 @@ def fit_generator(model,
             if val_gen and workers > 0:
                 # Create an Enqueuer that can be reused
                 val_data = validation_data
-                if isinstance(val_data, Sequence):
+                if is_sequence(val_data):
                     val_enqueuer = OrderedEnqueuer(
                         val_data,
                         use_multiprocessing=use_multiprocessing)
@@ -122,7 +124,7 @@ def fit_generator(model,
                 val_e
... (truncated)
```

**Measured before:** `ValueError: `steps_per_epoch=None` is only valid for a generator based on the `keras.utils.Sequence` class. Please specify `steps_per_epoch` or use the `keras.utils.Sequence` class.`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The change replaces the `isinstance(generator, Sequence)` check with `is_sequence(generator)`, which is a refactoring that removes the need for the `Sequence` class check. This eliminates the error `ValueError: `steps_per_epoch=None` is only valid for a generator based on the `keras.utils.Sequence` class. Please specify `steps_per_epoch` or use the `keras.utils.Sequence` class.` by ensuring the generator is treated as a sequence regardless of its actual type.

`keras-11` — grounded: ____   invented: ____   direction: ____

---

## 7. `pandas-147`  (pandas)

**Commit message:** BUG/CLN: DatetimeTZDtype.construct_from_string Exception (#28505)

**Test run:** `pytest pandas/tests/dtypes/test_dtypes.py::TestDatetimeTZDtype::test_construct_from_string_raises`

```diff
diff --git a/pandas/core/dtypes/dtypes.py b/pandas/core/dtypes/dtypes.py
index aa7e6801b..fcdb89dd8 100644
--- a/pandas/core/dtypes/dtypes.py
+++ b/pandas/core/dtypes/dtypes.py
@@ -685,7 +685,7 @@ class DatetimeTZDtype(PandasExtensionDtype):
             tz = timezones.tz_standardize(tz)
         elif tz is not None:
             raise pytz.UnknownTimeZoneError(tz)
-        elif tz is None:
+        if tz is None:
             raise TypeError("A 'tz' is required.")
 
         self._unit = unit
@@ -737,14 +737,17 @@ class DatetimeTZDtype(PandasExtensionDtype):
         """
         if isinstance(string, str):
             msg = "Could not construct DatetimeTZDtype from '{}'"
-            try:
-                match = cls._match.match(string)
-                if match:
-                    d = match.groupdict()
+            match = cls._match.match(string)
+            if match:
+                d = match.groupdict()
+                try:
                     return cls(unit=d["unit"], tz=d["tz"])
-            except Exception:
-                # TODO(py3): Change this pass to `raise TypeError(msg) from e`
-                pass
+                except (KeyError, TypeError, ValueError) as err:
+                    # KeyError if maybe_get_tz tries and fails to get a
+                    #  pytz timezone (actually pytz.UnknownTimeZoneError).
+                    # TypeError if we pass a nonsense tz;
+                    # ValueError if we pass a unit other than "ns"
+                    raise TypeError(msg.format(string)) from err
             raise TypeError(msg.format(string))
 
         raise TypeError("Could not construct DatetimeTZDtype")
```

**Measured before:** `Failed: DID NOT RAISE <class 'TypeError'>`

**Measured after:**  `1 passed`

**The model said:** The change removes the `try-except` block around the `groupdict()` call in the `DatetimeTZDtype.construct_from_string` method, which previously caught exceptions and re-raised them as `TypeError`. This resolves the failure where the test did not raise the expected exception, ensuring the project's own tests now observe the correct behavior.

`pandas-147` — grounded: ____   invented: ____   direction: ____

---

## 8. `pandas-157`  (pandas)

**Commit message:** BUG: timedelta merge asof with tolerance (#27650)

**Test run:** `pytest pandas/tests/reshape/merge/test_merge_asof.py::TestAsOfMerge::test_timedelta_tolerance_nearest`

```diff
diff --git a/pandas/core/reshape/merge.py b/pandas/core/reshape/merge.py
index f45c7693b..225de3f11 100644
--- a/pandas/core/reshape/merge.py
+++ b/pandas/core/reshape/merge.py
@@ -22,7 +22,6 @@ from pandas.core.dtypes.common import (
     is_bool,
     is_bool_dtype,
     is_categorical_dtype,
-    is_datetime64_dtype,
     is_datetime64tz_dtype,
     is_datetimelike,
     is_dtype_equal,
@@ -1635,7 +1634,7 @@ class _AsOfMerge(_OrderedMerge):
                 )
             )
 
-            if is_datetime64_dtype(lt) or is_datetime64tz_dtype(lt):
+            if is_datetimelike(lt):
                 if not isinstance(self.tolerance, Timedelta):
                     raise MergeError(msg)
                 if self.tolerance < Timedelta(0):
```

**Measured before:** `pandas.errors.MergeError: key must be integer, timestamp or float`

**Measured after:**  `1 passed`

**The model said:** The change removes the `is_datetime64_dtype` check from the `_AsOfMerge` class, which resolves the `pandas.errors.MergeError: key must be integer, timestamp or float` failure by allowing datetimelike types to be used as keys.

`pandas-157` — grounded: ____   invented: ____   direction: ____

---

## 9. `pandas-130`  (pandas)

**Commit message:** BUG: value_counts can handle the case even with empty groups (#28479) (#28634)

**Test run:** `pytest pandas/tests/groupby/test_value_counts.py::test_series_groupby_value_counts_with_grouper`

```diff
diff --git a/pandas/core/groupby/ops.py b/pandas/core/groupby/ops.py
index 2c8aa1294..9599ce0bf 100644
--- a/pandas/core/groupby/ops.py
+++ b/pandas/core/groupby/ops.py
@@ -767,6 +767,11 @@ class BinGrouper(BaseGrouper):
             ngroups,
         )
 
+    @cache_readonly
+    def recons_codes(self):
+        # get unique result indices, and prepend 0 as groupby starts from the first
+        return [np.r_[0, np.flatnonzero(self.bins[1:] != self.bins[:-1]) + 1]]
+
     @cache_readonly
     def result_index(self):
         if len(self.binlabels) != 0 and isna(self.binlabels[0]):
```

**Measured before:** `ValueError: operands could not be broadcast together with shape (5,) (4,)`

**Measured after:**  `1 passed`

**The model said:** The addition of `recons_codes` attribute to `BinGrouper` resolves the `ValueError: operands could not be broadcast together with shape (5,) (4,)` by ensuring the correct binning logic, which previously failed when the input data was empty.

`pandas-130` — grounded: ____   invented: ____   direction: ____

---

## 10. `scrapy-7`  (scrapy)

**Commit message:** FormRequest: handle whitespaces in action attribute properly

**Test run:** `python -m unittest -q tests.test_http_request.FormRequestTest.test_spaces_in_action`

```diff
diff --git a/scrapy/http/request/form.py b/scrapy/http/request/form.py
index 2862dc09..905d8412 100644
--- a/scrapy/http/request/form.py
+++ b/scrapy/http/request/form.py
@@ -5,10 +5,13 @@ This module implements the FormRequest class which is a more convenient class
 See documentation in docs/topics/request-response.rst
 """
 
+import six
 from six.moves.urllib.parse import urljoin, urlencode
+
 import lxml.html
 from parsel.selector import create_root_node
-import six
+from w3lib.html import strip_html5_whitespace
+
 from scrapy.http.request import Request
 from scrapy.utils.python import to_bytes, is_listlike
 from scrapy.utils.response import get_base_url
@@ -51,7 +54,10 @@ class FormRequest(Request):
 
 def _get_form_url(form, url):
     if url is None:
-        return urljoin(form.base_url, form.action)
+        action = form.get('action')
+        if action is None:
+            return form.base_url
+        return urljoin(form.base_url, strip_html5_whitespace(action))
     return urljoin(form.base_url, url)
```

**Measured before:** `OK`

**Measured after:**  `OK`

**The model said:** The change strips HTML5 whitespace from the `form.action` attribute before joining it with the base URL, which resolves the failure where the request was failing to build the correct URL.

`scrapy-7` — grounded: ____   invented: ____   direction: ____

---

## 11. `pandas-112`  (pandas)

**Commit message:** BUG: Support categorical targets in IntervalIndex.get_indexer (#30181)

**Test run:** `pytest pandas/tests/frame/test_analytics.py::TestDataFrameAnalytics::test_round_interval_category_columns`

```diff
diff --git a/pandas/core/indexes/interval.py b/pandas/core/indexes/interval.py
index 2555caac2..b1f67eeab 100644
--- a/pandas/core/indexes/interval.py
+++ b/pandas/core/indexes/interval.py
@@ -19,6 +19,7 @@ from pandas.core.dtypes.cast import (
 )
 from pandas.core.dtypes.common import (
     ensure_platform_int,
+    is_categorical,
     is_datetime64tz_dtype,
     is_datetime_or_timedelta_dtype,
     is_dtype_equal,
@@ -36,6 +37,7 @@ from pandas.core.dtypes.generic import ABCSeries
 from pandas.core.dtypes.missing import isna
 
 from pandas._typing import AnyArrayLike
+from pandas.core.algorithms import take_1d
 from pandas.core.arrays.interval import IntervalArray, _interval_shared_docs
 import pandas.core.common as com
 import pandas.core.indexes.base as ibase
@@ -958,6 +960,10 @@ class IntervalIndex(IntervalMixin, Index):
             left_indexer = self.left.get_indexer(target_as_index.left)
             right_indexer = self.right.get_indexer(target_as_index.right)
             indexer = np.where(left_indexer == right_indexer, left_indexer, -1)
+        elif is_categorical(target_as_index):
+            # get an indexer for unique categories then propogate to codes via take_1d
+            categories_indexer = self.get_indexer(target_as_index.categories)
+            indexer = take_1d(categories_indexer, target_as_index.codes, fill_value=-1)
         elif not is_object_dtype(target_as_index):
             # homogeneous scalar index: use IntervalTree
             target_as_index = self._maybe_convert_i8(target_as_index)
diff --git a/pandas/tests/indexes/interval/test_indexing.py b/pandas/tests/indexes/interval/test_indexing.py
index 05d8aee2a..15ea9a6b6 100644
--- a/pandas/tests/indexes/interval/test_indexing.py
+++ b/pandas/tests/indexes/interval/test_indexing.py
@@ -3,7 +3,14 @@ import re
 import numpy as np
 import pytest
 
-from pandas import Interval, IntervalIndex, Timedelta, date_range, timedelta_range
+from pandas import (
+    CategoricalIndex,
+    Interval,
+    IntervalIndex,
+    Timedelta,
+    date_range,
+    timedelta_range,
+)
 from pandas.core.indexes.base import InvalidIndexError
 import pandas.util.testing as tm
 
@@ -231,6 +238,25 @@ class TestGetIndexer:
         expected = np.array([0] * size, dtype="intp")
         tm.assert_numpy_array_equal(result, expected)
 
+    @pytest.mark.parametrize(
+        "target",
+        [
+            IntervalIndex.from_tuples([(7, 8), (1, 2), (3, 4), (0, 1)]),
+            IntervalIndex.from_
... (truncated)
```

**Measured before:** `TypeError: No matching signature found`

**Measured after:**  `1 passed`

**The model said:** The change adds support for categorical targets in `IntervalIndex.get_indexer`, which previously failed with `TypeError: No matching signature found`.

`pandas-112` — grounded: ____   invented: ____   direction: ____

---

## 12. `luigi-2`  (luigi)

**Commit message:** Merge pull request #2705 from spotify/claire/fix_dataflow_bq_return_type

**Test run:** `pytest test/contrib/beam_dataflow_test.py::BeamDataflowTest::test_get_target_path`

```diff
diff --git a/luigi/contrib/beam_dataflow.py b/luigi/contrib/beam_dataflow.py
index dd510786..42cdc742 100644
--- a/luigi/contrib/beam_dataflow.py
+++ b/luigi/contrib/beam_dataflow.py
@@ -219,6 +219,7 @@ class BeamDataflowJobTask(MixinNaiveBulkComplete, luigi.Task):
     def __init__(self):
         if not isinstance(self.dataflow_params, DataflowParamKeys):
             raise ValueError("dataflow_params must be of type DataflowParamKeys")
+        super(BeamDataflowJobTask, self).__init__()
 
     @abstractmethod
     def dataflow_executable(self):
@@ -471,9 +472,13 @@ class BeamDataflowJobTask(MixinNaiveBulkComplete, luigi.Task):
 
     @staticmethod
     def get_target_path(target):
+        """
+            Given a luigi Target, determine a stringly typed path to pass as a
+            Dataflow job argument.
+        """
         if isinstance(target, luigi.LocalTarget) or isinstance(target, gcs.GCSTarget):
             return target.path
         elif isinstance(target, bigquery.BigQueryTarget):
-            "{}:{}.{}".format(target.project_id, target.dataset_id, target.table_id)
+            return "{}:{}.{}".format(target.table.project_id, target.table.dataset_id, target.table.table_id)
         else:
-            raise ValueError("Target not supported")
+            raise ValueError("Target %s not supported" % target)
```

**Measured before:** `AttributeError: 'BigQueryTarget' object has no attribute 'project_id'`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The `get_target_path` method now returns a stringified path for BigQuery targets, which resolves the `AttributeError: 'BigQueryTarget' object has no attribute 'project_id'` by providing the necessary components directly in the Dataflow job arguments.

`luigi-2` — grounded: ____   invented: ____   direction: ____

---

## 13. `pandas-167`  (pandas)

**Commit message:** BUG: partial string indexing with scalar (#27712)

**Test run:** `pytest pandas/tests/indexes/datetimes/test_partial_slicing.py::TestSlicing::test_slice_reduce_to_series`

```diff
diff --git a/pandas/core/indexes/base.py b/pandas/core/indexes/base.py
index d0de99525..5fc477ed3 100644
--- a/pandas/core/indexes/base.py
+++ b/pandas/core/indexes/base.py
@@ -243,6 +243,9 @@ class Index(IndexOpsMixin, PandasObject):
     _infer_as_myclass = False
 
     _engine_type = libindex.ObjectEngine
+    # whether we support partial string indexing. Overridden
+    # in DatetimeIndex and PeriodIndex
+    _supports_partial_string_indexing = False
 
     _accessors = {"str"}
 
diff --git a/pandas/core/indexes/datetimes.py b/pandas/core/indexes/datetimes.py
index 0f7f580e2..67de7b019 100644
--- a/pandas/core/indexes/datetimes.py
+++ b/pandas/core/indexes/datetimes.py
@@ -238,6 +238,7 @@ class DatetimeIndex(DatetimeIndexOpsMixin, Int64Index, DatetimeDelegateMixin):
     )
 
     _engine_type = libindex.DatetimeEngine
+    _supports_partial_string_indexing = True
 
     _tz = None
     _freq = None
diff --git a/pandas/core/indexes/period.py b/pandas/core/indexes/period.py
index 19fe1eb89..f6b3d1076 100644
--- a/pandas/core/indexes/period.py
+++ b/pandas/core/indexes/period.py
@@ -173,6 +173,7 @@ class PeriodIndex(DatetimeIndexOpsMixin, Int64Index, PeriodDelegateMixin):
     _data = None
 
     _engine_type = libindex.PeriodEngine
+    _supports_partial_string_indexing = True
 
     # ------------------------------------------------------------------------
     # Index Constructors
diff --git a/pandas/core/indexing.py b/pandas/core/indexing.py
index df89dbe6d..e308ae037 100755
--- a/pandas/core/indexing.py
+++ b/pandas/core/indexing.py
@@ -1704,6 +1704,11 @@ class _LocIndexer(_LocationIndexer):
             if isinstance(ax, MultiIndex):
                 return False
 
+            if isinstance(k, str) and ax._supports_partial_string_indexing:
+                # partial string indexing, df.loc['2000', 'A']
+                # should not be considered scalar
+                return False
+
             if not ax.is_unique:
                 return False
 
@@ -1719,7 +1724,10 @@ class _LocIndexer(_LocationIndexer):
         """Translate any partial string timestamp matches in key, returning the
         new key (GH 10331)"""
         if isinstance(labels, MultiIndex):
-            if isinstance(key, str) and labels.levels[0].is_all_dates:
+            if (
+                isinstance(key, str)
+                and labels.levels[0]._supports_partial_string_indexing
+            ):
                 # Convert key '2016-01-01' to
                 # ('2016-01-0
... (truncated)
```

**Measured before:** `AssertionError: Series Expected type <class 'pandas.core.series.Series'>, found <class 'numpy.ndarray'> instead`

**Measured after:**  `1 passed`

**The model said:** The change removes the `is_all_dates` check from the `_get_string_slice` method, which resolves the `AssertionError: Series Expected type <class 'pandas.core.series.Series'>, found <class 'numpy.ndarray'> instead` by allowing partial string indexing on non-date-like indexes.

`pandas-167` — grounded: ____   invented: ____   direction: ____

---

## 14. `httpie-2`  (httpie)

**Commit message:** Fixed --max-redirects

**Test run:** `pytest tests/test_redirects.py::TestRedirects::test_max_redirects`

```diff
diff --git a/httpie/client.py b/httpie/client.py
index 1115f4d..482f9dc 100644
--- a/httpie/client.py
+++ b/httpie/client.py
@@ -40,6 +40,7 @@ def get_response(args, config_dir):
     """Send the request and return a `request.Response`."""
 
     requests_session = get_requests_session()
+    requests_session.max_redirects = args.max_redirects
 
     if not args.session and not args.session_read_only:
         kwargs = get_requests_kwargs(args)
diff --git a/httpie/core.py b/httpie/core.py
index c0014ce..3dbe7f2 100644
--- a/httpie/core.py
+++ b/httpie/core.py
@@ -192,7 +192,6 @@ def main(args=sys.argv[1:], env=Environment(), error=None):
         error('Too many redirects (--max-redirects=%s).', args.max_redirects)
     except Exception as e:
         # TODO: Better distinction between expected and unexpected errors.
-        #       Network errors vs. bugs, etc.
         if traceback:
             raise
         msg = str(e)
```

**Measured before:** `AssertionError: assert 0 == 6`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The default value of `--max-redirects` was increased from 5 to 6, which resolved the previous failure where the test expected 0 redirects but observed 6.

`httpie-2` — grounded: ____   invented: ____   direction: ____

---

## 15. `thefuck-9`  (thefuck)

**Commit message:** Fix suggestion for `git push -u`

**Test run:** `pytest tests/rules/test_git_push.py::test_get_new_command`

```diff
diff --git a/thefuck/rules/git_push.py b/thefuck/rules/git_push.py
index 0a624eb..f64d2ce 100644
--- a/thefuck/rules/git_push.py
+++ b/thefuck/rules/git_push.py
@@ -24,7 +24,11 @@ def get_new_command(command):
         pass
     if upstream_option_index is not -1:
         command.script_parts.pop(upstream_option_index)
-        command.script_parts.pop(upstream_option_index)
+        try:
+            command.script_parts.pop(upstream_option_index)
+        except IndexError:
+            # This happens for `git push -u`
+            pass
 
     push_upstream = command.stderr.split('\n')[-3].strip().partition('git ')[2]
     return replace_argument(" ".join(command.script_parts), 'push', push_upstream)
```

**Measured before:** `IndexError: pop index out of range`

**Measured after:**  `1 passed`

**The model said:** The commit removes the second call to `command.script_parts.pop` inside the `get_new_command` function, which previously caused an `IndexError: pop index out of range` when the `git push -u` command was executed. This fix resolves the failure by preventing the script parts from being popped beyond their bounds.

`thefuck-9` — grounded: ____   invented: ____   direction: ____

---

## 16. `pandas-40`  (pandas)

**Commit message:** BUG: 27453 right merge order (#31278)

**Test run:** `pytest pandas/tests/reshape/merge/test_merge.py::TestMerge::test_merge_preserves_row_order`

```diff
diff --git a/pandas/core/reshape/merge.py b/pandas/core/reshape/merge.py
index 3b3802875..6e024560e 100644
--- a/pandas/core/reshape/merge.py
+++ b/pandas/core/reshape/merge.py
@@ -6,14 +6,14 @@ import copy
 import datetime
 from functools import partial
 import string
-from typing import TYPE_CHECKING, Optional, Tuple, Union
+from typing import TYPE_CHECKING, Optional, Tuple, Union, cast
 import warnings
 
 import numpy as np
 
 from pandas._libs import Timedelta, hashtable as libhashtable, lib
 import pandas._libs.join as libjoin
-from pandas._typing import FrameOrSeries
+from pandas._typing import ArrayLike, FrameOrSeries
 from pandas.errors import MergeError
 from pandas.util._decorators import Appender, Substitution
 
@@ -24,6 +24,7 @@ from pandas.core.dtypes.common import (
     is_array_like,
     is_bool,
     is_bool_dtype,
+    is_categorical,
     is_categorical_dtype,
     is_datetime64tz_dtype,
     is_dtype_equal,
@@ -1271,7 +1272,7 @@ def _get_join_indexers(
 
     # get left & right join labels and num. of levels at each location
     mapped = (
-        _factorize_keys(left_keys[n], right_keys[n], sort=sort)
+        _factorize_keys(left_keys[n], right_keys[n], sort=sort, how=how)
         for n in range(len(left_keys))
     )
     zipped = zip(*mapped)
@@ -1283,8 +1284,8 @@ def _get_join_indexers(
     # factorize keys to a dense i8 space
     # `count` is the num. of unique keys
     # set(lkey) | set(rkey) == range(count)
-    lkey, rkey, count = _factorize_keys(lkey, rkey, sort=sort)
 
+    lkey, rkey, count = _factorize_keys(lkey, rkey, sort=sort, how=how)
     # preserve left frame order if how == 'left' and sort == False
     kwargs = copy.copy(kwargs)
     if how == "left":
@@ -1822,7 +1823,59 @@ def _right_outer_join(x, y, max_groups):
     return left_indexer, right_indexer
 
 
-def _factorize_keys(lk, rk, sort=True):
+def _factorize_keys(
+    lk: ArrayLike, rk: ArrayLike, sort: bool = True, how: str = "inner"
+) -> Tuple[np.array, np.array, int]:
+    """
+    Encode left and right keys as enumerated types.
+
+    This is used to get the join indexers to be used when merging DataFrames.
+
+    Parameters
+    ----------
+    lk : array-like
+        Left key.
+    rk : array-like
+        Right key.
+    sort : bool, defaults to True
+        If True, the encoding is done such that the unique elements in the
+        keys are sorted.
+    how : {‘left’, ‘right’, ‘outer’, ‘inner’}, default ‘inner’
+        Type of merge.
+
+    
... (truncated)
```

**Measured before:** `AssertionError: DataFrame.iloc[:, 0] (column name="animal") are different`

**Measured after:**  `2 passed`

**The model said:** The change replaces the `is_array_like` check with `is_categorical` and `is_dtype_equal` in `_factorize_keys`, which resolves the previous failure where `AssertionError: DataFrame.iloc[:, 0] (column name="animal") are different` was raised.

`pandas-40` — grounded: ____   invented: ____   direction: ____

---

## 17. `matplotlib-27`  (matplotlib)

**Commit message:** colorbar(label=None) should give an empty label

**Test run:** `pytest lib/matplotlib/tests/test_colorbar.py::test_colorbar_label`

```diff
diff --git a/lib/matplotlib/colorbar.py b/lib/matplotlib/colorbar.py
index 22fdb6801..0100218ac 100644
--- a/lib/matplotlib/colorbar.py
+++ b/lib/matplotlib/colorbar.py
@@ -724,7 +724,7 @@ class ColorbarBase(_ColorbarMappableDummy):
 
     def set_label(self, label, **kw):
         """Label the long axis of the colorbar."""
-        self._label = str(label)
+        self._label = label
         self._labelkw = kw
         self._set_label()
```

**Measured before:** `AssertionError: assert 'None' == ''`

**Measured after:**  `1 passed`

**The model said:** The change replaces the explicit string conversion `str(label)` with the direct assignment `self._label = label`, which resolves the previous failure where the test expected `'None'` but received an empty string.

`matplotlib-27` — grounded: ____   invented: ____   direction: ____

---

## 18. `scrapy-1`  (scrapy)

**Commit message:** Fix handling of None in allowed_domains.

**Test run:** `python -m unittest -q tests.test_spidermiddleware_offsite.TestOffsiteMiddleware4._get_spiderargs`

```diff
diff --git a/scrapy/spidermiddlewares/offsite.py b/scrapy/spidermiddlewares/offsite.py
index 232e96cb..36f80969 100644
--- a/scrapy/spidermiddlewares/offsite.py
+++ b/scrapy/spidermiddlewares/offsite.py
@@ -54,12 +54,16 @@ class OffsiteMiddleware(object):
         if not allowed_domains:
             return re.compile('')  # allow all by default
         url_pattern = re.compile("^https?://.*$")
+        domains = []
         for domain in allowed_domains:
-            if url_pattern.match(domain):
+            if domain is None:
+                continue
+            elif url_pattern.match(domain):
                 message = ("allowed_domains accepts only domains, not URLs. "
                            "Ignoring URL entry %s in allowed_domains." % domain)
                 warnings.warn(message, URLWarning)
-        domains = [re.escape(d) for d in allowed_domains if d is not None]
+            else:
+                domains.append(re.escape(domain))
         regex = r'^(.*\.)?(%s)$' % '|'.join(domains)
         return re.compile(regex)
```

**Measured before:** `TypeError: expected string or bytes-like object`

**Measured after:**  `OK`

**The model said:** The change removes the `url_pattern.match(domain)` check inside the loop, which previously caused a `TypeError: expected string or bytes-like object` when encountering a `None` value in `allowed_domains`. This resolves the failure where the test previously failed with `TypeError: expected string or bytes-like object`.

`scrapy-1` — grounded: ____   invented: ____   direction: ____

---

## 19. `ansible-6`  (ansible)

**Commit message:** galaxy - Fix collection install dep resolver for bad versions (#67405)

**Test run:** `pytest test/units/galaxy/test_collection_install.py::test_build_requirement_from_path_with_manifest`

```diff
diff --git a/lib/ansible/galaxy/collection.py b/lib/ansible/galaxy/collection.py
index 24b13d97a1..4d7b327613 100644
--- a/lib/ansible/galaxy/collection.py
+++ b/lib/ansible/galaxy/collection.py
@@ -219,12 +219,15 @@ class CollectionRequirement:
                 requirement = req
                 op = operator.eq
 
-                # In the case we are checking a new requirement on a base requirement (parent != None) we can't accept
-                # version as '*' (unknown version) unless the requirement is also '*'.
-                if parent and version == '*' and requirement != '*':
-                    break
-                elif requirement == '*' or version == '*':
-                    continue
+            # In the case we are checking a new requirement on a base requirement (parent != None) we can't accept
+            # version as '*' (unknown version) unless the requirement is also '*'.
+            if parent and version == '*' and requirement != '*':
+                display.warning("Failed to validate the collection requirement '%s:%s' for %s when the existing "
+                                "install does not have a version set, the collection may not work."
+                                % (to_text(self), req, parent))
+                continue
+            elif requirement == '*' or version == '*':
+                continue
 
             if not op(LooseVersion(version), LooseVersion(requirement)):
                 break
@@ -286,7 +289,13 @@ class CollectionRequirement:
             manifest = info['manifest_file']['collection_info']
             namespace = manifest['namespace']
             name = manifest['name']
-            version = manifest['version']
+            version = to_text(manifest['version'], errors='surrogate_or_strict')
+
+            if not hasattr(LooseVersion(version), 'version'):
+                display.warning("Collection at '%s' does not have a valid version set, falling back to '*'. Found "
+                                "version: '%s'" % (to_text(b_path), version))
+                version = '*'
+
             dependencies = manifest['dependencies']
         else:
             display.warning("Collection at '%s' does not have a MANIFEST.json file, cannot detect version."
@@ -877,7 +886,7 @@ def _get_collection_info(dep_map, existing_collections, collection, requirement,
     existing = [c for c in existing_collections if to_text(c) == to_text(collection_info)]
     if existing and not collection_info.force
... (truncated)
```

**Measured before:** `AttributeError: 'float' object has no attribute 'split'`

**Measured after:**  `3 passed`

**The model said:** The change replaces `version.split()` with `to_text(manifest['version'])` in the `CollectionRequirement` class, which resolves the `AttributeError: 'float' object has no attribute 'split'` failure by ensuring the version is treated as a string rather than a float.

`ansible-6` — grounded: ____   invented: ____   direction: ____

---

## 20. `thefuck-4`  (thefuck)

**Commit message:** Support aliases with equal sign (#808)

**Test run:** `pytest tests/shells/test_fish.py::TestFish::test_get_aliases`

```diff
diff --git a/thefuck/shells/fish.py b/thefuck/shells/fish.py
index 471df2a..5693404 100644
--- a/thefuck/shells/fish.py
+++ b/thefuck/shells/fish.py
@@ -20,9 +20,17 @@ def _get_functions(overridden):
 def _get_aliases(overridden):
     aliases = {}
     proc = Popen(['fish', '-ic', 'alias'], stdout=PIPE, stderr=DEVNULL)
-    alias_out = proc.stdout.read().decode('utf-8').strip().split('\n')
-    for alias in alias_out:
-        name, value = alias.replace('alias ', '', 1).split(' ', 1)
+    alias_out = proc.stdout.read().decode('utf-8').strip()
+    if not alias_out:
+        return aliases
+    for alias in alias_out.split('\n'):
+        for separator in (' ', '='):
+            split_alias = alias.replace('alias ', '', 1).split(separator, 1)
+            if len(split_alias) == 2:
+                name, value = split_alias
+                break
+        else:
+            continue
         if name not in overridden:
             aliases[name] = value
     return aliases
```

**Measured before:** `ValueError: not enough values to unpack (expected 2, got 1)`

**Measured after:**  `1 passed`

**The model said:** The change replaces the `split(' ', 1)` call with `split(separator, 1)` to handle cases where the alias definition might include spaces after the equals sign, which previously caused the `ValueError: not enough values to unpack (expected 2, got 1)` failure.

`thefuck-4` — grounded: ____   invented: ____   direction: ____

---

## 21. `black-23`  (black)

**Commit message:** Automatic detection of deprecated Python 2 forms of print and exec

**Test run:** `python -m unittest -q tests.test_black.BlackTestCase.test_python2`

```diff
diff --git a/black.py b/black.py
index bb8ec2e..7935cdc 100644
--- a/black.py
+++ b/black.py
@@ -235,23 +235,36 @@ def format_str(src_contents: str, line_length: int) -> FileContent:
     return dst_contents
 
 
+GRAMMARS = [
+    pygram.python_grammar_no_print_statement_no_exec_statement,
+    pygram.python_grammar_no_print_statement,
+    pygram.python_grammar_no_exec_statement,
+    pygram.python_grammar,
+]
+
+
 def lib2to3_parse(src_txt: str) -> Node:
     """Given a string with source, return the lib2to3 Node."""
     grammar = pygram.python_grammar_no_print_statement
-    drv = driver.Driver(grammar, pytree.convert)
     if src_txt[-1] != '\n':
         nl = '\r\n' if '\r\n' in src_txt[:1024] else '\n'
         src_txt += nl
-    try:
-        result = drv.parse_string(src_txt, True)
-    except ParseError as pe:
-        lineno, column = pe.context[1]
-        lines = src_txt.splitlines()
+    for grammar in GRAMMARS:
+        drv = driver.Driver(grammar, pytree.convert)
         try:
-            faulty_line = lines[lineno - 1]
-        except IndexError:
-            faulty_line = "<line number missing in source>"
-        raise ValueError(f"Cannot parse: {lineno}:{column}: {faulty_line}") from None
+            result = drv.parse_string(src_txt, True)
+            break
+
+        except ParseError as pe:
+            lineno, column = pe.context[1]
+            lines = src_txt.splitlines()
+            try:
+                faulty_line = lines[lineno - 1]
+            except IndexError:
+                faulty_line = "<line number missing in source>"
+            exc = ValueError(f"Cannot parse: {lineno}:{column}: {faulty_line}")
+    else:
+        raise exc from None
 
     if isinstance(result, Leaf):
         result = Node(syms.file_input, [result])
@@ -903,6 +916,17 @@ def whitespace(leaf: Leaf) -> str:  # noqa C901
         ):
             return NO
 
+        elif (
+            prevp.type == token.RIGHTSHIFT
+            and prevp.parent
+            and prevp.parent.type == syms.shift_expr
+            and prevp.prev_sibling
+            and prevp.prev_sibling.type == token.NAME
+            and prevp.prev_sibling.value == 'print'
+        ):
+            # Python 2 print chevron
+            return NO
+
     elif prev.type in OPENING_BRACKETS:
         return NO
 
@@ -1538,7 +1562,12 @@ def assert_equivalent(src: str, dst: str) -> None:
     try:
         src_ast = ast.parse(src)
     except Exception as exc:
-        raise AssertionEr
... (truncated)
```

**Measured before:** `AssertionError: '#!/u[39 chars]nt >>sys.stderr, "Warning:",\nprint >>sys.stde[214 chars]))\n' != '#!/u[39 chars]nt >> sys.stderr, "Warning:",\nprint >> sys.st[217 chars]))\n'`

**Measured after:**  `OK`

**The model said:** The commit removes the `print >>` syntax from the test, which previously caused the assertion `AssertionError: '#!/u[39 chars]nt >>sys.stderr, 

`black-23` — grounded: ____   invented: ____   direction: ____

---

## 22. `thefuck-29`  (thefuck)

**Commit message:** Fix the @wrap_settings annotation

**Test run:** `pytest tests/test_types.py::test_update_settings`

```diff
diff --git a/thefuck/types.py b/thefuck/types.py
index cc48138..2e5b41a 100644
--- a/thefuck/types.py
+++ b/thefuck/types.py
@@ -23,7 +23,9 @@ class Settings(dict):
         return self.get(item)
 
     def update(self, **kwargs):
-        """Returns new settings with new values from `kwargs`."""
-        conf = dict(self)
-        conf.update(kwargs)
+        """
+        Returns new settings with values from `kwargs` for unset settings.
+        """
+        conf = dict(kwargs)
+        conf.update(self)
         return Settings(conf)
```

**Measured before:** `AssertionError: assert 'new-val' == 'val'`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The docstring of the `update` method was updated to include a comment about updating values for unset settings, which resolved the previous failure where the test expected `'new-val'` but got `'val'`.

`thefuck-29` — grounded: ____   invented: ____   direction: ____

---

## 23. `pandas-54`  (pandas)

**Commit message:** BUG: disallow invalid dtype to CategoricalDtype._from_values_or_dtype (#32169)

**Test run:** `pytest pandas/tests/dtypes/test_dtypes.py::TestCategoricalDtype::test_from_values_or_dtype_invalid_dtype`

```diff
diff --git a/pandas/core/dtypes/dtypes.py b/pandas/core/dtypes/dtypes.py
index d93ad973f..0730de934 100644
--- a/pandas/core/dtypes/dtypes.py
+++ b/pandas/core/dtypes/dtypes.py
@@ -324,6 +324,8 @@ class CategoricalDtype(PandasExtensionDtype, ExtensionDtype):
                 raise ValueError(
                     "Cannot specify `categories` or `ordered` together with `dtype`."
                 )
+            elif not isinstance(dtype, CategoricalDtype):
+                raise ValueError(f"Cannot not construct CategoricalDtype from {dtype}")
         elif is_categorical(values):
             # If no "dtype" was passed, use the one from "values", but honor
             # the "ordered" and "categories" arguments
diff --git a/pandas/tests/indexes/common.py b/pandas/tests/indexes/common.py
index 2073aa072..c9e762af3 100644
--- a/pandas/tests/indexes/common.py
+++ b/pandas/tests/indexes/common.py
@@ -605,7 +605,8 @@ class Base:
         assert not indices.equals(np.array(indices))
 
         # Cannot pass in non-int64 dtype to RangeIndex
-        if not isinstance(indices, RangeIndex):
+        if not isinstance(indices, (RangeIndex, CategoricalIndex)):
+            # TODO: CategoricalIndex can be re-allowed following GH#32167
             same_values = Index(indices, dtype=object)
             assert indices.equals(same_values)
             assert same_values.equals(indices)
```

**Measured before:** `Failed: DID NOT RAISE <class 'ValueError'>`

**Measured after:**  `1 passed`

**The model said:** The change removes the `RangeIndex` check from the `Base` class, which previously prevented the creation of a `CategoricalIndex` from a non-int64 dtype. This resolves the failure where the test did not raise `ValueError` before the change.

`pandas-54` — grounded: ____   invented: ____   direction: ____

---

## 24. `pandas-35`  (pandas)

**Commit message:** BUG: create new MI from MultiIndex._get_level_values (#33134)

**Test run:** `pytest pandas/tests/indexes/multi/test_get_level_values.py::test_get_level_values_when_periods`

```diff
diff --git a/pandas/core/indexes/period.py b/pandas/core/indexes/period.py
index 0646acab5..8aaf82878 100644
--- a/pandas/core/indexes/period.py
+++ b/pandas/core/indexes/period.py
@@ -324,8 +324,8 @@ class PeriodIndex(DatetimeIndexOpsMixin, Int64Index):
 
     @cache_readonly
     def _engine(self):
-        # To avoid a reference cycle, pass a weakref of self to _engine_type.
-        period = weakref.ref(self)
+        # To avoid a reference cycle, pass a weakref of self._values to _engine_type.
+        period = weakref.ref(self._values)
         return self._engine_type(period, len(self))
 
     @doc(Index.__contains__)
```

**Measured before:** `AttributeError: 'NoneType' object has no attribute 'view'`

**Measured after:**  `1 passed`

**The model said:** The change replaces `self` with `self._values` in the `_engine` method, which resolves the `AttributeError: 'NoneType' object has no attribute 'view'` by ensuring the correct type is used for indexing operations.

`pandas-35` — grounded: ____   invented: ____   direction: ____

---

## 25. `scrapy-10`  (scrapy)

**Commit message:** Do not interpret non-ASCII bytes in "Location" and percent-encode them (#2322)

**Test run:** `python -m unittest -q tests.test_downloadermiddleware_redirect.RedirectMiddlewareTest.test_latin1_location`

```diff
diff --git a/scrapy/downloadermiddlewares/redirect.py b/scrapy/downloadermiddlewares/redirect.py
index 4ed7e4c2..db276eef 100644
--- a/scrapy/downloadermiddlewares/redirect.py
+++ b/scrapy/downloadermiddlewares/redirect.py
@@ -1,9 +1,10 @@
 import logging
 from six.moves.urllib.parse import urljoin
 
+from w3lib.url import safe_url_string
+
 from scrapy.http import HtmlResponse
 from scrapy.utils.response import get_meta_refresh
-from scrapy.utils.python import to_native_str
 from scrapy.exceptions import IgnoreRequest, NotConfigured
 
 logger = logging.getLogger(__name__)
@@ -65,8 +66,7 @@ class RedirectMiddleware(BaseRedirectMiddleware):
         if 'Location' not in response.headers or response.status not in allowed_status:
             return response
 
-        # HTTP header is ascii or latin1, redirected url will be percent-encoded utf-8
-        location = to_native_str(response.headers['location'].decode('latin1'))
+        location = safe_url_string(response.headers['location'])
 
         redirected_url = urljoin(request.url, location)
```

**Measured before:** `AssertionError: 'http://scrapytest.org/a%C3%A7%C3%A3o' != 'http://scrapytest.org/a%C3%83%C2%A7%C3%83%C2%A3o'`

**Measured after:**  `OK`

**The model said:** The change replaces `to_native_str` with `safe_url_string` to ensure that the URL encoding is handled correctly, which resolves the previous failure where the percent-encoded UTF-8 characters were incorrectly decoded as Latin-1.

`scrapy-10` — grounded: ____   invented: ____   direction: ____

---

## 26. `youtube-dl-18`  (youtube-dl)

**Commit message:** [YoutubeDL] Do not override id, extractor and extractor_key in url_transparent All these meta fields must be borrowed from final extractor that actually performs extraction. This commit fixes extracto

**Test run:** `python -m unittest -q test.test_YoutubeDL.TestYoutubeDL.test_do_not_override_ie_key_in_url_transparent`

```diff
diff --git a/youtube_dl/YoutubeDL.py b/youtube_dl/YoutubeDL.py
index 89c07be29..f94836d06 100755
--- a/youtube_dl/YoutubeDL.py
+++ b/youtube_dl/YoutubeDL.py
@@ -860,7 +860,7 @@ class YoutubeDL(object):
 
             force_properties = dict(
                 (k, v) for k, v in ie_result.items() if v is not None)
-            for f in ('_type', 'url', 'ie_key'):
+            for f in ('_type', 'url', 'id', 'extractor', 'extractor_key', 'ie_key'):
                 if f in force_properties:
                     del force_properties[f]
             new_result = info.copy()
```

**Measured before:** `AssertionError: 'foo1_id' != 'testid'`

**Measured after:**  `OK`

**The model said:** The commit removes the `id` field from the `force_properties` dictionary, which resolves the failure `AssertionError: 'foo1_id' != 'testid'` by ensuring the extracted ID matches the expected value.

`youtube-dl-18` — grounded: ____   invented: ____   direction: ____

---

## 27. `matplotlib-2`  (matplotlib)

**Commit message:** Fix colors for scatter() with unfilled markers

**Test run:** `pytest lib/matplotlib/tests/test_axes.py::TestScatter::test_scatter_unfilled`

```diff
diff --git a/lib/matplotlib/axes/_axes.py b/lib/matplotlib/axes/_axes.py
index f1a16cbd6..81f8aa4ee 100644
--- a/lib/matplotlib/axes/_axes.py
+++ b/lib/matplotlib/axes/_axes.py
@@ -4393,8 +4393,9 @@ default: :rc:`scatter.edgecolors`
             - 'none': No patch boundary will be drawn.
             - A color or sequence of colors.
 
-            For non-filled markers, the *edgecolors* kwarg is ignored and
-            forced to 'face' internally.
+            For non-filled markers, *edgecolors* is ignored. Instead, the color
+            is determined like with 'face', i.e. from *c*, *colors*, or
+            *facecolors*.
 
         plotnonfinite : bool, default: False
             Set to plot points with nonfinite *c*, in conjunction with
@@ -4476,7 +4477,6 @@ default: :rc:`scatter.edgecolors`
         path = marker_obj.get_path().transformed(
             marker_obj.get_transform())
         if not marker_obj.is_filled():
-            edgecolors = 'face'
             if linewidths is None:
                 linewidths = rcParams['lines.linewidth']
             elif np.iterable(linewidths):
@@ -4488,8 +4488,8 @@ default: :rc:`scatter.edgecolors`
 
         collection = mcoll.PathCollection(
                 (path,), scales,
-                facecolors=colors,
-                edgecolors=edgecolors,
+                facecolors=colors if marker_obj.is_filled() else 'none',
+                edgecolors=edgecolors if marker_obj.is_filled() else colors,
                 linewidths=linewidths,
                 offsets=offsets,
                 transOffset=kwargs.pop('transform', self.transData),
```

**Measured before:** `assert (3, 4) == (0, 4)`

**Measured after:**  `1 passed`

**The model said:** The change removes the explicit setting of `edgecolors='face'` for non-filled markers, which previously caused the test `(3, 4) == (0, 4)` to fail. The behavior now defaults to using the color specified by `c`, `colors`, or `facecolors`, resolving the failure.

`matplotlib-2` — grounded: ____   invented: ____   direction: ____

---

## 28. `scrapy-22`  (scrapy)

**Commit message:** Fixed bug on XMLItemExporter with non-string fields in items

**Test run:** `python -m unittest -q tests.test_exporters.XmlItemExporterTest.test_nonstring_types_item`

```diff
diff --git a/scrapy/exporters.py b/scrapy/exporters.py
index 35f50838..360007c0 100644
--- a/scrapy/exporters.py
+++ b/scrapy/exporters.py
@@ -144,8 +144,10 @@ class XmlItemExporter(BaseItemExporter):
         elif is_listlike(serialized_value):
             for value in serialized_value:
                 self._export_xml_field('value', value)
-        else:
+        elif isinstance(serialized_value, six.text_type):
             self._xg_characters(serialized_value)
+        else:
+            self._xg_characters(str(serialized_value))
         self.xg.endElement(name)
 
     # Workaround for http://bugs.python.org/issue17606
```

**Measured before:** `AttributeError: 'bool' object has no attribute 'decode'`

**Measured after:**  `OK`

**The model said:** The change replaces `serialized_value.decode()` with `str(serialized_value)`, which resolves the `AttributeError: 'bool' object has no attribute 'decode'` by ensuring the input is always treated as a string.

`scrapy-22` — grounded: ____   invented: ____   direction: ____

---

## 29. `fastapi-12`  (fastapi)

**Commit message:** :bug: Fix HTTP Bearer security auto-error (#282)

**Test run:** `pytest tests/test_security_http_bearer_optional.py::test_security_http_bearer_incorrect_scheme_credentials`

```diff
diff --git a/fastapi/security/http.py b/fastapi/security/http.py
index f41d8d9..362390b 100644
--- a/fastapi/security/http.py
+++ b/fastapi/security/http.py
@@ -112,10 +112,13 @@ class HTTPBearer(HTTPBase):
             else:
                 return None
         if scheme.lower() != "bearer":
-            raise HTTPException(
-                status_code=HTTP_403_FORBIDDEN,
-                detail="Invalid authentication credentials",
-            )
+            if self.auto_error:
+                raise HTTPException(
+                    status_code=HTTP_403_FORBIDDEN,
+                    detail="Invalid authentication credentials",
+                )
+            else:
+                return None
         return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
```

**Measured before:** `assert 403 == 200`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `auto_error` flag was removed from the `HTTPBearer` class, which resolved the previous assertion failure where the response status code was 403 instead of 200.

`fastapi-12` — grounded: ____   invented: ____   direction: ____

---

## 30. `thefuck-2`  (thefuck)

**Commit message:** #902: Use `os.pathsep` to split PATH env var (#917)

**Test run:** `pytest tests/test_utils.py::test_get_all_executables_pathsep`

```diff
diff --git a/thefuck/utils.py b/thefuck/utils.py
index bd8028e..6112c01 100644
--- a/thefuck/utils.py
+++ b/thefuck/utils.py
@@ -118,7 +118,7 @@ def get_all_executables():
     tf_entry_points = ['thefuck', 'fuck']
 
     bins = [exe.name.decode('utf8') if six.PY2 else exe.name
-            for path in os.environ.get('PATH', '').split(':')
+            for path in os.environ.get('PATH', '').split(os.pathsep)
             for exe in _safe(lambda: list(Path(path).iterdir()), [])
             if not _safe(exe.is_dir, True)
             and exe.name not in tf_entry_points]
```

**Measured before:** `AssertionError: 'Path' does not contain all of (call('C:\\\\foo'), call('C:\\\\bar'), call('C:\\\\baz'), call('C:\\\\foo\\\\bar')) in its call list, found [call('C'), call().iterdir(), call().iterdir().__iter__(), call().iterdir().__len__(), call('\\\\foo;C'), call().iterdir(), call().iterdir().__iter__(), call().iterdir().__len__(), call('\\\\bar;C'), call().iterdir(), call().iterdir().__iter__()`

**Measured after:**  `2 passed`

**The model said:** The commit replaces the hardcoded `':'` separator with `os.pathsep`, which resolves the failure `AssertionError: 'Path' does not contain all of (call('C:\foo'), call('C:\bar'), call('C:\baz'), call('C:\foo\\bar')) in its call list, found [call('C'), call().iterdir(), call().iterdir().__iter__(), call().iterdir().__len__(), call('\\foo;C'), call().iterdir(), call().iterdir().__iter__(), call().iterdir().__len__(), call('\\bar;

`thefuck-2` — grounded: ____   invented: ____   direction: ____

---

## 31. `pandas-45`  (pandas)

**Commit message:** BUG: Don't multiply sets during construction (#32594)

**Test run:** `pytest pandas/tests/frame/test_constructors.py::TestDataFrameConstructorWithDatetimeTZ::test_construction_from_set_raises`

```diff
diff --git a/pandas/core/construction.py b/pandas/core/construction.py
index e2d8fba8d..c9754ff58 100644
--- a/pandas/core/construction.py
+++ b/pandas/core/construction.py
@@ -5,6 +5,7 @@ and Index.__new__.
 These should not depend on core.internals.
 """
 
+from collections import abc
 from typing import TYPE_CHECKING, Any, Optional, Sequence, Union, cast
 
 import numpy as np
@@ -446,6 +447,8 @@ def sanitize_array(
         # GH#16804
         arr = np.arange(data.start, data.stop, data.step, dtype="int64")
         subarr = _try_cast(arr, dtype, copy, raise_cast_failure)
+    elif isinstance(data, abc.Set):
+        raise TypeError("Set type is unordered")
     else:
         subarr = _try_cast(data, dtype, copy, raise_cast_failure)
```

**Measured before:** `Failed: DID NOT RAISE <class 'TypeError'>`

**Measured after:**  `1 passed`

**The model said:** The change removes the `isinstance(data, abc.Set)` check, which previously prevented the `TypeError: Set type is unordered` from being raised when constructing a Series from a set. This resolves the failure where the test previously failed with "DID NOT RAISE <class 'TypeError'>".

`pandas-45` — grounded: ____   invented: ____   direction: ____

---

## 32. `pandas-33`  (pandas)

**Commit message:** BUG: Don't raise on value_counts for empty Int64 (#33339)

**Test run:** `pytest pandas/tests/arrays/integer/test_function.py::test_value_counts_empty`

```diff
diff --git a/pandas/core/arrays/integer.py b/pandas/core/arrays/integer.py
index 4f3c68aa0..f5189068d 100644
--- a/pandas/core/arrays/integer.py
+++ b/pandas/core/arrays/integer.py
@@ -499,7 +499,8 @@ class IntegerArray(BaseMaskedArray):
         ExtensionArray.argsort
         """
         data = self._data.copy()
-        data[self._mask] = data.min() - 1
+        if self._mask.any():
+            data[self._mask] = data.min() - 1
         return data
 
     @classmethod
```

**Measured before:** `ValueError: zero-size array to reduction operation minimum which has no identity`

**Measured after:**  `1 passed`

**The model said:** The change replaces the `min() - 1` assignment with an explicit check for the mask, which prevents the `ValueError: zero-size array to reduction operation minimum which has no identity` when the array is empty.

`pandas-33` — grounded: ____   invented: ____   direction: ____

---

## 33. `scrapy-23`  (scrapy)

**Commit message:** py3 fix HttpProxy and Retry Middlewares

**Test run:** `python -m unittest -q tests.test_downloadermiddleware_httpproxy.TestDefaultHeadersMiddleware.test_proxy_auth`

```diff
diff --git a/scrapy/downloadermiddlewares/httpproxy.py b/scrapy/downloadermiddlewares/httpproxy.py
index dda6a3d2..8c3514fd 100644
--- a/scrapy/downloadermiddlewares/httpproxy.py
+++ b/scrapy/downloadermiddlewares/httpproxy.py
@@ -9,7 +9,7 @@ from six.moves.urllib.parse import urlunparse
 
 from scrapy.utils.httpobj import urlparse_cached
 from scrapy.exceptions import NotConfigured
-
+from scrapy.utils.python import to_bytes
 
 class HttpProxyMiddleware(object):
 
@@ -26,7 +26,7 @@ class HttpProxyMiddleware(object):
         proxy_url = urlunparse((proxy_type or orig_type, hostport, '', '', '', ''))
 
         if user:
-            user_pass = '%s:%s' % (unquote(user), unquote(password))
+            user_pass = to_bytes('%s:%s' % (unquote(user), unquote(password)))
             creds = base64.b64encode(user_pass).strip()
         else:
             creds = None
@@ -52,4 +52,4 @@ class HttpProxyMiddleware(object):
         creds, proxy = self.proxies[scheme]
         request.meta['proxy'] = proxy
         if creds:
-            request.headers['Proxy-Authorization'] = 'Basic ' + creds
+            request.headers['Proxy-Authorization'] = b'Basic ' + creds
diff --git a/tests/test_downloadermiddleware_retry.py b/tests/test_downloadermiddleware_retry.py
index 20561e77..3de9399c 100644
--- a/tests/test_downloadermiddleware_retry.py
+++ b/tests/test_downloadermiddleware_retry.py
@@ -21,20 +21,20 @@ class RetryTest(unittest.TestCase):
 
     def test_priority_adjust(self):
         req = Request('http://www.scrapytest.org/503')
-        rsp = Response('http://www.scrapytest.org/503', body='', status=503)
+        rsp = Response('http://www.scrapytest.org/503', body=b'', status=503)
         req2 = self.mw.process_response(req, rsp, self.spider)
         assert req2.priority < req.priority
 
     def test_404(self):
         req = Request('http://www.scrapytest.org/404')
-        rsp = Response('http://www.scrapytest.org/404', body='', status=404)
+        rsp = Response('http://www.scrapytest.org/404', body=b'', status=404)
 
         # dont retry 404s
         assert self.mw.process_response(req, rsp, self.spider) is rsp
 
     def test_dont_retry(self):
         req = Request('http://www.scrapytest.org/503', meta={'dont_retry': True})
-        rsp = Response('http://www.scrapytest.org/503', body='', status=503)
+        rsp = Response('http://www.scrapytest.org/503', body=b'', status=503)
 
         # first retry
         r = self.mw.process_response(req, rsp
... (truncated)
```

**Measured before:** `TypeError: a bytes-like object is required, not 'str'`

**Measured after:**  `OK`

**The model said:** The change replaces `unquote` with `to_bytes` in the `HttpProxyMiddleware`, which resolves the `TypeError: a bytes-like object is required, not 'str'` failure observed in the `test_503` method of `RetryTest`.

`scrapy-23` — grounded: ____   invented: ____   direction: ____

---

## 34. `matplotlib-24`  (matplotlib)

**Commit message:** Backport PR #14677: Don't misclip axis when calling set_ticks on inverted axes.

**Test run:** `pytest lib/matplotlib/tests/test_axes.py::test_set_ticks_inverted`

```diff
diff --git a/lib/matplotlib/axis.py b/lib/matplotlib/axis.py
index f645b4b44..a4cdffc55 100644
--- a/lib/matplotlib/axis.py
+++ b/lib/matplotlib/axis.py
@@ -1892,7 +1892,7 @@ def _make_getset_interval(method_name, lim_name, attr_name):
                 setter(self, min(vmin, vmax, oldmin), max(vmin, vmax, oldmax),
                        ignore=True)
             else:
-                setter(self, max(vmin, vmax, oldmax), min(vmin, vmax, oldmin),
+                setter(self, max(vmin, vmax, oldmin), min(vmin, vmax, oldmax),
                        ignore=True)
         self.stale = True
```

**Measured before:** `assert (0.7, 0.3) == (1, 0)`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The order of the `setter` calls in `_make_getset_interval` was swapped, which corrected the behavior where the minimum value was incorrectly clipped to the maximum instead of vice versa. This resolved the failure `assert (0.7, 0.3) == (1, 0)`, which previously occurred because the axis limits were inverted.

`matplotlib-24` — grounded: ____   invented: ____   direction: ____

---

## 35. `youtube-dl-35`  (youtube-dl)

**Commit message:** [arte] Fix upload date extraction

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_unified_dates`

```diff
diff --git a/youtube_dl/extractor/arte.py b/youtube_dl/extractor/arte.py
index 957d35979..c3d02f85e 100644
--- a/youtube_dl/extractor/arte.py
+++ b/youtube_dl/extractor/arte.py
@@ -86,11 +86,15 @@ class ArteTVPlus7IE(InfoExtractor):
         info = self._download_json(json_url, video_id)
         player_info = info['videoJsonPlayer']
 
+        upload_date_str = player_info.get('shootingDate')
+        if not upload_date_str:
+            upload_date_str = player_info.get('VDA', '').split(' ')[0]
+
         info_dict = {
             'id': player_info['VID'],
             'title': player_info['VTI'],
             'description': player_info.get('VDE'),
-            'upload_date': unified_strdate(player_info.get('VDA', '').split(' ')[0]),
+            'upload_date': unified_strdate(upload_date_str),
             'thumbnail': player_info.get('programImage') or player_info.get('VTU', {}).get('IUR'),
         }
 
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index 950cd1a7a..f05747097 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -890,6 +890,7 @@ def unified_strdate(date_str):
         '%d/%m/%Y',
         '%d/%m/%y',
         '%Y/%m/%d %H:%M:%S',
+        '%d/%m/%Y %H:%M:%S',
         '%Y-%m-%d %H:%M:%S',
         '%d.%m.%Y %H:%M',
         '%d.%m.%Y %H.%M',
```

**Measured before:** `AssertionError: None != '20140128'`

**Measured after:**  `OK`

**The model said:** The change replaces the direct string split in `unified_strdate` with a direct lookup of the `shootingDate` field, which resolves the previous failure where the upload date was incorrectly parsed as `None`.

`youtube-dl-35` — grounded: ____   invented: ____   direction: ____

---

## 36. `luigi-25`  (luigi)

**Commit message:** Merge pull request #996 from kianho/fix-995

**Test run:** `pytest test/contrib/redshift_test.py::TestS3CopyToTable::test_s3_copy_to_table`

```diff
diff --git a/luigi/contrib/redshift.py b/luigi/contrib/redshift.py
index af0223ea..93d5a392 100644
--- a/luigi/contrib/redshift.py
+++ b/luigi/contrib/redshift.py
@@ -163,7 +163,7 @@ class S3CopyToTable(rdbms.CopyToTable):
         if not (self.table):
             raise Exception("table need to be specified")
 
-        path = self.s3_load_path()
+        path = self.s3_load_path
         connection = self.output().connect()
         if not self.does_table_exist(connection):
             # try creating table
```

**Measured before:** `TypeError: 'str' object is not callable`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The change replaces the call to `self.s3_load_path()` with a direct attribute access `self.s3_load_path`, which resolves the `TypeError: 'str' object is not callable'` observed in the project's own tests.

`luigi-25` — grounded: ____   invented: ____   direction: ____

---

## 37. `ansible-5`  (ansible)

**Commit message:** Fix and add tests for some module_utils.common.validation (#67771)

**Test run:** `pytest test/units/module_utils/common/validation/test_check_required_arguments.py::test_check_required_arguments_missing_multiple`

```diff
diff --git a/lib/ansible/module_utils/common/validation.py b/lib/ansible/module_utils/common/validation.py
index 4c29c8b234..fc13f4d0aa 100644
--- a/lib/ansible/module_utils/common/validation.py
+++ b/lib/ansible/module_utils/common/validation.py
@@ -189,7 +189,7 @@ def check_required_arguments(argument_spec, module_parameters):
             missing.append(k)
 
     if missing:
-        msg = "missing required arguments: %s" % ", ".join(missing)
+        msg = "missing required arguments: %s" % ", ".join(sorted(missing))
         raise TypeError(to_native(msg))
 
     return missing
diff --git a/test/units/module_utils/common/validation/test_check_mutually_exclusive.py b/test/units/module_utils/common/validation/test_check_mutually_exclusive.py
index 5d44f85151..7bf90760b1 100644
--- a/test/units/module_utils/common/validation/test_check_mutually_exclusive.py
+++ b/test/units/module_utils/common/validation/test_check_mutually_exclusive.py
@@ -34,11 +34,12 @@ def test_check_mutually_exclusive_found(mutually_exclusive_terms):
         'fox': 'red',
         'socks': 'blue',
     }
-    expected = "TypeError('parameters are mutually exclusive: string1|string2, box|fox|socks',)"
+    expected = "parameters are mutually exclusive: string1|string2, box|fox|socks"
 
     with pytest.raises(TypeError) as e:
         check_mutually_exclusive(mutually_exclusive_terms, params)
-        assert e.value == expected
+
+    assert to_native(e.value) == expected
 
 
 def test_check_mutually_exclusive_none():
@@ -53,4 +54,4 @@ def test_check_mutually_exclusive_none():
 def test_check_mutually_exclusive_no_params(mutually_exclusive_terms):
     with pytest.raises(TypeError) as te:
         check_mutually_exclusive(mutually_exclusive_terms, None)
-        assert "TypeError: 'NoneType' object is not iterable" in to_native(te.error)
+    assert "'NoneType' object is not iterable" in to_native(te.value)
```

**Measured before:** `AssertionError: assert 'missing requ...nts: foo, bar' == 'missing requ...nts: bar, foo'`

**Measured after:**  `1 passed`

**The model said:** The order of the missing arguments in the error message was corrected from "foo, bar" to "bar, foo", which resolved the previous failure `AssertionError: assert 'missing requ...nts: foo, bar' == 'missing requ...nts: bar, foo'`.

`ansible-5` — grounded: ____   invented: ____   direction: ____

---

## 38. `pandas-161`  (pandas)

**Commit message:** BUG: Ensure that fill_na in Categorical only replaces null values (#27932)

**Test run:** `pytest pandas/tests/series/test_missing.py::TestSeriesMissingData::test_fillna_categorical_with_new_categories`

```diff
diff --git a/pandas/core/arrays/categorical.py b/pandas/core/arrays/categorical.py
index bbbeb812d..a895da618 100644
--- a/pandas/core/arrays/categorical.py
+++ b/pandas/core/arrays/categorical.py
@@ -1840,8 +1840,8 @@ class Categorical(ExtensionArray, PandasObject):
                     raise ValueError("fill value must be in categories")
 
                 values_codes = _get_codes_for_values(value, self.categories)
-                indexer = np.where(values_codes != -1)
-                codes[indexer] = values_codes[values_codes != -1]
+                indexer = np.where(codes == -1)
+                codes[indexer] = values_codes[indexer]
 
             # If value is not a dict or Series it should be a scalar
             elif is_hashable(value):
```

**Measured before:** `AssertionError: Series are different`

**Measured after:**  `3 passed`

**The model said:** The change replaces `np.where` with direct indexing to update the `codes` array when `fill_na` encounters null values, which resolves the previous `AssertionError: Series are different`.

`pandas-161` — grounded: ____   invented: ____   direction: ____

---

## 39. `luigi-23`  (luigi)

**Commit message:** Fix #1023 add pruning on get_work of local scheduler

**Test run:** `pytest test/worker_external_task_test.py::WorkerExternalTaskTest::test_external_dependency_completes_later`

```diff
diff --git a/luigi/interface.py b/luigi/interface.py
index 0a15fc69..860c1596 100644
--- a/luigi/interface.py
+++ b/luigi/interface.py
@@ -109,7 +109,7 @@ class core(task.Config):
 class WorkerSchedulerFactory(object):
 
     def create_local_scheduler(self):
-        return scheduler.CentralPlannerScheduler()
+        return scheduler.CentralPlannerScheduler(prune_on_get_work=True)
 
     def create_remote_scheduler(self, host, port):
         return rpc.RemoteScheduler(host=host, port=port)
diff --git a/luigi/scheduler.py b/luigi/scheduler.py
index bbd00efa..81dafb15 100644
--- a/luigi/scheduler.py
+++ b/luigi/scheduler.py
@@ -101,6 +101,8 @@ class scheduler(Config):
 
     visualization_graph = parameter.Parameter(default="svg", config_path=dict(section='scheduler', name='visualization-graph'))
 
+    prune_on_get_work = parameter.BoolParameter(default=False)
+
 
 def fix_time(x):
     # Backwards compatibility for a fix in Dec 2014. Prior to the fix, pickled state might store datetime objects
@@ -227,7 +229,7 @@ class Worker(object):
     def __init__(self, worker_id, last_active=None):
         self.id = worker_id
         self.reference = None  # reference to the worker in the real world. (Currently a dict containing just the host)
-        self.last_active = last_active  # seconds since epoch
+        self.last_active = last_active or time.time()  # seconds since epoch
         self.started = time.time()  # seconds since epoch
         self.tasks = set()  # task objects
         self.info = {}
@@ -710,6 +712,9 @@ class CentralPlannerScheduler(Scheduler):
         # TODO: remove tasks that can't be done, figure out if the worker has absolutely
         # nothing it can wait for
 
+        if self._config.prune_on_get_work:
+            self.prune()
+
         worker_id = kwargs['worker']
         # Return remaining tasks that have no FAILED descendents
         self.update(worker_id, {'host': host})
```

**Measured before:** `luigi.parameter.UnknownParameterException: scheduler[args=(), kwargs={'retry_delay': 0.01, 'remove_delay': 3, 'worker_disconnect_delay': 3, 'disable_persist': 3, 'disable_window': 5, 'disable_failures': 2, 'prune_on_get_work': True}]: unknown parameter prune_on_get_work`

**Measured after:**  `1 passed, 13 warnings`

**The model said:** The `prune_on_get_work` parameter was added to the `CentralPlannerScheduler` configuration, which resolved the `UnknownParameterException: scheduler[args=(), kwargs={'retry_delay': 0.01, 'remove_delay': 3, 'worker_disconnect_delay': 3, 'disable_persist': 3, 'disable_window': 5, 'disable_failures': 2, 'prune_on_get_work': True}]: unknown parameter prune_on_get_work` error.

`luigi-23` — grounded: ____   invented: ____   direction: ____

---

## 40. `luigi-15`  (luigi)

**Commit message:** assistants bugfix: Also prune UNKNOWN tasks

**Test run:** `pytest test/central_planner_test.py::CentralPlannerTest::test_assistants_dont_nurture_finished_statuses`

```diff
diff --git a/luigi/scheduler.py b/luigi/scheduler.py
index d67beb9e..bb419af2 100644
--- a/luigi/scheduler.py
+++ b/luigi/scheduler.py
@@ -482,8 +482,8 @@ class SimpleTaskState(object):
     def get_necessary_tasks(self):
         necessary_tasks = set()
         for task in self.get_active_tasks():
-            if task.status not in (DONE, DISABLED) or \
-                    getattr(task, 'scheduler_disable_time', None) is not None:
+            if task.status not in (DONE, DISABLED, UNKNOWN) or \
+                    task.scheduler_disable_time is not None:
                 necessary_tasks.update(task.deps)
                 necessary_tasks.add(task.id)
         return necessary_tasks
```

**Measured before:** `AssertionError: Items in the second set but not the first:`

**Measured after:**  `1 passed, 2 warnings`

**The model said:** The change removes the `UNKNOWN` status check from the `SimpleTaskState.get_necessary_tasks` method, which resolves the `AssertionError: Items in the second set but not the first:` failure by excluding tasks with the `UNKNOWN` status from the necessary tasks calculation.

`luigi-15` — grounded: ____   invented: ____   direction: ____

---

## 41. `tornado-1`  (tornado)

**Commit message:** websocket: Fix set_nodelay

**Test run:** `python -m unittest -q tornado.test.websocket_test.WebSocketTest.test_nodelay`

```diff
diff --git a/tornado/websocket.py b/tornado/websocket.py
index 00d08bab..d991fee5 100644
--- a/tornado/websocket.py
+++ b/tornado/websocket.py
@@ -558,8 +558,8 @@ class WebSocketHandler(tornado.web.RequestHandler):
 
         .. versionadded:: 3.1
         """
-        assert self.stream is not None
-        self.stream.set_nodelay(value)
+        assert self.ws_connection is not None
+        self.ws_connection.set_nodelay(value)
 
     def on_connection_close(self) -> None:
         if self.ws_connection:
@@ -714,6 +714,10 @@ class WebSocketProtocol(abc.ABC):
     async def _receive_frame_loop(self) -> None:
         raise NotImplementedError()
 
+    @abc.abstractmethod
+    def set_nodelay(self, x: bool) -> None:
+        raise NotImplementedError()
+
 
 class _PerMessageDeflateCompressor(object):
     def __init__(
@@ -1345,6 +1349,9 @@ class WebSocketProtocol13(WebSocketProtocol):
         self.write_ping(b"")
         self.last_ping = now
 
+    def set_nodelay(self, x: bool) -> None:
+        self.stream.set_nodelay(x)
+
 
 class WebSocketClientConnection(simple_httpclient._HTTPConnection):
     """WebSocket client connection.
```

**Measured before:** `AssertionError: None != 'hello'`

**Measured after:**  `OK`

**The model said:** The `set_nodelay` method was renamed from `self.stream.set_nodelay` to `self.ws_connection.set_nodelay`, which resolved the previous failure where the assertion `None != 'hello'` was raised.

`tornado-1` — grounded: ____   invented: ____   direction: ____

---

## 42. `pandas-88`  (pandas)

**Commit message:** BUG: pivot_table with multi-index columns only fails (#31013)

**Test run:** `pytest pandas/tests/reshape/test_pivot.py::TestPivotTable::test_pivot_table_multiindex_only`

```diff
diff --git a/pandas/core/reshape/pivot.py b/pandas/core/reshape/pivot.py
index b443ba142..7109f2376 100644
--- a/pandas/core/reshape/pivot.py
+++ b/pandas/core/reshape/pivot.py
@@ -117,7 +117,9 @@ def pivot_table(
                 agged[v] = maybe_downcast_to_dtype(agged[v], data[v].dtype)
 
     table = agged
-    if table.index.nlevels > 1:
+
+    # GH17038, this check should only happen if index is defined (not None)
+    if table.index.nlevels > 1 and index:
         # Related GH #17123
         # If index_names are integers, determine whether the integers refer
         # to the level position or name.
```

**Measured before:** `AttributeError: 'Series' object has no attribute 'columns'`

**Measured after:**  `4 passed`

**The model said:** The check for `table.index.nlevels > 1` was added to ensure the index is defined before attempting to access its `columns` attribute, which resolves the `AttributeError: 'Series' object has no attribute 'columns'` failure.

`pandas-88` — grounded: ____   invented: ____   direction: ____

---

## 43. `pandas-140`  (pandas)

**Commit message:** Bugfix/groupby datetime issue (#28569)

**Test run:** `pytest pandas/tests/groupby/test_apply.py::test_apply_datetime_issue`

```diff
diff --git a/pandas/core/groupby/generic.py b/pandas/core/groupby/generic.py
index b5aec1897..e556708dc 100644
--- a/pandas/core/groupby/generic.py
+++ b/pandas/core/groupby/generic.py
@@ -1913,7 +1913,9 @@ def _recast_datetimelike_result(result: DataFrame) -> DataFrame:
     result = result.copy()
 
     obj_cols = [
-        idx for idx in range(len(result.columns)) if is_object_dtype(result.dtypes[idx])
+        idx
+        for idx in range(len(result.columns))
+        if is_object_dtype(result.dtypes.iloc[idx])
     ]
 
     # See GH#26285
```

**Measured before:** `KeyError: 0`

**Measured after:**  `3 passed`

**The model said:** The change replaces `range(len(result.columns))` with `result.dtypes.iloc[idx]` inside the list comprehension, which resolves the KeyError: 0 observed before the fix.

`pandas-140` — grounded: ____   invented: ____   direction: ____

---

## 44. `pandas-114`  (pandas)

**Commit message:** BUG: Index.get_value implementation for ExtensionArray (#29926)

**Test run:** `pytest pandas/tests/extension/decimal/test_decimal.py::test_indexing_no_materialize`

```diff
diff --git a/pandas/core/indexes/base.py b/pandas/core/indexes/base.py
index b99e60f8c..87c110f95 100644
--- a/pandas/core/indexes/base.py
+++ b/pandas/core/indexes/base.py
@@ -69,6 +69,7 @@ import pandas.core.algorithms as algos
 from pandas.core.arrays import ExtensionArray
 from pandas.core.base import IndexOpsMixin, PandasObject
 import pandas.core.common as com
+from pandas.core.construction import extract_array
 from pandas.core.indexers import maybe_convert_indices
 from pandas.core.indexes.frozen import FrozenList
 import pandas.core.missing as missing
@@ -4489,22 +4490,26 @@ class Index(IndexOpsMixin, PandasObject):
         # if we have something that is Index-like, then
         # use this, e.g. DatetimeIndex
         # Things like `Series._get_value` (via .at) pass the EA directly here.
-        s = getattr(series, "_values", series)
-        if isinstance(s, (ExtensionArray, Index)) and is_scalar(key):
-            # GH 20882, 21257
-            # Unify Index and ExtensionArray treatment
-            # First try to convert the key to a location
-            # If that fails, raise a KeyError if an integer
-            # index, otherwise, see if key is an integer, and
-            # try that
-            try:
-                iloc = self.get_loc(key)
-                return s[iloc]
-            except KeyError:
-                if len(self) > 0 and (self.holds_integer() or self.is_boolean()):
-                    raise
-                elif is_integer(key):
-                    return s[key]
+        s = extract_array(series, extract_numpy=True)
+        if isinstance(s, ExtensionArray):
+            if is_scalar(key):
+                # GH 20882, 21257
+                # First try to convert the key to a location
+                # If that fails, raise a KeyError if an integer
+                # index, otherwise, see if key is an integer, and
+                # try that
+                try:
+                    iloc = self.get_loc(key)
+                    return s[iloc]
+                except KeyError:
+                    if len(self) > 0 and (self.holds_integer() or self.is_boolean()):
+                        raise
+                    elif is_integer(key):
+                        return s[key]
+            else:
+                # if key is not a scalar, directly raise an error (the code below
+                # would convert to numpy arrays and raise later any way) - GH29926
+                raise InvalidIndexError(key)
 
         s = 
... (truncated)
```

**Measured before:** `Exception: tried to convert a DecimalArray to a numpy array`

**Measured after:**  `1 passed`

**The model said:** The change replaces `getattr(series, "_values", series)` with `extract_array(series, extract_numpy=True)`, which resolves the `Exception: tried to convert a DecimalArray to a numpy array` by ensuring that the index lookup is performed on the correct type without attempting to convert the array to a numpy array.

`pandas-114` — grounded: ____   invented: ____   direction: ____

---

## 45. `httpie-5`  (httpie)

**Commit message:** Fixed escaping for long separators.

**Test run:** `pytest tests/tests.py::TestItemParsing::test_escape_longsep`

```diff
diff --git a/httpie/cli.py b/httpie/cli.py
index 22797a5..29a55f6 100644
--- a/httpie/cli.py
+++ b/httpie/cli.py
@@ -36,14 +36,24 @@ class KeyValueType(object):
     """A type used with `argparse`."""
     def __init__(self, *separators):
         self.separators = separators
+        self.escapes = ['\\\\' + sep for sep in separators]
 
     def __call__(self, string):
         found = {}
+        found_escapes = []
+        for esc in self.escapes:
+            found_escapes += [m.span() for m in re.finditer(esc, string)]
         for sep in self.separators:
-            regex = '[^\\\\]' + sep
-            match = re.search(regex, string)
-            if match:
-                found[match.start() + 1] = sep
+            matches = re.finditer(sep, string)
+            for match in matches:
+                start, end = match.span()
+                inside_escape = False
+                for estart, eend in found_escapes:
+                    if start >= estart and end <= eend:
+                        inside_escape = True
+                        break
+                if not inside_escape:
+                    found[start] = sep
 
         if not found:
             #noinspection PyExceptionInherit
```

**Measured before:** `AssertionError: {'bob:': '=foo'} != {'bob:=': 'foo'}`

**Measured after:**  `1 passed`

**The model said:** The commit adds escape sequences for long separators, which resolves the failure `AssertionError: {'bob:': '=foo'} != {'bob:=': 'foo'}` by ensuring that the separator is correctly interpreted as a literal rather than a special character.

`httpie-5` — grounded: ____   invented: ____   direction: ____

---

## 46. `youtube-dl-15`  (youtube-dl)

**Commit message:** [util] Improve scientific notation handling in js_to_json (closes #14789)

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_js_to_json_edgecases test.test_utils.TestUtil.test_js_to_json_realworld`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index 386897a85..2fe9cf585 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -2267,7 +2267,7 @@ def js_to_json(code):
         "(?:[^"\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^"\\]*"|
         '(?:[^'\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^'\\]*'|
         {comment}|,(?={skip}[\]}}])|
-        [a-zA-Z_][.a-zA-Z_0-9]*|
+        (?:(?<![0-9])[eE]|[a-df-zA-DF-Z_])[.a-zA-Z_0-9]*|
         \b(?:0[xX][0-9a-fA-F]+|0+[0-7]+)(?:{skip}:)?|
         [0-9]+(?={skip}:)
         '''.format(comment=COMMENT_RE, skip=SKIP_RE), fix_kv, code)
```

**Measured before:** `AssertionError: '{"se[14 chars]fset":-3.885780586188048"e"-16,"duration":39.75000000000001}]}' != '{"se[14 chars]fset":-3.885780586188048e-16,"duration":39.75000000000001}]}'`

**Measured after:**  `OK`

**The model said:** The change replaces the literal `e` with a non-word character boundary in the regex pattern for matching floating-point numbers, which resolves the failure `AssertionError: "{'se[14 chars]fset":-3.885780586188048"e"-16,"duration":39.75000000000001}]}' != "{'se[14 chars]fset":-3.885780586188048e-16

`youtube-dl-15` — grounded: ____   invented: ____   direction: ____

---

## 47. `matplotlib-28`  (matplotlib)

**Commit message:** Fix bug that caused a crash when setting negative limits and using log scale

**Test run:** `pytest lib/matplotlib/tests/test_axes.py::test_log_scales_invalid`

```diff
diff --git a/lib/matplotlib/axes/_base.py b/lib/matplotlib/axes/_base.py
index 28c4c9caa..6c3d95fe1 100644
--- a/lib/matplotlib/axes/_base.py
+++ b/lib/matplotlib/axes/_base.py
@@ -3249,7 +3249,10 @@ class _AxesBase(martist.Artist):
             if right is None:
                 right = old_right
 
-        if self.get_xscale() == 'log':
+        if self.get_xscale() == 'log' and (left <= 0 or right <= 0):
+            # Axes init calls set_xlim(0, 1) before get_xlim() can be called,
+            # so only grab the limits if we really need them.
+            old_left, old_right = self.get_xlim()
             if left <= 0:
                 cbook._warn_external(
                     'Attempted to set non-positive left xlim on a '
```

**Measured before:** `UnboundLocalError: local variable 'old_left' referenced before assignment`

**Measured after:**  `1 passed`

**The model said:** The change ensures that `old_left` and `old_right` are only assigned if the axes have a log scale and the limits are non-negative, preventing the `UnboundLocalError: local variable 'old_left' referenced before assignment` failure.

`matplotlib-28` — grounded: ____   invented: ____   direction: ____

---

## 48. `matplotlib-11`  (matplotlib)

**Commit message:** Fix Text('').get_window_extent(dpi=...).

**Test run:** `pytest lib/matplotlib/tests/test_text.py::test_non_default_dpi`

```diff
diff --git a/lib/matplotlib/text.py b/lib/matplotlib/text.py
index 429d31fb9..77ab7145a 100644
--- a/lib/matplotlib/text.py
+++ b/lib/matplotlib/text.py
@@ -891,12 +891,12 @@ class Text(Artist):
         #return _unit_box
         if not self.get_visible():
             return Bbox.unit()
-        if dpi is not None:
-            dpi_orig = self.figure.dpi
-            self.figure.dpi = dpi
+        if dpi is None:
+            dpi = self.figure.dpi
         if self.get_text() == '':
-            tx, ty = self._get_xy_display()
-            return Bbox.from_bounds(tx, ty, 0, 0)
+            with cbook._setattr_cm(self.figure, dpi=dpi):
+                tx, ty = self._get_xy_display()
+                return Bbox.from_bounds(tx, ty, 0, 0)
 
         if renderer is not None:
             self._renderer = renderer
@@ -905,13 +905,12 @@ class Text(Artist):
         if self._renderer is None:
             raise RuntimeError('Cannot get window extent w/o renderer')
 
-        bbox, info, descent = self._get_layout(self._renderer)
-        x, y = self.get_unitless_position()
-        x, y = self.get_transform().transform((x, y))
-        bbox = bbox.translated(x, y)
-        if dpi is not None:
-            self.figure.dpi = dpi_orig
-        return bbox
+        with cbook._setattr_cm(self.figure, dpi=dpi):
+            bbox, info, descent = self._get_layout(self._renderer)
+            x, y = self.get_unitless_position()
+            x, y = self.get_transform().transform((x, y))
+            bbox = bbox.translated(x, y)
+            return bbox
 
     def set_backgroundcolor(self, color):
         """
```

**Measured before:** `assert 800.0 == 80.0`

**Measured after:**  `2 passed`

**The model said:** The change removes the explicit `dpi` argument from the `Text` class's `get_window_extent` method, which previously caused the test to fail with the assertion `assert 800.0 == 80.0`.

`matplotlib-11` — grounded: ____   invented: ____   direction: ____

---

## 49. `fastapi-16`  (fastapi)

**Commit message:** :bug: Fix jsonable_encoder for models with Config (#29)

**Test run:** `pytest tests/test_jsonable_encoder.py::test_encode_model_with_config`

```diff
diff --git a/fastapi/encoders.py b/fastapi/encoders.py
index 82e3ffa..f5059a7 100644
--- a/fastapi/encoders.py
+++ b/fastapi/encoders.py
@@ -15,17 +15,12 @@ def jsonable_encoder(
     custom_encoder: dict = {},
 ) -> Any:
     if isinstance(obj, BaseModel):
-        if not obj.Config.json_encoders:
-            return jsonable_encoder(
-                obj.dict(include=include, exclude=exclude, by_alias=by_alias),
-                include_none=include_none,
-            )
-        else:
-            return jsonable_encoder(
-                obj.dict(include=include, exclude=exclude, by_alias=by_alias),
-                include_none=include_none,
-                custom_encoder=obj.Config.json_encoders,
-            )
+        encoder = getattr(obj.Config, "json_encoders", custom_encoder)
+        return jsonable_encoder(
+            obj.dict(include=include, exclude=exclude, by_alias=by_alias),
+            include_none=include_none,
+            custom_encoder=encoder,
+        )
     if isinstance(obj, Enum):
         return obj.value
     if isinstance(obj, (str, int, float, type(None))):
```

**Measured before:** `AttributeError: type object 'Config' has no attribute 'json_encoders'`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The commit replaces the conditional check for `obj.Config.json_encoders` with a direct call to `getattr`, which resolves the `AttributeError: type object 'Config' has no attribute 'json_encoders'` by ensuring the attribute is accessed safely.

`fastapi-16` — grounded: ____   invented: ____   direction: ____

---

## 50. `youtube-dl-7`  (youtube-dl)

**Commit message:** [utils:js_to_json] Fix bad escape in double quoted strings

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_js_to_json_realworld`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index db5b3698e..a61e47646 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -1701,8 +1701,8 @@ def js_to_json(code):
         if v in ('true', 'false', 'null'):
             return v
         if v.startswith('"'):
-            return v
-        if v.startswith("'"):
+            v = re.sub(r"\\'", "'", v[1:-1])
+        elif v.startswith("'"):
             v = v[1:-1]
             v = re.sub(r"\\\\|\\'|\"", lambda m: {
                 '\\\\': '\\\\',
```

**Measured before:** `AssertionError: '"The CW\\\'s \\\'Crazy Ex-Girlfriend\\\'"' != '"The CW\'s \'Crazy Ex-Girlfriend\'"'`

**Measured after:**  `OK`

**The model said:** The commit replaces `v.startswith("'"` with `v.startswith("'"` to fix the failing assertion `AssertionError: "The CW\'s \'Crazy Ex-Girlfriend\'"` -> `"The CW's 'Crazy Ex-Girlfriend'"`.

`youtube-dl-7` — grounded: ____   invented: ____   direction: ____

---
