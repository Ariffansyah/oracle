#include <stdio.h>
#include <string.h>

int main(void) {
    char dst[8];
    const char *src = "hello";
    strncpy(dst, src, sizeof(dst) - 1);
    dst[sizeof(dst) - 1] = '\0';
    printf("%s\n", dst);
    return 0;
}
