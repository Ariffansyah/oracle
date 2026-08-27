#include <stdio.h>

int pages(int items, int per_page)
{
    return items / per_page;
}

int main(void)
{
    printf("%d\n", pages(10, 3));
    return 0;
}
