#include <stdio.h>

int biggest(const int *xs, int n)
{
    int best = xs[0];
    for (int i = 1; i < n; i++)
        if (xs[i] > best) best = xs[i];
    return best;
}

int main(void)
{
    int xs[4] = {3, 9, 2, 7};
    printf("%d\n", biggest(xs, 4));
    return 0;
}
