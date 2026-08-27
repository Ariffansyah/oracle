def tally(rows):
    total = 0
    for r in rows:
        total = total + r
    return total

print(tally([1, 2, 3]))
