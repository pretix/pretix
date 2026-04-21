function init_installment_filtering() {
    var installmentToggle = document.getElementById('pay_in_installments');
    if (!installmentToggle) {
        return;
    }

    var countGroup = document.getElementById('installments_count_group');
    var countSelect = document.getElementById('installments_count');
    var providerPanels = Array.prototype.slice.call(document.querySelectorAll('[data-payment-provider]'));

    var syncInstallmentMode = function () {
        var useInstallments = installmentToggle.checked;
        var firstVisibleRadio = null;
        var checkedVisibleRadio = null;

        countGroup.hidden = !useInstallments;
        countSelect.disabled = !useInstallments;

        providerPanels.forEach(function (panel) {
            var supportsInstallments = panel.getAttribute('data-installments-available') === 'true';
            var shouldShow = !useInstallments || supportsInstallments;
            var radio = panel.querySelector('input[name="payment"]');

            panel.hidden = !shouldShow;
            panel.style.display = shouldShow ? '' : 'none';

            if (shouldShow && radio && !firstVisibleRadio) {
                firstVisibleRadio = radio;
            }

            if (radio && radio.checked && shouldShow) {
                checkedVisibleRadio = radio;
            }

            if (radio && radio.checked && !shouldShow) {
                radio.checked = false;
            }
        });

        if (!checkedVisibleRadio && firstVisibleRadio) {
            firstVisibleRadio.checked = true;
        }
    };

    installmentToggle.addEventListener('change', syncInstallmentMode);
    syncInstallmentMode();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init_installment_filtering);
} else {
    init_installment_filtering();
}
