// Package shipping prices the delivery of an order.
package shipping

// Cost is the price of a delivery, in cents, by weight in grams.
func Cost(grams int) int {
	return 500 + grams/100*20
}
