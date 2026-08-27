def safe_divide_x(a, b):
    if b == 0:
        return None
    return a / b

print(safe_divide_x(10, 0))
