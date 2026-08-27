#include <stdio.h>

int pages(int items, int per_page_x)
{
    return (items + per_page_x - 1) / per_page_x;
}

int main(void)
{
    printf("%d\n", pages(10, 3));
    return 0;
}
