def collect(x, acc=None):
    if acc is None:
        acc = []
    acc.append(x)
    return acc

print(collect(1), collect(2), collect(3))
