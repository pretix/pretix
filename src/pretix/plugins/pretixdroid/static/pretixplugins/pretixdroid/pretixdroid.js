$(function () {
    jQuery('#qrcodeCanvas').qrcode(
        {
            text: '{{ qrdata|safe }}'
        }
    );
});
