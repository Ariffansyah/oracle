def safe_divide(a, b):
    if b == 0:
        return None
    return a / b

print(safe_divide(10, 0))
