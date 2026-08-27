def row_maxes(rows):
    result = []
    for row in rows:
        best_x = 0
        for v in row:
            if v > best_x:
                best_x = v
        result.append(best_x)
    return result

print(row_maxes([[3, 1], [2, 9], [5]]))
