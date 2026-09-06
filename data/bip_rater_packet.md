# BugsInPy rater packet

50 cases drawn from the `exec` arm with seed 7.

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

Record answers in `bip_rater.csv` as `id,grounded,invented,direction`, then:

    python bench/bugsinpy_rater.py --score /home/arp/Documents/oracle/data/bip_rater.csv

The rubric's own verdict is not in this file.

---

## 1. `luigi-22`  (luigi)

**Commit message:** A Fix the TypeError whenever prune is called before update has been invoked in worker.

**Test run:** `pytest test/scheduler_test.py::SchedulerTest::test_worker_prune_after_init`

```diff
diff --git a/luigi/scheduler.py b/luigi/scheduler.py
index 37ab3d91..fe5a4fe0 100644
--- a/luigi/scheduler.py
+++ b/luigi/scheduler.py
@@ -224,7 +224,7 @@ class Worker(object):
     Structure for tracking worker activity and keeping their references.
     """
 
-    def __init__(self, worker_id, last_active=None):
+    def __init__(self, worker_id, last_active=time.time()):
         self.id = worker_id
         self.reference = None  # reference to the worker in the real world. (Currently a dict containing just the host)
         self.last_active = last_active  # seconds since epoch
```

**Measured before:** `TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'`

**Measured after:**  `1 passed`

**The model said:** The default value for `last_active` was changed from `None` to `time.time()`, which removes the TypeError when the scheduler attempts to add the worker to the active workers list.

`luigi-22` — grounded: ____   invented: ____   direction: ____

---

## 2. `thefuck-15`  (thefuck)

**Commit message:** #N/A: Fix `git_add` rule

**Test run:** `pytest tests/rules/test_git_add.py::test_match`

```diff
diff --git a/thefuck/rules/git_add.py b/thefuck/rules/git_add.py
index 0cf1b05..a779a20 100644
--- a/thefuck/rules/git_add.py
+++ b/thefuck/rules/git_add.py
@@ -5,15 +5,14 @@ from thefuck.specific.git import git_support
 
 @git_support
 def match(command):
-    return ('did not match any file(s) known to git.' in command.stderr
-            and "Did you forget to 'git add'?" in command.stderr)
+    return 'did not match any file(s) known to git.' in command.stderr
 
 
 @git_support
 def get_new_command(command):
     missing_file = re.findall(
-            r"error: pathspec '([^']*)' "
-            r"did not match any file\(s\) known to git.", command.stderr)[0]
+        r"error: pathspec '([^']*)' "
+        r'did not match any file\(s\) known to git.', command.stderr)[0]
 
     formatme = shell.and_('git add -- {}', '{}')
     return formatme.format(missing_file, command.script)
```

**Measured before:** `assert False`

**Measured after:**  `2 passed`

**The model said:** The regex pattern used to extract the missing file name from the error message was updated to remove the trailing period, which caused the test to fail before but pass after the change.

`thefuck-15` — grounded: ____   invented: ____   direction: ____

---

## 3. `matplotlib-19`  (matplotlib)

**Commit message:** Don't default to negative radii in polar plot.

**Test run:** `pytest lib/matplotlib/tests/test_axes.py::test_polar_no_data`

```diff
diff --git a/lib/matplotlib/projections/polar.py b/lib/matplotlib/projections/polar.py
index 2aa1bd35e..9da973c97 100644
--- a/lib/matplotlib/projections/polar.py
+++ b/lib/matplotlib/projections/polar.py
@@ -385,6 +385,7 @@ class RadialLocator(mticker.Locator):
     :class:`~matplotlib.ticker.Locator` (which may be different
     depending on the scale of the *r*-axis.
     """
+
     def __init__(self, base, axes=None):
         self.base = base
         self._axes = axes
@@ -416,6 +417,11 @@ class RadialLocator(mticker.Locator):
         # docstring inherited
         return self.base.refresh()
 
+    def nonsingular(self, vmin, vmax):
+        # docstring inherited
+        return ((0, 1) if (vmin, vmax) == (-np.inf, np.inf)  # Init. limits.
+                else self.base.nonsingular(vmin, vmax))
+
     def view_limits(self, vmin, vmax):
         vmin, vmax = self.base.view_limits(vmin, vmax)
         if vmax > vmin:
```

**Measured before:** `assert (-0.06 == 0)`

**Measured after:**  `1 passed`

**The model said:** The `nonsingular` method was added to the `RadialLocator` class, which returns `(0, 1)` for initial limits instead of `(None, None)`. This change ensures that the test `assert (-0.06 == 0)` passes, as the output is now `1 passed` instead of `0 failed`.

`matplotlib-19` — grounded: ____   invented: ____   direction: ____

---

## 4. `black-6`  (black)

**Commit message:** Add support for always tokenizing async/await as keywords

**Test run:** `python -m unittest -q tests.test_black.BlackTestCase.test_async_as_identifier`

```diff
diff --git a/black.py b/black.py
index c96d205..c8aa30b 100644
--- a/black.py
+++ b/black.py
@@ -48,6 +48,7 @@ from blib2to3 import pygram, pytree
 from blib2to3.pgen2 import driver, token
 from blib2to3.pgen2.grammar import Grammar
 from blib2to3.pgen2.parse import ParseError
+from blib2to3.pgen2.tokenize import TokenizerConfig
 
 
 __version__ = "19.3b0"
@@ -136,19 +137,28 @@ class Feature(Enum):
     NUMERIC_UNDERSCORES = 3
     TRAILING_COMMA_IN_CALL = 4
     TRAILING_COMMA_IN_DEF = 5
+    # The following two feature-flags are mutually exclusive, and exactly one should be
+    # set for every version of python.
+    ASYNC_IS_VALID_IDENTIFIER = 6
+    ASYNC_IS_RESERVED_KEYWORD = 7
 
 
 VERSION_TO_FEATURES: Dict[TargetVersion, Set[Feature]] = {
-    TargetVersion.PY27: set(),
-    TargetVersion.PY33: {Feature.UNICODE_LITERALS},
-    TargetVersion.PY34: {Feature.UNICODE_LITERALS},
-    TargetVersion.PY35: {Feature.UNICODE_LITERALS, Feature.TRAILING_COMMA_IN_CALL},
+    TargetVersion.PY27: {Feature.ASYNC_IS_VALID_IDENTIFIER},
+    TargetVersion.PY33: {Feature.UNICODE_LITERALS, Feature.ASYNC_IS_VALID_IDENTIFIER},
+    TargetVersion.PY34: {Feature.UNICODE_LITERALS, Feature.ASYNC_IS_VALID_IDENTIFIER},
+    TargetVersion.PY35: {
+        Feature.UNICODE_LITERALS,
+        Feature.TRAILING_COMMA_IN_CALL,
+        Feature.ASYNC_IS_VALID_IDENTIFIER,
+    },
     TargetVersion.PY36: {
         Feature.UNICODE_LITERALS,
         Feature.F_STRINGS,
         Feature.NUMERIC_UNDERSCORES,
         Feature.TRAILING_COMMA_IN_CALL,
         Feature.TRAILING_COMMA_IN_DEF,
+        Feature.ASYNC_IS_VALID_IDENTIFIER,
     },
     TargetVersion.PY37: {
         Feature.UNICODE_LITERALS,
@@ -156,6 +166,7 @@ VERSION_TO_FEATURES: Dict[TargetVersion, Set[Feature]] = {
         Feature.NUMERIC_UNDERSCORES,
         Feature.TRAILING_COMMA_IN_CALL,
         Feature.TRAILING_COMMA_IN_DEF,
+        Feature.ASYNC_IS_RESERVED_KEYWORD,
     },
     TargetVersion.PY38: {
         Feature.UNICODE_LITERALS,
@@ -163,6 +174,7 @@ VERSION_TO_FEATURES: Dict[TargetVersion, Set[Feature]] = {
         Feature.NUMERIC_UNDERSCORES,
         Feature.TRAILING_COMMA_IN_CALL,
         Feature.TRAILING_COMMA_IN_DEF,
+        Feature.ASYNC_IS_RESERVED_KEYWORD,
     },
 }
 
@@ -748,20 +760,62 @@ def decode_bytes(src: bytes) -> Tuple[FileContent, Encoding, NewLine]:
         return tiow.read(), encoding, newline
 
 
-def get_grammars(target_versions: Set[TargetVersion]) -> List[Grammar]:
+@dataclass(frozen=T
... (truncated)
```

**Measured before:** `AssertionError: 0 != 123 : All done! ✨ 🍰 ✨`

**Measured after:**  `OK`

**The model said:** The change adds a new `ASYNC_IS_VALID_IDENTIFIER` feature flag to the `VERSION_TO_FEATURES` dictionary, which allows the parser to treat `async` as a valid identifier instead of a reserved keyword. This change resolves the assertion error by allowing the program to execute without crashing, as the test now passes.

`black-6` — grounded: ____   invented: ____   direction: ____

---

## 5. `luigi-5`  (luigi)

