<?php
// The home page of the store.
require __DIR__ . '/../src/Product.php';

$product = new Acme\Store\Product('Book', 2000);
?>
<p class="price"><?= $product->priceWithTax(0.23) ?></p>
