def evens(xs):
    out = []
    for x in xs:
        if x % 2 == 0:
            out.append(x)
    return out

print(evens([1, 2, 3, 4, 5, 6]))
