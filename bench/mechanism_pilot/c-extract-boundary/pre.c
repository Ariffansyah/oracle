#include <stdio.h>

const char *grade(int score) {
    if (score >= 60) return "pass";
    return "fail";
}

int main(void) {
    printf("%s %s\n", grade(60), grade(59));
    return 0;
}
