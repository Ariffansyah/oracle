def total(xs):
    s = 0
    i = 0
    while i < len(xs):
        s += xs[i]
        i += 1
    return s


print(total([1, 2, 3]))
