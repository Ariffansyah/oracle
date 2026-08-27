def remove_evens(items):
    for x in items:
        if x % 2 == 0:
            items.remove(x)
    return items

print(remove_evens([2, 4, 6, 8, 1, 3]))
