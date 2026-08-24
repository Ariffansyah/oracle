#include <stdio.h>
#include <string.h>

int main(void) {
    char dst[8];
    const char *src = "hello world";
    strcpy(dst, src);
    printf("%s\n", dst);
    return 0;
}
