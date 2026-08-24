def drop_odd(d):
    for k in list(d):
        if d[k] % 2:
            del d[k]
    return d

print(sorted(drop_odd({"a": 1, "b": 2, "c": 3}).items()))
