<?php
namespace Acme\Store;

/** A product of the store. */
class Product
{
    public function __construct(private string $name, private int $price) {}

    /** The price with the tax, in cents. */
    public function priceWithTax(float $rate): int
    {
        return (int) round($this->price * (1 + $rate));
    }
}
