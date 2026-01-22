/*global $,gettext*/

$(function () {
    var runLotteryBtn = $('#run-lottery-btn');
    var itemSelect = $('select[name="item"]');
    var confirmModal = $('#lottery-confirm-modal');
    var productNameSpan = $('#lottery-product-name');
    var confirmBtn = $('#lottery-confirm-btn');
    var lotteryUrl = null;
    
    if (runLotteryBtn.length && itemSelect.length) {
        runLotteryBtn.on('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            
            var selectedItemId = itemSelect.val();
            var selectedItemText = itemSelect.find('option:selected').text();
            
            // Validate that a product is selected (not "All products")
            if (!selectedItemId || selectedItemId === '' || selectedItemId === null || selectedItemId === undefined) {
                alert(gettext('You must select a specific product to run the lottery. Please select a product from the dropdown and try again.'));
                return false;
            }
            
            // Build the lottery URL with the item parameter preserved
            var urlParams = new URLSearchParams(window.location.search);
            urlParams.set('lottery', 'run');
            urlParams.set('item', selectedItemId);
            
            // Preserve other filter parameters from the current URL
            var currentParams = new URLSearchParams(window.location.search);
            if (currentParams.has('status')) {
                urlParams.set('status', currentParams.get('status'));
            }
            if (currentParams.has('subevent')) {
                urlParams.set('subevent', currentParams.get('subevent'));
            }
            if (currentParams.has('email')) {
                urlParams.set('email', currentParams.get('email'));
            }
            if (currentParams.has('name')) {
                urlParams.set('name', currentParams.get('name'));
            }
            
            lotteryUrl = window.location.pathname + '?' + urlParams.toString();
            
            // Show confirmation modal
            productNameSpan.text(selectedItemText);
            confirmModal.modal('show');
            
            return false;
        });
    }
    
    if (confirmBtn.length) {
        confirmBtn.on('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            if (lotteryUrl) {
                // Close modal immediately
                confirmModal.modal('hide');
                
                // Remove modal backdrop if it exists
                $('.modal-backdrop').remove();
                $('body').removeClass('modal-open');
                $('body').css('padding-right', '');
                
                // Navigate to trigger download
                window.location.href = lotteryUrl;
            }
        });
    }
});

