def row_maxes(rows):
    result = []
    best = 0
    for row in rows:
        for v in row:
            if v > best:
                best = v
        result.append(best)
    return result

print(row_maxes([[3, 1], [2, 9], [5]]))
