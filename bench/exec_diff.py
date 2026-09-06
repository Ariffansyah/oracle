"""Run pre and post, and report the behavioural difference as fact.

The model's job becomes explaining a difference it is SHOWN, not predicting one.
That removes the two failure modes the 2 Sep hand-grade found most damaging:
an inverted before/after cannot survive being handed the real values, and a
fabricated `ValueError` cannot survive being handed the real exception.
"""
import json, pathlib, shutil, subprocess, tempfile, sys

ROOT = pathlib.Path("bench/basic")
TIMEOUT = 15

def cmd_for(ext, src, workdir):
    b = str(workdir / "b")
    return {
        "py":   (None, ["python3", src]),
        "js":   (None, ["node", src]),
        "ts":   (None, ["node", "--experimental-strip-types", src]),
        "rb":   (None, ["ruby", src]),
        "php":  (None, ["php", src]),
        "go":   (None, ["go", "run", src]),
        "java": (None, ["java", src]),
        "c":    (["gcc", "-w", src, "-o", b], [b]),
        "rs":   (["rustc", "-A", "warnings", src, "-o", b], [b]),
    }.get(ext)

def run_one(path: pathlib.Path, ext: str):
    with tempfile.TemporaryDirectory() as td:
        wd = pathlib.Path(td)
        # java's single-file launcher needs the filename to match the class
        name = path.name
        if ext == "java":
            cls = "Main"
            for line in path.read_text().splitlines():
                if "class " in line:
                    cls = line.split("class ")[1].split()[0].strip("{ ")
                    break
            name = f"{cls}.java"
        dst = wd / name
        shutil.copy(path, dst)
        spec = cmd_for(ext, str(dst), wd)
        if spec is None:
            return {"status": "unsupported"}
        build, run = spec
        try:
            if build:
                b = subprocess.run(build, capture_output=True, text=True,
                                   timeout=TIMEOUT, cwd=wd)
                if b.returncode != 0:
                    return {"status": "build-error",
                            "err": (b.stderr or "").strip().splitlines()[:1]}
            r = subprocess.run(run, capture_output=True, text=True,
                               timeout=TIMEOUT, cwd=wd)
            # `raw` is UNSTRIPPED. Stripping the comparison key erases exactly
            # the difference a whitespace change makes: a pre/post pair differing
            # only in `.strip()` compared EQUAL and was labelled clean. `out`
            # stays stripped for display; `raw` is what equality must use.
            return {"status": "ok", "rc": r.returncode,
                    "raw": (r.stdout or "")[:400],
                    "out": (r.stdout or "").strip()[:200],
                    "err": (r.stderr or "").strip().splitlines()[-1][:200]
                           if r.stderr.strip() else ""}
        except subprocess.TimeoutExpired:
            return {"status": "timeout"}

def main():
    out = {}
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        meta = json.loads((d / "meta.json").read_text())
        ext = meta["ext"]
        pre, post = d / f"pre.{ext}", d / f"post.{ext}"
        if not pre.exists() or not post.exists():
            continue
        a, b = run_one(pre, ext), run_one(post, ext)
        differs = (a.get("raw"), a.get("rc"), a.get("err")) != \
                  (b.get("raw"), b.get("rc"), b.get("err"))
        out[d.name] = {"buggy": bool(meta.get("buggy")), "lang": meta["language"],
                       "pre": a, "post": b, "differs": differs}
        print(f"{d.name:26} {'DIFFERS' if differs else 'same':8} "
              f"pre={a.get('out','')!r:>16} post={b.get('out','')!r:>16} "
              f"{a.get('status')}/{b.get('status')}", flush=True)
    json.dump(out, open(sys.argv[1], "w"), indent=1)


if __name__ == "__main__":
    main()
