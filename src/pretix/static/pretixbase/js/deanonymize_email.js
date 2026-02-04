document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('a[href^="mailto:"]').forEach(function(link) {
        // Replace [at] with @ and the [dot] with . in both the href and the displayed text (if needed)
        link.href = link.href.replace('[at]', '@').replace('[dot]', '.');
        link.textContent = link.textContent.replace('[at]', '@').replace('[dot]', '.');
    });
});
