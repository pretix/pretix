/*global eventreverse */
(function() {
    'use strict';
    
    function getOrdinalSuffix(num) {
        var j = num % 10;
        var k = num % 100;
        if (j === 1 && k !== 11) {
            return num + 'st';
        }
        if (j === 2 && k !== 12) {
            return num + 'nd';
        }
        if (j === 3 && k !== 13) {
            return num + 'rd';
        }
        return num + 'th';
    }
    
    function initFillVoucherButton() {
        var fillBtn = document.getElementById('fill-voucher-btn');
        if (!fillBtn) {
            return;
        }
        
        fillBtn.addEventListener('click', function() {
            var voucherInput = document.getElementById('voucher');
            if (voucherInput) {
                voucherInput.value = this.getAttribute('data-voucher-code');
                voucherInput.focus();
                // Scroll to voucher form if needed
                var voucherForm = voucherInput.closest('form');
                if (voucherForm) {
                    voucherForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            } else {
                // Voucher form not found - show error message
                var rankResult = document.getElementById('rank-result');
                if (rankResult) {
                    rankResult.textContent = rankResult.getAttribute('data-error-text') || 'Voucher form not found.';
                    fillBtn.classList.add('hidden');
                }
            }
        });
    }
    
    function loadWaitingListRank() {
        var rankResult = document.getElementById('rank-result');
        var fillBtn = document.getElementById('fill-voucher-btn');
        if (fillBtn) {
            fillBtn.classList.add('hidden');
        }
        
        if (!rankResult) {
            return;
        }
        
        var rankUrl = rankResult.getAttribute('data-rank-url');
        if (!rankUrl) {
            rankResult.textContent = 'Error: Rank URL not configured.';
            return;
        }
        
        fetch(rankUrl, {
            method: 'GET',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {  
            if (data.rank !== undefined) {
                if (data.rank === 0 && data.voucher_code && fillBtn) {
                    // User has a voucher - show button alongside rank result
                    rankResult.textContent = rankResult.getAttribute('data-voucher-text') || 'You have a voucher waiting for redemption!';
                    fillBtn.setAttribute('data-voucher-code', data.voucher_code);
                    fillBtn.classList.remove('hidden');
                } else {                                      
                    if (data.rank === 0) {
                        rankResult.textContent = rankResult.getAttribute('data-voucher-text') || 'You have a voucher waiting for redemption!';
                    } else {
                        var rankLabel = rankResult.getAttribute('data-rank-label') || 'You are {ordinal} in line';
                        var ordinalRank = getOrdinalSuffix(data.rank);
                        rankResult.textContent = rankLabel.replace('{ordinal}', ordinalRank);
                    }
                }
            } else if (data.error) {
                rankResult.textContent = data.error;
            } else {
                rankResult.textContent = rankResult.getAttribute('data-error-text') || 'Unable to determine your rank.';
            }
        })
        .catch(function(error) {
            rankResult.textContent = rankResult.getAttribute('data-error-text') || 'An error occurred. Please try again.';
        });
    }
    
    function init() {
        initFillVoucherButton();
        loadWaitingListRank();
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

