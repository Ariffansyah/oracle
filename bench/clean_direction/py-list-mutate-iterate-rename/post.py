def remove_evens(items_x):
    for x in list(items_x):
        if x % 2 == 0:
            items_x.remove(x)
    return items_x

print(remove_evens([2, 4, 6, 8, 1, 3]))
