"""The BugsInPy scoring rubric, checked against explanations it must separate.

Every check here is a pair: one explanation that should pass and one that should
not. A rubric only tested on the answers it likes measures the corpus, not the
model.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bench.eval_bugsinpy_arms import (from_commit_message, invents_exception,
                                      message_of, names_symbol,
                                      quotes_signature)

SIG = "TypeError: 'GalaxyAPI' object is not iterable"

# --- message_of: the class prefix is not part of the message ----------------
assert message_of(SIG) == "'GalaxyAPI' object is not iterable"
assert message_of("assert False") == "assert False"
assert message_of("AssertionError: assert 0 == 6") == "assert 0 == 6"

# --- quotes_signature -------------------------------------------------------
assert quotes_signature(
    "Before the change the verify path iterated the API object directly and "
    "raised \"'GalaxyAPI' object is not iterable\".", SIG)
# paraphrase that keeps the distinctive tokens still counts
assert quotes_signature(
    "The GalaxyAPI object was iterable nowhere, so iterating it failed.", SIG)
# a fluent explanation of the right change that never states the failure
assert not quotes_signature(
    "This commit improves the error message when MANIFEST.json is absent.", SIG)
# a different failure entirely
assert not quotes_signature(
    "It raised a KeyError because the manifest key was missing.", SIG)

# a short message must not pass on one incidental token
assert not quotes_signature("The list was empty.", "IndexError: list index out of range")
assert quotes_signature("it raised list index out of range on an empty list",
                        "IndexError: list index out of range")

# --- invents_exception ------------------------------------------------------
assert invents_exception("raises a TypeError here", "TypeError") is None
assert invents_exception("no exception is named at all", "TypeError") is None
bad = invents_exception("this used to raise a ValueError", "TypeError")
assert bad and "ValueError" in bad and "TypeError" in bad, bad
# naming both is not an invention -- the right one is present
assert invents_exception("a TypeError, not a ValueError", "TypeError") is None
# when the measured failure has no class, naming one is unsupported
bad2 = invents_exception("it raises a RuntimeError", "")
assert bad2 and "no exception" in bad2, bad2

# A signature can name a SECOND class, and that one is measured too. scrapy-5's
# test asserts a ValueError should have been raised; an explanation saying the
# commit now raises ValueError is right, and the first version of this rubric
# called it an invention.
SCRAPY5 = "AssertionError: ValueError not raised by follow"
assert invents_exception("the commit raises a ValueError for a None url",
                         "AssertionError", SCRAPY5) is None
COOKIE4 = ("AttributeError: module 'cookiecutter.exceptions' has no attribute "
           "'FailedHookException'")
assert invents_exception("it now raises FailedHookException when the hook fails",
                         "AttributeError", COOKIE4) is None
# but a class in neither the explanation's signature nor the class slot is still
# an invention
bad3 = invents_exception("this prevents a UnicodeDecodeError", "AssertionError",
                         SCRAPY5)
assert bad3 and "UnicodeDecodeError" in bad3, bad3
# and with no signature passed the old behaviour holds
assert invents_exception("raises a TypeError", "TypeError", "") is None

# --- a bare assertion is all operands ---------------------------------------
# the smoke run scored "previously asserted 0 == 6" as quoting nothing, because
# every informative token in `assert 0 == 6` is one character long
assert quotes_signature("the test that previously asserted 0 == 6 now passes",
                        "AssertionError: assert 0 == 6")
# but a number must match as a word, not as a substring of another number
assert not quotes_signature("the retry count went from 16 to 60",
                            "AssertionError: assert 0 == 6")

# --- names_symbol -----------------------------------------------------------
DIFF = """@@ -38,7 +38,7 @@ def tenumerate(iterable, start=0):
-    return enumerate(tqdm_class(iterable, start, **tqdm_kwargs))
+    return enumerate(tqdm_class(iterable, **tqdm_kwargs), start)
"""
assert names_symbol("the `start` argument moved to the `enumerate` call", DIFF)
assert names_symbol("tqdm_class is now called without it", DIFF)
# an explanation that locates nothing
assert not names_symbol("this commit fixes a bug in the library", DIFF)
# keywords in the diff must not count as locating anything
assert not names_symbol("it returns something", DIFF)

# --- from_commit_message ----------------------------------------------------
SUBJ = "Fixed #451 - OSError: [Errno 36] File name too long"
assert from_commit_message("this resolves the OSError for long names",
                           SUBJ, "AttributeError")
# an invention the author never wrote is the model's own
assert not from_commit_message("this resolves a KeyError", SUBJ, "AttributeError")
# naming the measured exception is not taking it from the message
assert not from_commit_message("it raised AttributeError", SUBJ, "AttributeError")

print("ok")
