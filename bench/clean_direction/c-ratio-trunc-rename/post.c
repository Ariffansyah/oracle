#include <stdio.h>

double score_percentage_x(int correct, int total)
{
    return (double)correct / total * 100.0;
}

int main(void)
{
    printf("%.2f\n", score_percentage_x(1, 3));
    return 0;
}
