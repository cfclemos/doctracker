#include <stdio.h>
#include "reading.h"

/* Print the average of a few readings. */
int main(void) {
    int readings[] = {215, 220, 218};
    printf("%d\n", average(readings, 3));
    return 0;
}
