def grade(score):
    if score >= 60:
        return "pass"
    return "fail"


print(grade(60), grade(59))
