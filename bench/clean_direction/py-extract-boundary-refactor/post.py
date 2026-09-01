def passing(score):
    return score >= 60


def grade(score):
    if passing(score):
        return "pass"
    return "fail"


print(grade(60), grade(59))