**Commit message:** Fix MRO on tasks using util.requires (#2307)

**Test run:** `pytest test/util_test.py::BasicsTest::test_inherits_has_effect_MRO`

```diff
diff --git a/luigi/util.py b/luigi/util.py
index 97feb8f5..f6be2002 100644
--- a/luigi/util.py
+++ b/luigi/util.py
@@ -274,18 +274,19 @@ class inherits(object):
         self.task_to_inherit = task_to_inherit
 
     def __call__(self, task_that_inherits):
+        # Get all parameter objects from the underlying task
         for param_name, param_obj in self.task_to_inherit.get_params():
+            # Check if the parameter exists in the inheriting task
             if not hasattr(task_that_inherits, param_name):
+                # If not, add it to the inheriting task
                 setattr(task_that_inherits, param_name, param_obj)
 
-        # Modify task_that_inherits by subclassing it and adding methods
-        @task._task_wraps(task_that_inherits)
-        class Wrapped(task_that_inherits):
+        # Modify task_that_inherits by adding methods
+        def clone_parent(_self, **args):
+            return _self.clone(cls=self.task_to_inherit, **args)
+        task_that_inherits.clone_parent = clone_parent
 
-            def clone_parent(_self, **args):
-                return _self.clone(cls=self.task_to_inherit, **args)
-
-        return Wrapped
+        return task_that_inherits
 
 
 class requires(object):
@@ -300,14 +301,12 @@ class requires(object):
     def __call__(self, task_that_requires):
         task_that_requires = self.inherit_decorator(task_that_requires)
 
-        # Modify task_that_requres by subclassing it and adding methods
-        @task._task_wraps(task_that_requires)
-        class Wrapped(task_that_requires):
+        # Modify task_that_requres by adding methods
+        def requires(_self):
+            return _self.clone_parent()
+        task_that_requires.requires = requires
 
-            def requires(_self):
-                return _self.clone_parent()
-
-        return Wrapped
+        return task_that_requires
 
 
 class copies(object):
```

**Measured before:** `AssertionError: "<class 'util_test.BasicsTest._setup_inherits_inheritence.<locals>.ChildTask'>" == "<class 'util_test.BasicsTest._setup_inherits_inheritence.<locals>.ChildTask'>"`

**Measured after:**  `1 passed, 31 warnings`

**The model said:** The commit adds a `clone_parent` method to the `inherits` decorator, which is used to create a new instance of the underlying task. This change allows the `requires` decorator to use the `clone_parent` method instead of directly cloning the task, which removes the assertion error and increases the number of passing tests from 1 to 31.

`luigi-5` — grounded: ____   invented: ____   direction: ____

---

## 6. `black-4`  (black)

**Commit message:** Fix unstable format involving backslash + whitespace at beginning of file (#948)

**Test run:** `python -m unittest -q tests.test_black.BlackTestCase.test_beginning_backslash`

```diff
diff --git a/black.py b/black.py
index f7022d8..05edf1a 100644
--- a/black.py
+++ b/black.py
@@ -1480,7 +1480,13 @@ class EmptyLineTracker:
         lines (two on module-level).
         """
         before, after = self._maybe_empty_lines(current_line)
-        before -= self.previous_after
+        before = (
+            # Black should not insert empty lines at the beginning
+            # of the file
+            0
+            if self.previous_line is None
+            else before - self.previous_after
+        )
         self.previous_after = after
         self.previous_line = current_line
         return before, after
```

**Measured before:** `AssertionError: 'print("hello, world")\n' != '\n\nprint("hello, world")\n'`

**Measured after:**  `OK`

**The model said:** The change removes the `if self.previous_line is None` guard, which causes the `before` counter to always start at zero instead of skipping the previous `after` value. This eliminates the assertion error in the project's own tests, which now passes without modification.

`black-4` — grounded: ____   invented: ____   direction: ____

---

## 7. `luigi-29`  (luigi)

**Commit message:** Fix #877 by breaking some backwards compatibility

**Test run:** `pytest test/task_test.py::TaskTest::test_external_tasks_loadable`

```diff
diff --git a/luigi/task_register.py b/luigi/task_register.py
index 85843024..15d18f70 100644
--- a/luigi/task_register.py
+++ b/luigi/task_register.py
@@ -135,8 +135,6 @@ class Register(abc.ABCMeta):
         # We return this in a topologically sorted list of inheritance: this is useful in some cases (#822)
         reg = OrderedDict()
         for cls in cls._reg:
-            if cls.run == NotImplemented:
-                continue
             name = cls.task_family
 
             if name in reg and reg[name] != cls and \
diff --git a/test/cmdline_test.py b/test/cmdline_test.py
index 64e56f52..229f365c 100644
--- a/test/cmdline_test.py
+++ b/test/cmdline_test.py
@@ -53,16 +53,6 @@ class AmbiguousClass(luigi.Task):
     pass
 
 
-class NonAmbiguousClass(luigi.ExternalTask):
-    pass
-
-
-class NonAmbiguousClass(luigi.Task):
-
-    def run(self):
-        NonAmbiguousClass.has_run = True
-
-
 class TaskWithSameName(luigi.Task):
 
     def run(self):
@@ -115,12 +105,6 @@ class CmdlineTest(unittest.TestCase):
     def test_cmdline_ambiguous_class(self, logger):
         self.assertRaises(Exception, luigi.run, ['--local-scheduler', '--no-lock', 'AmbiguousClass'])
 
-    @mock.patch("logging.getLogger")
-    @mock.patch("warnings.warn")
-    def test_cmdline_non_ambiguous_class(self, warn, logger):
-        luigi.run(['--local-scheduler', '--no-lock', 'NonAmbiguousClass'])
-        self.assertTrue(NonAmbiguousClass.has_run)
-
     @mock.patch("logging.getLogger")
     @mock.patch("logging.StreamHandler")
     def test_setup_interface_logging(self, handler, logger):
```

**Measured before:** `luigi.task_register.TaskClassException: Task 'ExternalTask' not found. Candidates are: Config,DummyTask,RangeBase,RangeDaily,RangeDailyBase,RangeHourly,RangeHourlyBase,Task,WrapperTask,core,scheduler,worker`

**Measured after:**  `1 passed`

**The model said:** Removing the `if cls.run == NotImplemented` check from `Register` causes the project's own tests to fail, as the `NonAmbiguousClass` task no longer has a `run` method defined, causing the `NonAmbiguousClass.has_run` attribute to be `False` instead of `True`.

`luigi-29` — grounded: ____   invented: ____   direction: ____

---

## 8. `youtube-dl-23`  (youtube-dl)

**Commit message:** [utils] Handle single-line comments in js_to_json

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_js_to_json_edgecases`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index cf46711b9..6c462625b 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -2107,7 +2107,7 @@ def js_to_json(code):
         v = m.group(0)
         if v in ('true', 'false', 'null'):
             return v
-        elif v.startswith('/*') or v == ',':
+        elif v.startswith('/*') or v.startswith('//') or v == ',':
             return ""
 
         if v[0] in ("'", '"'):
@@ -2134,7 +2134,7 @@ def js_to_json(code):
     return re.sub(r'''(?sx)
         "(?:[^"\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^"\\]*"|
         '(?:[^'\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^'\\]*'|
-        /\*.*?\*/|,(?=\s*[\]}])|
+        /\*.*?\*/|//[^\n]*|,(?=\s*[\]}])|
         [a-zA-Z_][.a-zA-Z_0-9]*|
         \b(?:0[xX][0-9a-fA-F]+|0+[0-7]+)(?:\s*:)?|
         [0-9]+(?=\s*:)
```

**Measured before:** `JSONDecodeError: Expecting value: line 1 column 8 (char 7)`

**Measured after:**  `OK`

**The model said:** The regex pattern now includes `//` for single-line comments, which removes the error when parsing the input string `"//"`.

`youtube-dl-23` — grounded: ____   invented: ____   direction: ____

---

## 9. `luigi-18`  (luigi)

**Commit message:** Overrides scheduler disable with manual disable by worker

**Test run:** `pytest test/central_planner_test.py::CentralPlannerTest::test_no_automatic_re_enable_after_auto_then_manual_disable`

```diff
diff --git a/luigi/scheduler.py b/luigi/scheduler.py
index 7c4d4718..edcaa5d5 100644
--- a/luigi/scheduler.py
+++ b/luigi/scheduler.py
@@ -402,7 +402,7 @@ class SimpleTaskState(object):
                 self.re_enable(task)
 
             # don't allow workers to override a scheduler disable
-            elif task.scheduler_disable_time is not None:
+            elif task.scheduler_disable_time is not None and new_status != DISABLED:
                 return
 
         if new_status == FAILED and task.can_disable() and task.status != DISABLED:
```

**Measured before:** `AssertionError: 'DISABLED' != 'FAILED'`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The change removes the `or task.scheduler_disable_time is not None` condition from the `SimpleTaskState` class, which allows workers to override a scheduler disable when the task's status is not `DISABLED`. This modification causes the test to pass, as the assertion error is no longer raised.

`luigi-18` — grounded: ____   invented: ____   direction: ____

---

## 10. `PySnooper-1`  (PySnooper)

**Commit message:** Fix unicode issues and add test, fix #124

**Test run:** `pytest -q -s tests/test_chinese.py::test_chinese`

```diff
diff --git a/pysnooper/pycompat.py b/pysnooper/pycompat.py
index 63dd3db..de0a472 100644
--- a/pysnooper/pycompat.py
+++ b/pysnooper/pycompat.py
@@ -8,6 +8,7 @@ import inspect
 import sys
 
 PY3 = (sys.version_info[0] == 3)
+PY2 = not PY3
 
 if hasattr(abc, 'ABC'):
     ABC = abc.ABC
diff --git a/pysnooper/tracer.py b/pysnooper/tracer.py
index 089b817..480d60a 100644
--- a/pysnooper/tracer.py
+++ b/pysnooper/tracer.py
@@ -14,6 +14,8 @@ import traceback
 
 from .variables import CommonVariable, Exploding, BaseVariable
 from . import utils, pycompat
+if pycompat.PY2:
+    from io import open
 
 
 ipython_filename_pattern = re.compile('^<ipython-input-([0-9]+)-.*>$')
@@ -84,7 +86,7 @@ def get_source_from_frame(frame):
     # apply tokenize.detect_encoding to decode the source into a
     # string, then we should do that ourselves.
     if isinstance(source[0], bytes):
-        encoding = 'ascii'
+        encoding = 'utf-8'
         for line in source[:2]:
             # File coding may be specified. Match pattern from PEP-263
             # (https://www.python.org/dev/peps/pep-0263/)
@@ -130,7 +132,8 @@ class FileWriter(object):
         self.overwrite = overwrite
 
     def write(self, s):
-        with open(self.path, 'w' if self.overwrite else 'a') as output_file:
+        with open(self.path, 'w' if self.overwrite else 'a',
+                  encoding='utf-8') as output_file:
             output_file.write(s)
         self.overwrite = False
 
diff --git a/tests/utils.py b/tests/utils.py
index b77e1f6..05185f0 100644
--- a/tests/utils.py
+++ b/tests/utils.py
@@ -254,7 +254,7 @@ def assert_output(output, expected_entries, prefix=None):
 
     any_mismatch = False
     result = ''
-    template = '\n{line!s:%s}   {expected_entry}  {arrow}' % max(map(len, lines))
+    template = u'\n{line!s:%s}   {expected_entry}  {arrow}' % max(map(len, lines))
     for expected_entry, line in zip_longest(expected_entries, lines, fillvalue=""):
         mismatch = not (expected_entry and expected_entry.check(line))
         any_mismatch |= mismatch
@@ -273,7 +273,7 @@ def assert_sample_output(module):
     with sys_tools.OutputCapturer(stdout=False,
                                   stderr=True) as output_capturer:
         module.main()
-        
+
     time = '21:10:42.298924'
     time_pattern = re.sub(r'\d', r'\\d', time)
```

**Measured before:** `1 passed, 2 warnings`

**Measured after:**  `1 passed, 2 warnings`

**The model said:** The default encoding for file I/O operations was changed from ASCII to UTF-8 in `FileWriter.write`, which is a non-breaking change that does not affect the project's own tests, which still pass with 1 passed, 2 warnings.

`PySnooper-1` — grounded: ____   invented: ____   direction: ____

---

## 11. `luigi-25`  (luigi)

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

**The model said:** The `path` variable was changed from a method call to a direct attribute access, which removed the `TypeError: 'str' object is not callable'` failure in the project's own tests.

`luigi-25` — grounded: ____   invented: ____   direction: ____

---

## 12. `youtube-dl-26`  (youtube-dl)

**Commit message:** [utils] Don't transform numbers not starting with a zero

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_js_to_json_realworld`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index c8308ba3a..82f67f6cd 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -1970,7 +1970,7 @@ def js_to_json(code):
         '(?:[^'\\]*(?:\\\\|\\['"nurtbfx/\n]))*[^'\\]*'|
         /\*.*?\*/|,(?=\s*[\]}])|
         [a-zA-Z_][.a-zA-Z_0-9]*|
-        (?:0[xX][0-9a-fA-F]+|0+[0-7]+)(?:\s*:)?|
+        \b(?:0[xX][0-9a-fA-F]+|0+[0-7]+)(?:\s*:)?|
         [0-9]+(?=\s*:)
         ''', fix_kv, code)
```

**Measured before:** `AssertionError: '{"foo":11}' != '{"foo":101}'`

**Measured after:**  `OK`

**The model said:** The regex pattern in `js_to_json` was updated to remove the word boundary (`\b`) before the literal number match, which allows it to capture numbers starting with a zero. This change resolves the assertion error by allowing the test to pass again.

`youtube-dl-26` — grounded: ____   invented: ____   direction: ____

---

## 13. `black-3`  (black)

**Commit message:** Change exit code to 2 when config file doesn't exist (#1361)

**Test run:** `python -m unittest -q tests.test_black.BlackTestCase.test_invalid_config_return_code`

```diff
diff --git a/black.py b/black.py
index d9348a3..26a2915 100644
--- a/black.py
+++ b/black.py
@@ -394,7 +394,7 @@ def target_version_option_callback(
 @click.option(
     "--config",
     type=click.Path(
-        exists=False, file_okay=True, dir_okay=False, readable=True, allow_dash=False
+        exists=True, file_okay=True, dir_okay=False, readable=True, allow_dash=False
     ),
     is_eager=True,
     callback=read_pyproject_toml,
```

**Measured before:** `AssertionError: 1 != 2 : Error: Could not open file /tmp/blk_iu8vgjem.log: Error reading configuration file: [Errno 2] No such file or directory: '/tmp/blk_iu8vgjem.log'`

**Measured after:**  `OK`

**The model said:** The `exists` parameter in the `--config` option was changed from `False` to `True`, which causes the program to exit with a status code of 2 instead of 1 when the specified file does not exist. This change fixes the assertion error by changing the expected exit code from 1 to 2.

`black-3` — grounded: ____   invented: ____   direction: ____

---

## 14. `scrapy-40`  (scrapy)

**Commit message:** fix PythonItemExporter for non-string types

**Test run:** `python -m unittest -q tests.test_exporters.PythonItemExporterTest.test_other_python_types_item`

```diff
diff --git a/scrapy/exporters.py b/scrapy/exporters.py
index 145468db..c7c78d05 100644
--- a/scrapy/exporters.py
+++ b/scrapy/exporters.py
@@ -273,10 +273,10 @@ class PythonItemExporter(BaseItemExporter):
             return dict(self._serialize_dict(value))
         if is_listlike(value):
             return [self._serialize_value(v) for v in value]
-        if self.binary:
-            return to_bytes(value, encoding=self.encoding)
-        else:
-            return to_unicode(value, encoding=self.encoding)
+        encode_func = to_bytes if self.binary else to_unicode
+        if isinstance(value, (six.text_type, bytes)):
+            return encode_func(value, encoding=self.encoding)
+        return value
 
     def _serialize_dict(self, value):
         for key, val in six.iteritems(value):
```

**Measured before:** `TypeError: to_unicode must receive a bytes, str or unicode object, got bool`

**Measured after:**  `OK`

**The model said:** The change removes the explicit `to_bytes` and `to_unicode` checks within `_serialize_value`, replacing them with a single `isinstance` check that handles both text and binary types. This eliminates the `TypeError: to_unicode must receive a bytes, str or unicode object, got bool` when exporting items with boolean values, which was previously causing the test to fail.

`scrapy-40` — grounded: ____   invented: ____   direction: ____

---

## 15. `youtube-dl-11`  (youtube-dl)

**Commit message:** [utils] handle int values passed to str_to_int

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_str_to_int`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index b14603d8a..328f037a8 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -3519,8 +3519,8 @@ def str_or_none(v, default=None):
 
 def str_to_int(int_str):
     """ A more relaxed version of int_or_none """
-    if int_str is None:
-        return None
+    if not isinstance(int_str, compat_str):
+        return int_str
     int_str = re.sub(r'[,\.\+]', '', int_str)
     return int(int_str)
```

**Measured before:** `TypeError: expected string or bytes-like object`

**Measured after:**  `OK`

**The model said:** The change removes the explicit `None` check in `str_to_int`, which allows the function to pass through non-string inputs without raising a `TypeError`. This modification resolves the observed `TypeError: expected string or bytes-like object` when passing non-string values to `str_to_int`.

`youtube-dl-11` — grounded: ____   invented: ____   direction: ____

---

## 16. `pandas-11`  (pandas)

**Commit message:** BUG: can't concatenate DataFrame with Series with duplicate keys (#33805)

**Test run:** `pytest pandas/tests/reshape/test_concat.py::test_duplicate_keys`

```diff
diff --git a/pandas/core/reshape/concat.py b/pandas/core/reshape/concat.py
index a868e663b..2f66cbf44 100644
--- a/pandas/core/reshape/concat.py
+++ b/pandas/core/reshape/concat.py
@@ -619,10 +619,10 @@ def _make_concat_multiindex(indexes, keys, levels=None, names=None) -> MultiInde
         for hlevel, level in zip(zipped, levels):
             to_concat = []
             for key, index in zip(hlevel, indexes):
-                try:
-                    i = level.get_loc(key)
-                except KeyError as err:
-                    raise ValueError(f"Key {key} not in level {level}") from err
+                mask = level == key
+                if not mask.any():
+                    raise ValueError(f"Key {key} not in level {level}")
+                i = np.nonzero(level == key)[0][0]
 
                 to_concat.append(np.repeat(i, len(index)))
             codes_list.append(np.concatenate(to_concat))
```

**Measured before:** `TypeError: int() argument must be a string, a bytes-like object or a number, not 'slice'`

**Measured after:**  `2 passed`

**The model said:** The change replaces `try/except` block with `np.nonzero` to find the index of the matching key, which removes the `TypeError: int() argument must be a string, a bytes-like object or a number, not 'slice'` error and allows the test suite to pass again.

`pandas-11` — grounded: ____   invented: ____   direction: ____

---

## 17. `luigi-9`  (luigi)

**Commit message:** retcodes: Understand succesful retries (#1951)

**Test run:** `pytest test/execution_summary_test.py::ExecutionSummaryTest::test_status_with_task_retry`

```diff
diff --git a/luigi/execution_summary.py b/luigi/execution_summary.py
index 27efbcb6..256f341b 100644
--- a/luigi/execution_summary.py
+++ b/luigi/execution_summary.py
@@ -43,12 +43,13 @@ def _partition_tasks(worker):
     set_tasks["completed"] = {task for (task, status, ext) in task_history if status == 'DONE' and task in pending_tasks}
     set_tasks["already_done"] = {task for (task, status, ext) in task_history
                                  if status == 'DONE' and task not in pending_tasks and task not in set_tasks["completed"]}
-    set_tasks["failed"] = {task for (task, status, ext) in task_history if status == 'FAILED'}
+    set_tasks["ever_failed"] = {task for (task, status, ext) in task_history if status == 'FAILED'}
+    set_tasks["failed"] = set_tasks["ever_failed"] - set_tasks["completed"]
     set_tasks["scheduling_error"] = {task for(task, status, ext) in task_history if status == 'UNKNOWN'}
     set_tasks["still_pending_ext"] = {task for (task, status, ext) in task_history
-                                      if status == 'PENDING' and task not in set_tasks["failed"] and task not in set_tasks["completed"] and not ext}
+                                      if status == 'PENDING' and task not in set_tasks["ever_failed"] and task not in set_tasks["completed"] and not ext}
     set_tasks["still_pending_not_ext"] = {task for (task, status, ext) in task_history
-                                          if status == 'PENDING' and task not in set_tasks["failed"] and task not in set_tasks["completed"] and ext}
+                                          if status == 'PENDING' and task not in set_tasks["ever_failed"] and task not in set_tasks["completed"] and ext}
     set_tasks["run_by_other_worker"] = set()
     set_tasks["upstream_failure"] = set()
     set_tasks["upstream_missing_dependency"] = set()
@@ -87,7 +88,7 @@ def _depth_first_search(set_tasks, current_task, visited):
         for task in current_task._requires():
             if task not in visited:
                 _depth_first_search(set_tasks, task, visited)
-            if task in set_tasks["failed"] or task in set_tasks["upstream_failure"]:
+            if task in set_tasks["ever_failed"] or task in set_tasks["upstream_failure"]:
                 set_tasks["upstream_failure"].add(current_task)
                 upstream_failure = True
             if task in set_tasks["still_pending_ext"] or task in set_tasks["upstream_missing_dependency"]:
@@ -261,6 +262,7 @@ def _get_comments
... (truncated)
```

**Measured before:** `KeyError: 'ever_failed'`

**Measured after:**  `1 passed, 23 warnings`

**The model said:** The `set_tasks` dictionary now includes an `ever_failed` key instead of `failed`, which removes the KeyError when accessing the `ever_failed` set. This change ensures that the project's own tests no longer fail with a KeyError, and the project's own tests now pass with 1 passed and 23 warnings.

`luigi-9` — grounded: ____   invented: ____   direction: ____

---

## 18. `cookiecutter-2`  (cookiecutter)

**Commit message:** Changed: Generated projects can use multiple type hooks at same time. (sh + py) (#974)

**Test run:** `tox tests/test_hooks.py::TestFindHooks::test_find_hook`

```diff
diff --git a/cookiecutter/hooks.py b/cookiecutter/hooks.py
index 20ccae2..3c73f74 100644
--- a/cookiecutter/hooks.py
+++ b/cookiecutter/hooks.py
@@ -54,11 +54,14 @@ def find_hook(hook_name, hooks_dir='hooks'):
         logger.debug('No hooks/dir in template_dir')
         return None
 
+    scripts = []
     for hook_file in os.listdir(hooks_dir):
         if valid_hook(hook_file, hook_name):
-            return os.path.abspath(os.path.join(hooks_dir, hook_file))
+            scripts.append(os.path.abspath(os.path.join(hooks_dir, hook_file)))
 
-    return None
+    if len(scripts) == 0:
+        return None
+    return scripts
 
 
 def run_script(script_path, cwd='.'):
@@ -119,9 +122,10 @@ def run_hook(hook_name, project_dir, context):
     :param project_dir: The directory to execute the script from.
     :param context: Cookiecutter project context.
     """
-    script = find_hook(hook_name)
-    if script is None:
+    scripts = find_hook(hook_name)
+    if not scripts:
         logger.debug('No %s hook found', hook_name)
         return
     logger.debug('Running hook %s', hook_name)
-    run_script_with_context(script, project_dir, context)
+    for script in scripts:
+        run_script_with_context(script, project_dir, context)
```

**Measured before:** `AssertionError: assert '<repo>/tests/test-hooks/hooks/pre_gen_project.py' == '/'`

**Measured after:**  `1 passed`

**The model said:** The change removes the direct return of the first matching hook file path, instead returning a list of all matching files. This allows the project's own tests to pass when multiple type hooks are present, as they now correctly identify and execute each hook script.

`cookiecutter-2` — grounded: ____   invented: ____   direction: ____

---

## 19. `thefuck-16`  (thefuck)

**Commit message:** #301: Set variables within the alias

**Test run:** `pytest tests/shells/test_bash.py::TestBash::test_app_alias_variables_correctly_set`

```diff
diff --git a/thefuck/shells/bash.py b/thefuck/shells/bash.py
index d6e9b2c..8f4e0e1 100644
--- a/thefuck/shells/bash.py
+++ b/thefuck/shells/bash.py
@@ -6,9 +6,11 @@ from .generic import Generic
 
 class Bash(Generic):
     def app_alias(self, fuck):
-        alias = "TF_ALIAS={0}" \
-                " alias {0}='PYTHONIOENCODING=utf-8" \
-                " TF_CMD=$(TF_SHELL_ALIASES=$(alias) thefuck $(fc -ln -1)) && " \
+        # It is VERY important to have the variables declared WITHIN the alias
+        alias = "alias {0}='TF_CMD=$(TF_ALIAS={0}" \
+                " PYTHONIOENCODING=utf-8" \
+                " TF_SHELL_ALIASES=$(alias)" \
+                " thefuck $(fc -ln -1)) &&" \
                 " eval $TF_CMD".format(fuck)
 
         if settings.alter_history:
diff --git a/thefuck/shells/fish.py b/thefuck/shells/fish.py
index fff003b..bc2b2ec 100644
--- a/thefuck/shells/fish.py
+++ b/thefuck/shells/fish.py
@@ -14,6 +14,7 @@ class Fish(Generic):
             return ['cd', 'grep', 'ls', 'man', 'open']
 
     def app_alias(self, fuck):
+        # It is VERY important to have the variables declared WITHIN the alias
         return ('function {0} -d "Correct your previous console command"\n'
                 '  set -l fucked_up_command $history[1]\n'
                 '  env TF_ALIAS={0} PYTHONIOENCODING=utf-8'
diff --git a/thefuck/shells/zsh.py b/thefuck/shells/zsh.py
index a8c0587..e522d6a 100644
--- a/thefuck/shells/zsh.py
+++ b/thefuck/shells/zsh.py
@@ -7,10 +7,11 @@ from .generic import Generic
 
 class Zsh(Generic):
     def app_alias(self, alias_name):
-        alias = "alias {0}='TF_ALIAS={0}" \
+        # It is VERY important to have the variables declared WITHIN the alias
+        alias = "alias {0}='TF_CMD=$(TF_ALIAS={0}" \
                 " PYTHONIOENCODING=utf-8" \
-                ' TF_SHELL_ALIASES=$(alias)' \
-                " TF_CMD=$(thefuck $(fc -ln -1 | tail -n 1)) &&" \
+                " TF_SHELL_ALIASES=$(alias)" \
+                " thefuck $(fc -ln -1 | tail -n 1)) &&" \
                 " eval $TF_CMD".format(alias_name)
 
         if settings.alter_history:
diff --git a/thefuck/types.py b/thefuck/types.py
index dcd99b6..81a7d1b 100644
--- a/thefuck/types.py
+++ b/thefuck/types.py
@@ -282,5 +282,5 @@ class CorrectedCommand(object):
             compatibility_call(self.side_effect, old_cmd, self.script)
         # This depends on correct setting of PYTHONIOENCODING by the alias:
         logs.debug(u'PYTHONIOENCODING: {}'.fo
... (truncated)
```

**Measured before:** `assert "alias fuck='TF_CMD=$(TF_ALIAS" in "TF_ALIAS=fuck alias fuck='PYTHONIOENCODING=utf-8 TF_CMD=$(TF_SHELL_ALIASES=$(alias) thefuck $(fc -ln -1)) &&  eval $TF_CMD && history -s $TF_CMD'"`

**Measured after:**  `1 passed`

**The model said:** The commit refactors the alias construction to move the `TF_ALIAS` variable declaration inside the alias definition, which resolves an issue where the environment variable was not being correctly set when the alias was executed. The test now passes without the assertion failure, indicating that the behavior has been restored to the expected state.

`thefuck-16` — grounded: ____   invented: ____   direction: ____

---

## 20. `youtube-dl-29`  (youtube-dl)

**Commit message:** [utils] unified_strdate: Return None if the date format can't be recognized (fixes #7340)

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_unified_dates`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index 7b3f79141..d39f313a4 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -911,7 +911,8 @@ def unified_strdate(date_str, day_first=True):
         timetuple = email.utils.parsedate_tz(date_str)
         if timetuple:
             upload_date = datetime.datetime(*timetuple[:6]).strftime('%Y%m%d')
-    return compat_str(upload_date)
+    if upload_date is not None:
+        return compat_str(upload_date)
 
 
 def determine_ext(url, default_ext='unknown_video'):
```

**Measured before:** `AssertionError: 'None' != None`

**Measured after:**  `OK`

**The model said:** The `unified_strdate` function now returns `None` explicitly when the date format cannot be recognized, which resolves the assertion error in the project's own tests.

`youtube-dl-29` — grounded: ____   invented: ____   direction: ____

---

## 21. `youtube-dl-25`  (youtube-dl)

**Commit message:** [utils] Correct octal/hexadecimal number detection in js_to_json

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_js_to_json_realworld`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index 35362e767..0c36c1b80 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -2038,14 +2038,14 @@ def js_to_json(code):
             }.get(m.group(0), m.group(0)), v[1:-1])
 
         INTEGER_TABLE = (
-            (r'^0[xX][0-9a-fA-F]+', 16),
-            (r'^0+[0-7]+', 8),
+            (r'^(0[xX][0-9a-fA-F]+)\s*:?$', 16),
+            (r'^(0+[0-7]+)\s*:?$', 8),
         )
 
         for regex, base in INTEGER_TABLE:
             im = re.match(regex, v)
             if im:
-                i = int(im.group(0), base)
+                i = int(im.group(1), base)
                 return '"%d":' % i if v.endswith(':') else '%d' % i
 
         return '"%s"' % v
```

**Measured before:** `AssertionError: '{"duration": 0}' != '{"duration": "00:01:07"}'`

**Measured after:**  `OK`

**The model said:** The change updates the octal/hexadecimal detection logic to strip any trailing whitespace before parsing the literal, which resolves the test failure by allowing the integer literal `0o10` to be correctly parsed as `8` instead of `10`.

`youtube-dl-25` — grounded: ____   invented: ____   direction: ____

---

## 22. `thefuck-1`  (thefuck)

**Commit message:** #1047: Fix pip_unknown_command by using a less restrictive regex

**Test run:** `pytest tests/rules/test_pip_unknown_command.py::test_get_new_command`

```diff
diff --git a/thefuck/rules/pip_unknown_command.py b/thefuck/rules/pip_unknown_command.py
index 75fcc7c..2720cda 100644
--- a/thefuck/rules/pip_unknown_command.py
+++ b/thefuck/rules/pip_unknown_command.py
@@ -12,8 +12,8 @@ def match(command):
 
 
 def get_new_command(command):
-    broken_cmd = re.findall(r'ERROR: unknown command \"([a-z]+)\"',
+    broken_cmd = re.findall(r'ERROR: unknown command "([^"]+)"',
                             command.output)[0]
-    new_cmd = re.findall(r'maybe you meant \"([a-z]+)\"', command.output)[0]
+    new_cmd = re.findall(r'maybe you meant "([^"]+)"', command.output)[0]
 
     return replace_argument(command.script, broken_cmd, new_cmd)
```

**Measured before:** `IndexError: list index out of range`

**Measured after:**  `2 passed`

**The model said:** The regex pattern in `get_new_command` was updated to use double quotes instead of single quotes around the captured group, which resolved the `IndexError: list index out of range` failure when the output contained quoted command names.

`thefuck-1` — grounded: ____   invented: ____   direction: ____

---

## 23. `spacy-5`  (spacy)

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

**The model said:** The `docs` argument was swapped in `_pipe` calls, which resolved the TypeError: 'function' object is not iterable error.

`spacy-5` — grounded: ____   invented: ____   direction: ____

---

## 24. `httpie-3`  (httpie)

**Commit message:** Fixed --download with --session

**Test run:** `pytest tests/test_sessions.py::TestSession::test_download_in_session`

```diff
diff --git a/httpie/sessions.py b/httpie/sessions.py
index e61a8e3..32254bf 100644
--- a/httpie/sessions.py
+++ b/httpie/sessions.py
@@ -101,6 +101,10 @@ class Session(BaseConfigDict):
 
         """
         for name, value in request_headers.items():
+
+            if value is None:
+                continue  # Ignore explicitely unset headers
+
             value = value.decode('utf8')
             if name == 'User-Agent' and value.startswith('HTTPie/'):
                 continue
```

**Measured before:** `AttributeError: 'NoneType' object has no attribute 'decode'`

**Measured after:**  `1 passed, 1 warning`

**The model said:** The change removes the `if value is None` check from the loop, which previously caused an `AttributeError: 'NoneType' object has no attribute 'decode'` when a header was explicitly set to `None`. This modification allows the loop to proceed without skipping any headers, which resolves the test failure by ensuring that all headers are processed correctly.

`httpie-3` — grounded: ____   invented: ____   direction: ____

---

## 25. `youtube-dl-30`  (youtube-dl)

**Commit message:** [YoutubeDL] format spec: Do not fail when a filter gives an empty result

**Test run:** `python -m unittest -q test.test_YoutubeDL.TestFormatSelection.test_format_filtering`

```diff
diff --git a/youtube_dl/YoutubeDL.py b/youtube_dl/YoutubeDL.py
index 5a79e5f1d..6478d05dc 100755
--- a/youtube_dl/YoutubeDL.py
+++ b/youtube_dl/YoutubeDL.py
@@ -1005,6 +1005,9 @@ class YoutubeDL(object):
                 format_spec = selector.selector
 
                 def selector_function(formats):
+                    formats = list(formats)
+                    if not formats:
+                        return
                     if format_spec == 'all':
                         for f in formats:
                             yield f
```

**Measured before:** `IndexError: list index out of range`

**Measured after:**  `OK`

**The model said:** The change adds a check to ensure that the `formats` list is non-empty before attempting to iterate over it, which resolves the `IndexError: list index out of range` failure observed in the project's own tests.

`youtube-dl-30` — grounded: ____   invented: ____   direction: ____

---

## 26. `matplotlib-8`  (matplotlib)

**Commit message:** FIX: cancel pending autoscale on manually setting limits

**Test run:** `pytest lib/matplotlib/tests/test_axes.py::test_unautoscaley;pytest lib/matplotlib/tests/test_axes.py::test_unautoscalex`

```diff
diff --git a/lib/matplotlib/axes/_base.py b/lib/matplotlib/axes/_base.py
index aec405415..30376c242 100644
--- a/lib/matplotlib/axes/_base.py
+++ b/lib/matplotlib/axes/_base.py
@@ -3332,6 +3332,9 @@ class _AxesBase(martist.Artist):
         left, right = sorted([left, right], reverse=bool(reverse))
 
         self._viewLim.intervalx = (left, right)
+        # Mark viewlims as no longer stale without triggering an autoscale.
+        for ax in self._shared_x_axes.get_siblings(self):
+            ax._stale_viewlim_x = False
         if auto is not None:
             self._autoscaleXon = bool(auto)
 
@@ -3601,6 +3604,9 @@ class _AxesBase(martist.Artist):
         bottom, top = sorted([bottom, top], reverse=bool(reverse))
 
         self._viewLim.intervaly = (bottom, top)
+        # Mark viewlims as no longer stale without triggering an autoscale.
+        for ax in self._shared_y_axes.get_siblings(self):
+            ax._stale_viewlim_y = False
         if auto is not None:
             self._autoscaleYon = bool(auto)
```

**Measured before:** `AssertionError:`

**Measured after:**  `3 passed`

**The model said:** The change removes the `self._stale_viewlim_x` and `self._stale_viewlim_y` flags from the `_AxesBase` class, which were used to prevent an autoscale when setting manual limits. This eliminates the assertion error that was previously observed, allowing the project's tests to pass again.

`matplotlib-8` — grounded: ____   invented: ____   direction: ____

---

## 27. `fastapi-3`  (fastapi)

**Commit message:** :bug: Fix exclude_unset and aliases in response model validation (#1074)

**Test run:** `pytest tests/test_serialize_response_model.py::test_valid`

```diff
diff --git a/fastapi/routing.py b/fastapi/routing.py
index b361048..b90935e 100644
--- a/fastapi/routing.py
+++ b/fastapi/routing.py
@@ -48,6 +48,28 @@ except ImportError:  # pragma: nocover
     from pydantic.fields import Field as ModelField  # type: ignore
 
 
+def _prepare_response_content(
+    res: Any, *, by_alias: bool = True, exclude_unset: bool
+) -> Any:
+    if isinstance(res, BaseModel):
+        if PYDANTIC_1:
+            return res.dict(by_alias=by_alias, exclude_unset=exclude_unset)
+        else:
+            return res.dict(
+                by_alias=by_alias, skip_defaults=exclude_unset
+            )  # pragma: nocover
+    elif isinstance(res, list):
+        return [
+            _prepare_response_content(item, exclude_unset=exclude_unset) for item in res
+        ]
+    elif isinstance(res, dict):
+        return {
+            k: _prepare_response_content(v, exclude_unset=exclude_unset)
+            for k, v in res.items()
+        }
+    return res
+
+
 async def serialize_response(
     *,
     field: ModelField = None,
@@ -60,13 +82,9 @@ async def serialize_response(
 ) -> Any:
     if field:
         errors = []
-        if exclude_unset and isinstance(response_content, BaseModel):
-            if PYDANTIC_1:
-                response_content = response_content.dict(exclude_unset=exclude_unset)
-            else:
-                response_content = response_content.dict(
-                    skip_defaults=exclude_unset
-                )  # pragma: nocover
+        response_content = _prepare_response_content(
+            response_content, by_alias=by_alias, exclude_unset=exclude_unset
+        )
         if is_coroutine:
             value, errors_ = field.validate(response_content, {}, loc=("response",))
         else:
```

**Measured before:** `pydantic.error_wrappers.ValidationError: 1 validation error for Item`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `exclude_unset` parameter was moved from the `serialize_response` function to the `_prepare_response_content` helper function, which simplifies the logic and reduces duplication. This change ensures that the validation error is no longer raised when `exclude_unset` is true and the response content is a `BaseModel`, as the validation is now handled by the helper function.

`fastapi-3` — grounded: ____   invented: ____   direction: ____

---

## 28. `youtube-dl-1`  (youtube-dl)

**Commit message:** [utils] Fix match_str for boolean meta fields

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_match_str`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index 027d12785..574284e94 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -2574,8 +2574,8 @@ def _match_one(filter_part, dct):
         return op(actual_value, comparison_value)
 
     UNARY_OPERATORS = {
-        '': lambda v: v is not None,
-        '!': lambda v: v is None,
+        '': lambda v: (v is True) if isinstance(v, bool) else (v is not None),
+        '!': lambda v: (v is False) if isinstance(v, bool) else (v is None),
     }
     operator_rex = re.compile(r'''(?x)\s*
         (?P<op>%s)\s*(?P<key>[a-z_]+)
```

**Measured before:** `AssertionError: True is not false`

**Measured after:**  `OK`

**The model said:** The change updates the `UNARY_OPERATORS` dictionary to correctly handle boolean values when evaluating the `!` operator, which previously caused the test to fail with `AssertionError: True is not false`. The updated logic ensures that the `!` operator correctly identifies `False` as a falsy value, allowing the test to pass without raising an assertion error.

`youtube-dl-1` — grounded: ____   invented: ____   direction: ____

---

## 29. `fastapi-8`  (fastapi)

**Commit message:** :bug: Fix preserving route_class when calling include_router (#538)

**Test run:** `pytest tests/test_custom_route_class.py::test_route_classes`

```diff
diff --git a/fastapi/routing.py b/fastapi/routing.py
index 8f61ea5..b090231 100644
--- a/fastapi/routing.py
+++ b/fastapi/routing.py
@@ -348,8 +348,10 @@ class APIRouter(routing.Router):
         include_in_schema: bool = True,
         response_class: Type[Response] = None,
         name: str = None,
+        route_class_override: Optional[Type[APIRoute]] = None,
     ) -> None:
-        route = self.route_class(
+        route_class = route_class_override or self.route_class
+        route = route_class(
             path,
             endpoint=endpoint,
             response_model=response_model,
@@ -487,6 +489,7 @@ class APIRouter(routing.Router):
                     include_in_schema=route.include_in_schema,
                     response_class=route.response_class or default_response_class,
                     name=route.name,
+                    route_class_override=type(route),
                 )
             elif isinstance(route, routing.Route):
                 self.add_route(
```

**Measured before:** `AttributeError: 'APIRoute' object has no attribute 'x_type'`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `route_class` parameter was added to the `APIRouter` constructor, which allows developers to override the default route class. This change resolves the `AttributeError: 'APIRoute' object has no attribute 'x_type'` by providing a new keyword argument for specifying the route class, ensuring that the project's own tests now pass without warnings.

`fastapi-8` — grounded: ____   invented: ____   direction: ____

---

## 30. `pandas-7`  (pandas)

**Commit message:** BUG: fix reindexing with a tz-aware index and method='nearest' (#31511)

**Test run:** `pytest pandas/tests/frame/indexing/test_indexing.py::TestDataFrameIndexing::test_reindex_nearest_tz`

```diff
diff --git a/pandas/core/indexes/base.py b/pandas/core/indexes/base.py
index d8b645746..6a7551391 100644
--- a/pandas/core/indexes/base.py
+++ b/pandas/core/indexes/base.py
@@ -3073,9 +3073,8 @@ class Index(IndexOpsMixin, PandasObject):
         left_indexer = self.get_indexer(target, "pad", limit=limit)
         right_indexer = self.get_indexer(target, "backfill", limit=limit)
 
-        target = np.asarray(target)
-        left_distances = abs(self.values[left_indexer] - target)
-        right_distances = abs(self.values[right_indexer] - target)
+        left_distances = np.abs(self[left_indexer] - target)
+        right_distances = np.abs(self[right_indexer] - target)
 
         op = operator.lt if self.is_monotonic_increasing else operator.le
         indexer = np.where(
```

**Measured before:** `numpy.core._exceptions.UFuncTypeError: ufunc 'subtract' cannot use operands with types dtype('<M8[ns]') and dtype('O')`

**Measured after:**  `13 passed`

**The model said:** The change replaces direct indexing with `self[left_indexer]` and `self[right_indexer]` to access values directly, which removes the need for `np.asarray` and simplifies the comparison logic. This refactoring resolves the `numpy.core._exceptions.UFuncTypeError: ufunc 'subtract' cannot use operands with types dtype('<M8[ns]') and dtype('O')` error, allowing the project's own tests to pass without modification.

`pandas-7` — grounded: ____   invented: ____   direction: ____

---

## 31. `black-23`  (black)

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

**The model said:** (nothing)

`black-23` — grounded: ____   invented: ____   direction: ____

---

## 32. `matplotlib-14`  (matplotlib)

**Commit message:** Lower Text's FontProperties priority when updating

**Test run:** `pytest lib/matplotlib/tests/test_text.py::test_fontproperties_kwarg_precedence`

```diff
diff --git a/lib/matplotlib/text.py b/lib/matplotlib/text.py
index 78fb5c57f..2a8a708e7 100644
--- a/lib/matplotlib/text.py
+++ b/lib/matplotlib/text.py
@@ -174,8 +174,12 @@ class Text(Artist):
 
     def update(self, kwargs):
         # docstring inherited
-        # Update bbox last, as it depends on font properties.
         sentinel = object()  # bbox can be None, so use another sentinel.
+        # Update fontproperties first, as it has lowest priority.
+        fontproperties = kwargs.pop("fontproperties", sentinel)
+        if fontproperties is not sentinel:
+            self.set_fontproperties(fontproperties)
+        # Update bbox last, as it depends on font properties.
         bbox = kwargs.pop("bbox", sentinel)
         super().update(kwargs)
         if bbox is not sentinel:
```

**Measured before:** `AssertionError: assert 12.0 == 40.0`

**Measured after:**  `1 passed`

**The model said:** The order of `fontproperties` and `bbox` updates was swapped in `Text.update`, which resolved an assertion error where the text height was incorrectly calculated.

`matplotlib-14` — grounded: ____   invented: ____   direction: ____

---

## 33. `matplotlib-25`  (matplotlib)

**Commit message:** Backport PR #14488: Make sure EventCollection doesn't modify input in-place

**Test run:** `pytest lib/matplotlib/tests/test_collections.py::test_EventCollection_nosort`

```diff
diff --git a/lib/matplotlib/collections.py b/lib/matplotlib/collections.py
index b7a7219ca..74c8b936d 100644
--- a/lib/matplotlib/collections.py
+++ b/lib/matplotlib/collections.py
@@ -1470,12 +1470,15 @@ class EventCollection(LineCollection):
 
         .. plot:: gallery/lines_bars_and_markers/eventcollection_demo.py
         """
-
+        if positions is None:
+            raise ValueError('positions must be an array-like object')
+        # Force a copy of positions
+        positions = np.array(positions, copy=True)
         segment = (lineoffset + linelength / 2.,
                    lineoffset - linelength / 2.)
-        if positions is None or len(positions) == 0:
+        if positions.size == 0:
             segments = []
-        elif hasattr(positions, 'ndim') and positions.ndim > 1:
+        elif positions.ndim > 1:
             raise ValueError('positions cannot be an array with more than '
                              'one dimension.')
         elif (orientation is None or orientation.lower() == 'none' or
```

**Measured before:** `AssertionError:`

**Measured after:**  `1 passed`

**The model said:** The change adds a check for `positions` being `None` and raises a `ValueError` if so, ensuring that the input is always an array-like object. This prevents the original assertion error from failing, which now passes instead.

`matplotlib-25` — grounded: ____   invented: ____   direction: ____

---

## 34. `scrapy-3`  (scrapy)

**Commit message:** Fix redirection error when the Location header value starts with 3 slashes (#4042)

**Test run:** `python -m unittest -q tests.test_downloadermiddleware_redirect.RedirectMiddlewareTest.test_redirect_302_relative`

```diff
diff --git a/scrapy/downloadermiddlewares/redirect.py b/scrapy/downloadermiddlewares/redirect.py
index 49468a2e..b73f864d 100644
--- a/scrapy/downloadermiddlewares/redirect.py
+++ b/scrapy/downloadermiddlewares/redirect.py
@@ -1,5 +1,5 @@
 import logging
-from six.moves.urllib.parse import urljoin
+from six.moves.urllib.parse import urljoin, urlparse
 
 from w3lib.url import safe_url_string
 
@@ -70,7 +70,10 @@ class RedirectMiddleware(BaseRedirectMiddleware):
         if 'Location' not in response.headers or response.status not in allowed_status:
             return response
 
-        location = safe_url_string(response.headers['location'])
+        location = safe_url_string(response.headers['Location'])
+        if response.headers['Location'].startswith(b'//'):
+            request_scheme = urlparse(request.url).scheme
+            location = request_scheme + '://' + location.lstrip('/')
 
         redirected_url = urljoin(request.url, location)
```

**Measured before:** `AssertionError: 'http://www.example.com/i8n.example2.com/302' != 'http://i8n.example2.com/302'`

**Measured after:**  `OK`

**The model said:** The change removes the `urljoin` call when the `Location` header starts with `//`, which causes the redirect URL to be constructed without the scheme. This resolves the assertion error by ensuring the redirect URL is correctly formed, allowing the test to pass.

`scrapy-3` — grounded: ____   invented: ____   direction: ____

---

## 35. `luigi-10`  (luigi)

**Commit message:** Filters tasks in second branch of Worker.get_pending_tasks (#1849)

**Test run:** `pytest test/scheduler_test.py::SchedulerWorkerTest::test_get_pending_tasks_with_many_done_tasks`

```diff
diff --git a/luigi/scheduler.py b/luigi/scheduler.py
index 16b203b1..6cc4b87f 100644
--- a/luigi/scheduler.py
+++ b/luigi/scheduler.py
@@ -302,7 +302,7 @@ class Worker(object):
             return six.moves.filter(lambda task: task.status in [PENDING, RUNNING],
                                     self.tasks)
         else:
-            return state.get_pending_tasks()
+            return six.moves.filter(lambda task: self.id in task.workers, state.get_pending_tasks())
 
     def is_trivial_worker(self, state):
         """
```

**Measured before:** `AssertionError: Items in the second set but not the first:`

**Measured after:**  `1 passed, 20 warnings`

**The model said:** The `Worker.get_pending_tasks` method now filters tasks based on whether the worker ID is present in the task's `workers` list instead of using the `state.get_pending_tasks()` method directly. This change resolves the assertion error by ensuring that only tasks assigned to the current worker are considered pending, which was previously causing the test to fail.

`luigi-10` — grounded: ____   invented: ____   direction: ____

---

## 36. `matplotlib-13`  (matplotlib)

**Commit message:** fix bug where make_compound_path kept all STOPs

**Test run:** `pytest lib/matplotlib/tests/test_path.py::test_make_compound_path_stops`

```diff
diff --git a/lib/matplotlib/path.py b/lib/matplotlib/path.py
index 93165dc68..f56746b88 100644
--- a/lib/matplotlib/path.py
+++ b/lib/matplotlib/path.py
@@ -330,6 +330,7 @@ class Path:
         if not args:
             return Path(np.empty([0, 2], dtype=np.float32))
 
+        # concatenate paths
         vertices = np.concatenate([x.vertices for x in args])
         codes = np.empty(len(vertices), dtype=cls.code_type)
         i = 0
@@ -341,6 +342,16 @@ class Path:
                 codes[i:i + len(path.codes)] = path.codes
             i += len(path.vertices)
 
+        # remove internal STOP's, replace kinal stop if present
+        last_vert = None
+        if codes.size > 0 and codes[-1] == cls.STOP:
+            last_vert = vertices[-1]
+        vertices = vertices[codes != cls.STOP, :]
+        codes = codes[codes != cls.STOP]
+        if last_vert is not None:
+            vertices = np.append(vertices, [last_vert], axis=0)
+            codes = np.append(codes, cls.STOP)
+
         return cls(vertices, codes)
 
     def __repr__(self):
```

**Measured before:** `assert 3 == 1`

**Measured after:**  `1 passed`

**The model said:** The change removes internal STOPs from compound paths, replacing the final STOP if present, which fixes the test assertion that was failing before.

`matplotlib-13` — grounded: ____   invented: ____   direction: ____

---

## 37. `luigi-27`  (luigi)

**Commit message:** Fix bug where command line Tasks skip config

**Test run:** `pytest test/parameter_test.py::TestParamWithDefaultFromConfig::testCommandLineWithDefault`

```diff
diff --git a/luigi/parameter.py b/luigi/parameter.py
index 6d12f2b7..9b742d8f 100644
--- a/luigi/parameter.py
+++ b/luigi/parameter.py
@@ -279,7 +279,7 @@ class Parameter(object):
             return [str(v) for v in x]
         return str(x)
 
-    def parse_from_input(self, param_name, x):
+    def parse_from_input(self, param_name, x, task_name=None):
         """
         Parses the parameter value from input ``x``, handling defaults and is_list.
 
@@ -289,8 +289,8 @@ class Parameter(object):
         :raises MissingParameterException: if x is false-y and no default is specified.
         """
         if not x:
-            if self.has_value:
-                return self.value
+            if self.has_task_value(param_name=param_name, task_name=task_name):
+                return self.task_value(param_name=param_name, task_name=task_name)
             elif self.is_bool:
                 return False
             elif self.is_list:
@@ -333,8 +333,9 @@ class Parameter(object):
             description.append('for all instances of class %s' % task_name)
         elif self.description:
             description.append(self.description)
-        if self.has_value:
-            description.append(" [default: %s]" % (self.value,))
+        if self.has_task_value(param_name=param_name, task_name=task_name):
+            value = self.task_value(param_name=param_name, task_name=task_name)
+            description.append(" [default: %s]" % (value,))
 
         if self.is_list:
             action = "append"
@@ -356,7 +357,7 @@ class Parameter(object):
         dest = self.parser_dest(param_name, task_name, glob=False)
         if dest is not None:
             value = getattr(args, dest, None)
-            params[param_name] = self.parse_from_input(param_name, value)
+            params[param_name] = self.parse_from_input(param_name, value, task_name=task_name)
 
     def set_global_from_args(self, param_name, task_name, args, is_without_section=False):
         # Note: side effects
@@ -364,7 +365,7 @@ class Parameter(object):
         if dest is not None:
             value = getattr(args, dest, None)
             if value:
-                self.set_global(self.parse_from_input(param_name, value))
+                self.set_global(self.parse_from_input(param_name, value, task_name=task_name))
             else:  # either False (bools) or None (everything else)
                 self.reset_global()
```

**Measured before:** `AssertionError: False is not true`

**Measured after:**  `1 passed, 5 warnings`

**The model said:** The `parse_from_input` method now includes a `task_name` parameter, which allows the default value to be retrieved based on the task name instead of the class-level default. This change resolves the assertion error by providing the correct default value when the parameter is not explicitly set on the command line, allowing the project's own tests to pass with 1 passed and 5 warnings.

`luigi-27` — grounded: ____   invented: ____   direction: ____

---

## 38. `thefuck-10`  (thefuck)

**Commit message:** Don't suggest `man 2/3 foo` if no man pages exist

**Test run:** `pytest tests/rules/test_man.py::test_get_new_command`

```diff
diff --git a/thefuck/rules/man.py b/thefuck/rules/man.py
index 3d0347a..e4ec54d 100644
--- a/thefuck/rules/man.py
+++ b/thefuck/rules/man.py
@@ -12,16 +12,22 @@ def get_new_command(command):
     if '2' in command.script:
         return command.script.replace("2", "3")
 
+    last_arg = command.script_parts[-1]
+    help_command = last_arg + ' --help'
+
+    # If there are no man pages for last_arg, suggest `last_arg --help` instead.
+    # Otherwise, suggest `--help` after suggesting other man page sections.
+    if command.stderr.strip() == 'No manual entry for ' + last_arg:
+        return [help_command]
+
     split_cmd2 = command.script_parts
     split_cmd3 = split_cmd2[:]
 
     split_cmd2.insert(1, ' 2 ')
     split_cmd3.insert(1, ' 3 ')
 
-    last_arg = command.script_parts[-1]
-
     return [
-        last_arg + ' --help',
         "".join(split_cmd3),
         "".join(split_cmd2),
+        help_command,
     ]
```

**Measured before:** `AssertionError: assert ['read --help... 'man 2 read'] == ['man 3 read',...'read --help']`

**Measured after:**  `8 passed`

**The model said:** The commit removes the direct suggestion of `last_arg --help` from the list of commands, replacing it with a more generic `--help` suggestion. This change allows the script to fall back to the default help output when no man pages are available, which is a more robust approach that avoids hardcoding specific command-line options.

`thefuck-10` — grounded: ____   invented: ____   direction: ____

---

## 39. `matplotlib-23`  (matplotlib)

**Commit message:** Fix nonsensical transform in mixed-mode axes aspect computation.

**Test run:** `pytest lib/matplotlib/tests/test_axes.py::test_aspect_nonlinear_adjustable_datalim`

```diff
diff --git a/lib/matplotlib/axes/_base.py b/lib/matplotlib/axes/_base.py
index 2e519a74c..7ecddbc02 100644
--- a/lib/matplotlib/axes/_base.py
+++ b/lib/matplotlib/axes/_base.py
@@ -1507,8 +1507,8 @@ class _AxesBase(martist.Artist):
             return
 
         dL = self.dataLim
-        x0, x1 = map(x_trf.inverted().transform, dL.intervalx)
-        y0, y1 = map(y_trf.inverted().transform, dL.intervaly)
+        x0, x1 = map(x_trf.transform, dL.intervalx)
+        y0, y1 = map(y_trf.transform, dL.intervaly)
         xr = 1.05 * (x1 - x0)
         yr = 1.05 * (y1 - y0)
```

**Measured before:** `assert (1.0, 100.0) == approx([3.162...93 ± 3.2e-05])`

**Measured after:**  `1 passed`

**The model said:** The change removes the `inverted()` call from the `map` transformations, which alters the axis limits calculation. This causes the test assertion to fail, as the computed aspect ratio changes from approximately 1.0 to 1.05.

`matplotlib-23` — grounded: ____   invented: ____   direction: ____

---

## 40. `scrapy-29`  (scrapy)

**Commit message:** Do not fail representing non-http requests

**Test run:** `python -m unittest -q tests.test_utils_request.UtilsRequestTest.test_request_httprepr_for_non_http_request`

```diff
diff --git a/scrapy/utils/request.py b/scrapy/utils/request.py
index ac415e50..0487d1e1 100644
--- a/scrapy/utils/request.py
+++ b/scrapy/utils/request.py
@@ -79,7 +79,7 @@ def request_httprepr(request):
     parsed = urlparse_cached(request)
     path = urlunparse(('', '', parsed.path or '/', parsed.params, parsed.query, ''))
     s = to_bytes(request.method) + b" " + to_bytes(path) + b" HTTP/1.1\r\n"
-    s += b"Host: " + to_bytes(parsed.hostname) + b"\r\n"
+    s += b"Host: " + to_bytes(parsed.hostname or b'') + b"\r\n"
     if request.headers:
         s += request.headers.to_string() + b"\r\n"
     s += b"\r\n"
```

**Measured before:** `TypeError: to_bytes must receive a unicode, str or bytes object, got NoneType`

**Measured after:**  `OK`

**The model said:** The change replaces `parsed.hostname` with `parsed.hostname or b''`, which prevents the TypeError when the hostname is `None`.

`scrapy-29` — grounded: ____   invented: ____   direction: ____

---

## 41. `ansible-17`  (ansible)

**Commit message:** Transform octal escape sequences in mtab fields (#60122)

**Test run:** `pytest test/units/module_utils/facts/test_facts.py::TestFactsLinuxHardwareGetMountFacts::test_get_mount_facts`

```diff
diff --git a/lib/ansible/module_utils/facts/hardware/linux.py b/lib/ansible/module_utils/facts/hardware/linux.py
index 19ca6e4799..befc2fb5e7 100644
--- a/lib/ansible/module_utils/facts/hardware/linux.py
+++ b/lib/ansible/module_utils/facts/hardware/linux.py
@@ -79,6 +79,9 @@ class LinuxHardware(Hardware):
     # regex used against mtab content to find entries that are bind mounts
     MTAB_BIND_MOUNT_RE = re.compile(r'.*bind.*"')
 
+    # regex used for replacing octal escape sequences
+    OCTAL_ESCAPE_RE = re.compile(r'\\[0-9]{3}')
+
     def populate(self, collected_facts=None):
         hardware_facts = {}
         self.module.run_command_environ_update = {'LANG': 'C', 'LC_ALL': 'C', 'LC_NUMERIC': 'C'}
@@ -460,6 +463,14 @@ class LinuxHardware(Hardware):
             mtab_entries.append(fields)
         return mtab_entries
 
+    @staticmethod
+    def _replace_octal_escapes_helper(match):
+        # Convert to integer using base8 and then convert to character
+        return chr(int(match.group()[1:], 8))
+
+    def _replace_octal_escapes(self, value):
+        return self.OCTAL_ESCAPE_RE.sub(self._replace_octal_escapes_helper, value)
+
     def get_mount_info(self, mount, device, uuids):
 
         mount_size = get_mount_size(mount)
@@ -485,6 +496,8 @@ class LinuxHardware(Hardware):
         pool = ThreadPool(processes=min(len(mtab_entries), cpu_count()))
         maxtime = globals().get('GATHER_TIMEOUT') or timeout.DEFAULT_GATHER_TIMEOUT
         for fields in mtab_entries:
+            # Transform octal escape sequences
+            fields = [self._replace_octal_escapes(field) for field in fields]
 
             device, mount, fstype, options = fields[0], fields[1], fields[2], fields[3]
```

**Measured before:** `AssertionError: 0 != 1`

**Measured after:**  `1 passed`

**The model said:** The commit adds a static method `_replace_octal_escapes` and a corresponding instance method `_replace_octal_escapes` to the `LinuxHardware` class. This refactoring replaces octal escape sequences in mtab fields before parsing them, which resolves an assertion error that was previously observed when the project's own tests were run.

`ansible-17` — grounded: ____   invented: ____   direction: ____

---

## 42. `scrapy-15`  (scrapy)

**Commit message:** Do not fail on canonicalizing URLs with wrong netlocs

**Test run:** `python -m unittest -q tests.test_utils_url.CanonicalizeUrlTest.test_canonicalize_url_idna_exceptions`

```diff
diff --git a/scrapy/utils/url.py b/scrapy/utils/url.py
index c80fc6e7..406eb584 100644
--- a/scrapy/utils/url.py
+++ b/scrapy/utils/url.py
@@ -41,9 +41,16 @@ def url_has_any_extension(url, extensions):
 
 
 def _safe_ParseResult(parts, encoding='utf8', path_encoding='utf8'):
+    # IDNA encoding can fail for too long labels (>63 characters)
+    # or missing labels (e.g. http://.example.com)
+    try:
+        netloc = parts.netloc.encode('idna')
+    except UnicodeError:
+        netloc = parts.netloc
+
     return (
         to_native_str(parts.scheme),
-        to_native_str(parts.netloc.encode('idna')),
+        to_native_str(netloc),
 
         # default encoding for path component SHOULD be UTF-8
         quote(to_bytes(parts.path, path_encoding), _safe_chars),
```

**Measured before:** `UnicodeError: encoding with 'idna' codec failed (UnicodeError: label empty or too long)`

**Measured after:**  `OK`

**The model said:** The change replaces the direct encoding of `parts.netloc` with `idna` in `_safe_ParseResult`, which was causing a `UnicodeError: label empty or too long` when the netloc contained a missing label. This fix ensures that the project's own tests no longer fail with this error.

`scrapy-15` — grounded: ____   invented: ____   direction: ____

---

## 43. `youtube-dl-37`  (youtube-dl)

**Commit message:** Fix unicode_escape (Fixes #2695)

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_uppercase_escpae`

```diff
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index 5f1f664c8..92fee966f 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -2,6 +2,7 @@
 # -*- coding: utf-8 -*-
 
 import calendar
+import codecs
 import contextlib
 import ctypes
 import datetime
@@ -1263,9 +1264,11 @@ class PagedList(object):
 
 
 def uppercase_escape(s):
+    unicode_escape = codecs.getdecoder('unicode_escape')
     return re.sub(
         r'\\U[0-9a-fA-F]{8}',
-        lambda m: m.group(0).decode('unicode-escape'), s)
+        lambda m: unicode_escape(m.group(0))[0],
+        s)
 
 try:
     struct.pack(u'!I', 0)
```

**Measured before:** `AttributeError: 'str' object has no attribute 'decode'`

**Measured after:**  `OK`

**The model said:** The `decode` method was removed from the `uppercase_escape` function, which replaced the direct call to `unicode_escape.decode`. This change resolves the `AttributeError: 'str' object has no attribute 'decode'` when running the project's own tests.

`youtube-dl-37` — grounded: ____   invented: ____   direction: ____

---

## 44. `scrapy-22`  (scrapy)

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

**The model said:** The change replaces `serialized_value.decode()` with `str(serialized_value)` inside the `XmlItemExporter` class, which resolves the `AttributeError: 'bool' object has no attribute 'decode'` when exporting non-string fields. This ensures that the project's own tests pass without errors.

`scrapy-22` — grounded: ____   invented: ____   direction: ____

---

## 45. `fastapi-7`  (fastapi)

**Commit message:** :bug: Fix issue with exotic pydantic error serialization (#748)

**Test run:** `pytest tests/test_multi_body_errors.py::test_jsonable_encoder_requiring_error`

```diff
diff --git a/fastapi/exception_handlers.py b/fastapi/exception_handlers.py
index cda2f8c..2b286d7 100644
--- a/fastapi/exception_handlers.py
+++ b/fastapi/exception_handlers.py
@@ -1,3 +1,4 @@
+from fastapi.encoders import jsonable_encoder
 from fastapi.exceptions import RequestValidationError
 from starlette.exceptions import HTTPException
 from starlette.requests import Request
@@ -19,5 +20,6 @@ async def request_validation_exception_handler(
     request: Request, exc: RequestValidationError
 ) -> JSONResponse:
     return JSONResponse(
-        status_code=HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()}
+        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
+        content={"detail": jsonable_encoder(exc.errors())},
     )
```

**Measured before:** `TypeError: Object of type Decimal is not JSON serializable`

**Measured after:**  `1 passed, 6 warnings`

**The model said:** The `RequestValidationError` handler now uses `jsonable_encoder` to serialize error details, which resolves the `TypeError: Object of type Decimal is not JSON serializable` issue, allowing the project's tests to pass without warnings.

`fastapi-7` — grounded: ____   invented: ____   direction: ____

---

## 46. `luigi-12`  (luigi)

**Commit message:** Caches get_autoconfig_client on a per-thread basis

**Test run:** `pytest test/hdfs_client_test.py::HdfsClientTest::test_get_autoconfig_client_cached`

```diff
diff --git a/luigi/contrib/hdfs/clients.py b/luigi/contrib/hdfs/clients.py
index f7ece64d..2e8399ba 100644
--- a/luigi/contrib/hdfs/clients.py
+++ b/luigi/contrib/hdfs/clients.py
@@ -19,33 +19,42 @@
 The implementations of the hdfs clients. The hadoop cli client and the
 snakebite client.
 """
-
+import logging
+import threading
 
 from luigi.contrib.hdfs import config as hdfs_config
 from luigi.contrib.hdfs import snakebite_client as hdfs_snakebite_client
 from luigi.contrib.hdfs import webhdfs_client as hdfs_webhdfs_client
 from luigi.contrib.hdfs import hadoopcli_clients as hdfs_hadoopcli_clients
 import luigi.contrib.target
-import logging
 
 logger = logging.getLogger('luigi-interface')
 
+_AUTOCONFIG_CLIENT = threading.local()
+
 
-def get_autoconfig_client():
+def get_autoconfig_client(client_cache=_AUTOCONFIG_CLIENT):
     """
     Creates the client as specified in the `luigi.cfg` configuration.
     """
-    configured_client = hdfs_config.get_configured_hdfs_client()
-    if configured_client == "webhdfs":
-        return hdfs_webhdfs_client.WebHdfsClient()
-    if configured_client == "snakebite":
-        return hdfs_snakebite_client.SnakebiteHdfsClient()
-    if configured_client == "snakebite_with_hadoopcli_fallback":
-        return luigi.contrib.target.CascadingClient([hdfs_snakebite_client.SnakebiteHdfsClient(),
-                                                     hdfs_hadoopcli_clients.create_hadoopcli_client()])
-    if configured_client == "hadoopcli":
-        return hdfs_hadoopcli_clients.create_hadoopcli_client()
-    raise Exception("Unknown hdfs client " + configured_client)
+    try:
+        return client_cache.client
+    except AttributeError:
+        configured_client = hdfs_config.get_configured_hdfs_client()
+        if configured_client == "webhdfs":
+            client_cache.client = hdfs_webhdfs_client.WebHdfsClient()
+        elif configured_client == "snakebite":
+            client_cache.client = hdfs_snakebite_client.SnakebiteHdfsClient()
+        elif configured_client == "snakebite_with_hadoopcli_fallback":
+            client_cache.client = luigi.contrib.target.CascadingClient([
+                hdfs_snakebite_client.SnakebiteHdfsClient(),
+                hdfs_hadoopcli_clients.create_hadoopcli_client(),
+            ])
+        elif configured_client == "hadoopcli":
+            client_cache.client = hdfs_hadoopcli_clients.create_hadoopcli_client()
+        else:
+            raise Exception("Unknown hdfs clie
... (truncated)
```

**Measured before:** `AssertionError: <luigi.contrib.hdfs.hadoopcli_clients.HdfsClient object at 0x7f82403d9310> is not <luigi.contrib.hdfs.hadoopcli_clients.HdfsClient object at 0x7f82403d9340>`

**Measured after:**  `1 passed, 20 warnings`

**The model said:** The commit caches the auto-configured HDFS client on a per-thread basis using a `threading.local` instance, which prevents multiple threads from creating separate instances of the client. This change resolves the assertion error that occurred when multiple threads tried to create the client concurrently, ensuring consistent behavior across all tests.

`luigi-12` — grounded: ____   invented: ____   direction: ____

---

## 47. `luigi-24`  (luigi)

**Commit message:** Merge pull request #1001 from pbamba/spark_config

**Test run:** `pytest test/contrib/spark_test.py::SparkSubmitTaskTest::test_run`

```diff
diff --git a/luigi/contrib/spark.py b/luigi/contrib/spark.py
index c5c6afba..34c3e615 100644
--- a/luigi/contrib/spark.py
+++ b/luigi/contrib/spark.py
@@ -269,7 +269,7 @@ class SparkSubmitTask(luigi.Task):
         command = []
         if value and isinstance(value, dict):
             for prop, value in value.items():
-                command += [name, '"{0}={1}"'.format(prop, value)]
+                command += [name, '{0}={1}'.format(prop, value)]
         return command
 
     def _flag_arg(self, name, value):
```

**Measured before:** `AssertionError: Lists differ: ['ss-[240 chars]f', '"Prop=Value"', '--properties-file', 'conf[346 chars]rg2'] != ['ss-[240 chars]f', 'Prop=Value', '--properties-file', 'conf/s[344 chars]rg2']`

**Measured after:**  `1 passed, 3 warnings`

**The model said:** The change replaces double quotes around the property assignment in the `SparkSubmitTask` constructor with single quotes, which alters the output format of the command line arguments. This modification causes the test suite to fail, as the list element containing the property assignment now includes double quotes instead of single quotes. The project's own tests now pass with 1 assertion and 3 warnings.

`luigi-24` — grounded: ____   invented: ____   direction: ____

---

## 48. `youtube-dl-40`  (youtube-dl)

**Commit message:** Fix f4m downloading on Python 2.6

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_struct_unpack`

```diff
diff --git a/youtube_dl/downloader/f4m.py b/youtube_dl/downloader/f4m.py
index 9a6c03556..052751106 100644
--- a/youtube_dl/downloader/f4m.py
+++ b/youtube_dl/downloader/f4m.py
@@ -4,13 +4,14 @@ import base64
 import io
 import itertools
 import os
-from struct import unpack, pack
 import time
 import xml.etree.ElementTree as etree
 
 from .common import FileDownloader
 from .http import HttpFD
 from ..utils import (
+    struct_pack,
+    struct_unpack,
     compat_urllib_request,
     compat_urlparse,
     format_bytes,
@@ -27,13 +28,13 @@ class FlvReader(io.BytesIO):
 
     # Utility functions for reading numbers and strings
     def read_unsigned_long_long(self):
-        return unpack('!Q', self.read(8))[0]
+        return struct_unpack('!Q', self.read(8))[0]
 
     def read_unsigned_int(self):
-        return unpack('!I', self.read(4))[0]
+        return struct_unpack('!I', self.read(4))[0]
 
     def read_unsigned_char(self):
-        return unpack('!B', self.read(1))[0]
+        return struct_unpack('!B', self.read(1))[0]
 
     def read_string(self):
         res = b''
@@ -196,7 +197,7 @@ def write_flv_header(stream, metadata):
     # Script data
     stream.write(b'\x12')
     # Size of the metadata with 3 bytes
-    stream.write(pack('!L', len(metadata))[1:])
+    stream.write(struct_pack('!L', len(metadata))[1:])
     stream.write(b'\x00\x00\x00\x00\x00\x00\x00')
     stream.write(metadata)
     # Magic numbers extracted from the output files produced by AdobeHDS.php
diff --git a/youtube_dl/utils.py b/youtube_dl/utils.py
index 67c6af507..dd03f058f 100644
--- a/youtube_dl/utils.py
+++ b/youtube_dl/utils.py
@@ -17,6 +17,7 @@ import platform
 import re
 import ssl
 import socket
+import struct
 import subprocess
 import sys
 import traceback
@@ -1220,3 +1221,20 @@ def uppercase_escape(s):
     return re.sub(
         r'\\U([0-9a-fA-F]{8})',
         lambda m: compat_chr(int(m.group(1), base=16)), s)
+
+try:
+    struct.pack(u'!I', 0)
+except TypeError:
+    # In Python 2.6 (and some 2.7 versions), struct requires a bytes argument
+    def struct_pack(spec, *args):
+        if isinstance(spec, compat_str):
+            spec = spec.encode('ascii')
+        return struct.pack(spec, *args)
+
+    def struct_unpack(spec, *args):
+        if isinstance(spec, compat_str):
+            spec = spec.encode('ascii')
+        return struct.unpack(spec, *args)
+else:
+    struct_pack = struct.pack
+    struct_unpack = struct.unpack
```

**Measured before:** `ImportError: cannot import name 'struct_unpack' from 'youtube_dl.utils' (<repo>/youtube_dl/utils.py)`

**Measured after:**  `OK`

**The model said:** The `struct` module was updated to support Unicode literals in the `pack` and `unpack` functions, which resolves the `ImportError: cannot import name 'struct_unpack' from 'youtube_dl.utils'` when running the project's own tests on Python 2.6.

`youtube-dl-40` — grounded: ____   invented: ____   direction: ____

---

## 49. `youtube-dl-38`  (youtube-dl)

**Commit message:** [facebook] Fix login process

**Test run:** `python -m unittest -q test.test_utils.TestUtil.test_urlencode_postdata`

```diff
diff --git a/youtube_dl/extractor/facebook.py b/youtube_dl/extractor/facebook.py
index f6b5f589a..848a2c263 100644
--- a/youtube_dl/extractor/facebook.py
+++ b/youtube_dl/extractor/facebook.py
@@ -11,6 +11,7 @@ from ..utils import (
     compat_urllib_error,
     compat_urllib_parse,
     compat_urllib_request,
+    urlencode_postdata,
 
     ExtractorError,
 )
@@ -51,8 +52,8 @@ class FacebookIE(InfoExtractor):
 
         login_page_req = compat_urllib_request.Request(self._LOGIN_URL)
         login_page_req.add_header('Cookie', 'locale=en_US')
-        self.report_login()
-        login_page = self._download_webpage(login_page_req, None, note=False,
+        login_page = self._download_webpage(login_page_req, None,
+            note='Downloading login page',
             errnote='Unable to download login page')
         lsd = self._search_regex(
             r'<input type="hidden" name="lsd" value="([^"]*)"',
@@ -70,23 +71,25 @@ class FacebookIE(InfoExtractor):
             'timezone': '-60',
             'trynum': '1',
             }
-        request = compat_urllib_request.Request(self._LOGIN_URL, compat_urllib_parse.urlencode(login_form))
+        request = compat_urllib_request.Request(self._LOGIN_URL, urlencode_postdata(login_form))
         request.add_header('Content-Type', 'application/x-www-form-urlencoded')
         try:
-            login_results = compat_urllib_request.urlopen(request).read()
+            login_results = self._download_webpage(request, None,
+                note='Logging in', errnote='unable to fetch login page')
             if re.search(r'<form(.*)name="login"(.*)</form>', login_results) is not None:
                 self._downloader.report_warning('unable to log in: bad username/password, or exceded login rate limit (~3/min). Check credentials or wait.')
                 return
 
             check_form = {
-                'fb_dtsg': self._search_regex(r'"fb_dtsg":"(.*?)"', login_results, 'fb_dtsg'),
+                'fb_dtsg': self._search_regex(r'name="fb_dtsg" value="(.+?)"', login_results, 'fb_dtsg'),
                 'nh': self._search_regex(r'name="nh" value="(\w*?)"', login_results, 'nh'),
                 'name_action_selected': 'dont_save',
-                'submit[Continue]': self._search_regex(r'<input value="(.*?)" name="submit\[Continue\]"', login_results, 'continue'),
+                'submit[Continue]': self._search_regex(r'<button[^>]+value="(.*?)"[^>]+name="submit\[Continue\]"', login_results, 'continue')
... (truncated)
```

**Measured before:** `ImportError: cannot import name 'urlencode_postdata' from 'youtube_dl.utils' (<repo>/youtube_dl/utils.py)`

**Measured after:**  `OK`

**The model said:** The `urlencode_postdata` function was added to `youtube_dl.utils`, which resolves the `ImportError: cannot import name 'urlencode_postdata' from 'youtube_dl.utils' (<repo>/youtube_dl/utils.py)` when running the project's own tests.

`youtube-dl-38` — grounded: ____   invented: ____   direction: ____

---

## 50. `luigi-15`  (luigi)

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

**The model said:** The `UNKNOWN` state was added to the list of statuses that cause a task to be pruned, which reduced the number of failures from 1 to 2.

`luigi-15` — grounded: ____   invented: ____   direction: ____

---
