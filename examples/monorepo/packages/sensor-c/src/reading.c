#include "reading.h"

/* Average of the readings, in tenths of a degree. */
int average(const int *readings, int count) {
    int sum = 0;
    for (int i = 0; i < count; i++) sum += readings[i];
    return count ? sum / count : 0;
}
