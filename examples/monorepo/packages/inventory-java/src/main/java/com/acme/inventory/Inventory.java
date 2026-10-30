package com.acme.inventory;

/** What can tell how many units of a product are left. */
public interface Inventory {
    /** Units of a product left; zero when it was never added. */
    int unitsOf(String product);
}
