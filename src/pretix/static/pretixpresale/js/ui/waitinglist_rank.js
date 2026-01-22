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
            // If products is present but not an array, forcibly make it an empty array.
            if (data.products !== undefined && !Array.isArray(data.products)) {
                data.products = [];
            }

            // Support for expired vouchers
            if (data.expired_voucher) {
                var expiredText = rankResult.getAttribute('data-expired-voucher-text') || 'You have an expired voucher.';
                var sentDateText = '';
                
                if (data.voucher_sent_date) {
                    try {
                        var sentDate = new Date(data.voucher_sent_date);
                        var dateOptions = { year: 'numeric', month: 'long', day: 'numeric' };
                        var formattedDate = sentDate.toLocaleDateString(undefined, dateOptions);
                        sentDateText = ' ' + (rankResult.getAttribute('data-sent-date-text') || 'It was sent on {date}.').replace('{date}', formattedDate);
                    } catch (e) {
                        // If date parsing fails, just show the expired message
                    }
                }
                
                rankResult.textContent = expiredText + sentDateText;

            } else if (data.products && Array.isArray(data.products)) {
                // Multiple product format
                if (data.products.length === 0) {
                    rankResult.textContent = rankResult.getAttribute('data-error-text') || 'Unable to determine your rank.';
                    return;
                }
                
                // Create table structure
                var table = document.createElement('table');
                table.className = 'table table-striped table-condensed';
                
                var thead = document.createElement('thead');
                var headerRow = document.createElement('tr');
                var headerProduct = document.createElement('th');
                headerProduct.textContent = 'Product';
                var headerRank = document.createElement('th');
                headerRank.textContent = 'Status';
                headerRow.appendChild(headerProduct);
                headerRow.appendChild(headerRank);
                thead.appendChild(headerRow);
                table.appendChild(thead);
                
                var tbody = document.createElement('tbody');
                var voucherText = rankResult.getAttribute('data-voucher-text') || 'You have a voucher waiting for redemption!';
                var rankLabel = rankResult.getAttribute('data-rank-label') || 'You are {ordinal} in line';
                
                data.products.forEach(function(product) {
                    var row = document.createElement('tr');
                    
                    // Product name cell
                    var productCell = document.createElement('td');
                    var productName = product.item_name;
                    if (product.variation_name) {
                        productName += ' – ' + product.variation_name;
                    }
                    productCell.textContent = productName;
                    row.appendChild(productCell);
                    
                    // Rank/Status cell
                    var rankCell = document.createElement('td');
                    if (product.rank === 0) {
                        rankCell.textContent = voucherText;
                        rankCell.className = 'text-success';
                    } else if (product.rank !== null && product.rank !== undefined) {
                        var ordinalRank = getOrdinalSuffix(product.rank);
                        rankCell.textContent = rankLabel.replace('{ordinal}', ordinalRank);
                    } else {
                        rankCell.textContent = rankResult.getAttribute('data-error-text') || 'Unable to determine rank.';
                        rankCell.className = 'text-muted';
                    }
                    row.appendChild(rankCell);
                    
                    tbody.appendChild(row);
                });
                
                table.appendChild(tbody);
                
                // Clear and add table
                rankResult.innerHTML = '';
                rankResult.appendChild(table);

            } else if (data.rank !== undefined) {
                // Single rank/legacy format
                if (data.rank === 0) {
                    rankResult.textContent = rankResult.getAttribute('data-voucher-text') || 'You have a voucher waiting for redemption!';
                } else {
                    var rankLabel2 = rankResult.getAttribute('data-rank-label') || 'You are {ordinal} in line';
                    var ordinalRank2 = getOrdinalSuffix(data.rank);
                    rankResult.textContent = rankLabel2.replace('{ordinal}', ordinalRank2);
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

