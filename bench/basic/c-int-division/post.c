#include <stdio.h>

double average(const int *xs, int n)
{
    int s = 0;
    for (int i = 0; i < n; i++) s += xs[i];
    return s / n;
}

int main(void)
{
    int xs[4] = {1, 2, 3, 4};
    printf("%.2f\n", average(xs, 4));
    return 0;
}
