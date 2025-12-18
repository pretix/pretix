/*global eventreverse */
(function() {
    'use strict';
    
    function loadWaitingListRank() {
        var rankResult = document.getElementById('rank-result');
        
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
                if (data.rank === 0) {
                    rankResult.textContent = rankResult.getAttribute('data-voucher-text') || 'You have a voucher waiting for redemption!';
                } else {
                    var rankLabel = rankResult.getAttribute('data-rank-label') || 'Your rank:';
                    rankResult.textContent = rankLabel + ' ' + data.rank;
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
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadWaitingListRank);
    } else {
        loadWaitingListRank();
    }
})();

