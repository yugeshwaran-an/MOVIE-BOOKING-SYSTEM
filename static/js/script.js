/**
 * Movie Ticket Booking System - Client-side dynamic pricing and validation
 */

document.addEventListener('DOMContentLoaded', function () {
  const quantityInput = document.getElementById('booking-quantity');
  const rateInput = document.getElementById('show-rate');
  const baseAmountDisplay = document.getElementById('display-base-amount');
  const bookingChargeDisplay = document.getElementById('display-booking-charge');
  const grandTotalDisplay = document.getElementById('display-grand-total');

  function updatePricing() {
    if (!quantityInput || !rateInput) return;

    const rate = parseFloat(rateInput.value) || 0;
    let qty = parseInt(quantityInput.value, 10);

    if (isNaN(qty) || qty < 1) {
      qty = 1;
    } else if (qty > 5) {
      qty = 5;
    }

    const baseAmount = rate * qty;
    // BR4: IF base_total < Rs.1000 -> booking_charge = Rs.50, ELSE Rs.0
    const bookingCharge = baseAmount < 1000 ? 50 : 0;
    const grandTotal = baseAmount + bookingCharge;

    if (baseAmountDisplay) {
      baseAmountDisplay.textContent = 'Rs. ' + baseAmount.toFixed(2);
    }
    if (bookingChargeDisplay) {
      bookingChargeDisplay.textContent = 'Rs. ' + bookingCharge.toFixed(2);
    }
    if (grandTotalDisplay) {
      grandTotalDisplay.textContent = 'Rs. ' + grandTotal.toFixed(2);
    }
  }

  if (quantityInput) {
    quantityInput.addEventListener('input', updatePricing);
    quantityInput.addEventListener('change', updatePricing);
    // Initial calculation
    updatePricing();
  }

  // Auto-dismiss alerts after 5 seconds if desired
  const alerts = document.querySelectorAll('.alert');
  if (alerts.length > 0) {
    setTimeout(() => {
      alerts.forEach(alert => {
        alert.style.transition = 'opacity 0.5s ease';
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 500);
      });
    }, 6000);
  }
});
