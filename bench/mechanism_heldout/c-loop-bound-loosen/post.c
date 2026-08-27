#include <stdio.h>

int total(const int *xs, int n)
{
    int s = 0;
    for (int i = 0; i <= n; i++)
        s += xs[i];
    return s;
}

int main(void)
{
    int xs[3] = {1, 2, 3};
    printf("%d\n", total(xs, 3));
    return 0;
}
