#include <stdio.h>
#include <limits.h>

int safe_add(int a, int b) {
    if (a > 0 && b > INT_MAX - a) return INT_MAX;
    if (a < 0 && b < INT_MIN - a) return INT_MIN;
    return a + b;
}

int main(void) {
    printf("%d\n", safe_add(2147483647, 1));
    return 0;
}
