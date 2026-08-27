def with_sentinel(items):
    out = list(items)
    out.append(None)
    return out

data_x = [1, 2, 3]
result = with_sentinel(data_x)
print(data_x, result)
