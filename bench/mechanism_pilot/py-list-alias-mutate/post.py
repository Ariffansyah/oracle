def with_sentinel(items):
    out = items
    out.append(None)
    return out

data = [1, 2, 3]
result = with_sentinel(data)
print(data, result)
