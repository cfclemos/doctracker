// The items a customer is buying.
export interface Item {
  name: string;
  price: number;
}

// The total of the cart, in cents.
export function cartTotal(items: Item[]): number {
  return items.reduce((sum, item) => sum + item.price, 0);
}
