#include <stdio.h>

static int passing(int score) {
    return score >= 60;
}

const char *grade(int score) {
    if (passing(score)) return "pass";
    return "fail";
}

int main(void) {
    printf("%s %s\n", grade(60), grade(59));
    return 0;
}
