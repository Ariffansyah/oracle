#include <stdio.h>

double score_percentage(int correct, int total)
{
    return (double)(correct / total) * 100.0;
}

int main(void)
{
    printf("%.2f\n", score_percentage(1, 3));
    return 0;
}
