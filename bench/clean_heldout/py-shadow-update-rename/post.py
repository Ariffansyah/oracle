def tally(rows):
    total_x = 0
    for r in rows:
        total_x = total_x + r
    return total_x

print(tally([1, 2, 3]))
