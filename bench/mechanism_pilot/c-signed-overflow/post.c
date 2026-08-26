#include <stdio.h>
#include <limits.h>

int safe_add(int a, int b) {
    return a + b;
}

int main(void) {
    printf("%d\n", safe_add(2147483647, 1));
    return 0;
}
