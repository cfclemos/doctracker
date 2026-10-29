//! Exchange rates between currencies.

/// Convert an amount with a rate, rounding to the cent.
pub fn convert(amount: f64, rate: f64) -> f64 {
    (amount * rate * 100.0).round() / 100.0
}
