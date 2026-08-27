def tally(rows):
    total = 0
    for r in rows:
        subtotal = total + r
    return total

print(tally([1, 2, 3]))
