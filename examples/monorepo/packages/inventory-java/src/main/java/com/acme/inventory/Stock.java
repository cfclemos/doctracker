package com.acme.inventory;

import java.util.HashMap;
import java.util.Map;

/** The quantity of each product in the warehouse. */
public class Stock implements Inventory {
    private final Map<String, Integer> quantities = new HashMap<>();

    /** Add units of a product. */
    public void add(String product, int units) {
        quantities.merge(product, units, Integer::sum);
    }

    /** Units of a product left; zero when it was never added. */
    @Override
    public int unitsOf(String product) {
        return quantities.getOrDefault(product, 0);
    }
}
