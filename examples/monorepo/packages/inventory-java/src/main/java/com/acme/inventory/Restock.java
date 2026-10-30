package com.acme.inventory;

/** Decide when a product must be ordered again. */
public final class Restock {
    private Restock() {}

    /** Whether the stock of a product fell below the minimum. */
    public static boolean needed(Inventory stock, String product, int minimum) {
        return stock.unitsOf(product) < minimum;
    }
}
