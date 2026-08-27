import math

def pages(items, per_page):
    return math.floor(items / per_page)

print(pages(10, 3))
