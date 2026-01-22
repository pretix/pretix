/*global $,gettext*/

$(function () {
    var runLotteryBtn = $('#run-lottery-btn');
    var revertListBtn = $('#revert-list-btn');
    var itemSelect = $('select[name="item"]');
    var confirmModal = $('#lottery-confirm-modal');
    var modalTitle = $('#lottery-modal-title');
    var modalDescription = $('#lottery-modal-description');
    var productContainer = $('#lottery-product-container');
    var productNameSpan = $('#lottery-product-name');
    var modalWarning = $('#lottery-modal-warning');
    var confirmBtn = $('#lottery-confirm-btn');
    var actionUrl = null;
    
    function buildUrlParams(action) {
        var urlParams = new URLSearchParams(window.location.search);
        urlParams.set('lottery', action);
        
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
        
        return urlParams;
    }
    
    function showConfirmationModal(config) {
        modalTitle.text(config.title);
        modalDescription.text(config.description);
        modalWarning.text(config.warning);
        confirmBtn.text(config.confirmButtonText);
        
        if (config.showProduct) {
            productContainer.show();
            productNameSpan.text(config.productName);
        } else {
            productContainer.hide();
        }
        
        confirmModal.modal('show');
    }
    
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
            var urlParams = buildUrlParams('run');
            urlParams.set('item', selectedItemId);
            
            actionUrl = window.location.pathname + '?' + urlParams.toString();
            
            // Show confirmation modal
            showConfirmationModal({
                title: gettext('Confirm Lottery Run'),
                description: gettext('You are about to run the lottery for the following product:'),
                productName: selectedItemText,
                showProduct: true,
                warning: gettext('This action will shuffle the waiting list priorities for this product. This cannot be easily undone.'),
                confirmButtonText: gettext('Yes, run the lottery')
            });
            
            return false;
        });
    }
    
    if (revertListBtn.length && itemSelect.length) {
        revertListBtn.on('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            
            var selectedItemId = itemSelect.val();
            var selectedItemText = itemSelect.find('option:selected').text();
            
            // Validate that a product is selected (not "All products")
            if (!selectedItemId || selectedItemId === '' || selectedItemId === null || selectedItemId === undefined) {
                alert(gettext('You must select a specific product to revert the list. Please select a product from the dropdown and try again.'));
                return false;
            }
            
            // Build the revert URL with the item parameter preserved
            var urlParams = buildUrlParams('revert');
            urlParams.set('item', selectedItemId);
            
            actionUrl = window.location.pathname + '?' + urlParams.toString();
            
            // Show confirmation modal
            showConfirmationModal({
                title: gettext('Confirm List Reversion'),
                description: gettext('You are about to revert the waiting list priorities for the following product:'),
                productName: selectedItemText,
                showProduct: true,
                warning: gettext('This action will restore the waiting list priorities to their original order. This cannot be easily undone.'),
                confirmButtonText: gettext('Yes, revert the list')
            });
            
            return false;
        });
    }
    
    if (confirmBtn.length) {
        confirmBtn.on('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            if (actionUrl) {
                // Close modal immediately
                confirmModal.modal('hide');
                
                // Remove modal backdrop if it exists
                $('.modal-backdrop').remove();
                $('body').removeClass('modal-open');
                $('body').css('padding-right', '');
                
                // Navigate to trigger action
                window.location.href = actionUrl;
            }
        });
    }
});

