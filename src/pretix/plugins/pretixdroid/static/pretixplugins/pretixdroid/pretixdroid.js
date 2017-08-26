$(function () {
    jQuery('#qrcodeCanvas').qrcode(
        {
            text: $("#qrdata").html()
        }
    );
});
