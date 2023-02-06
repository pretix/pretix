/*global $, Morris, gettext, formatPrice*/
$(function () {
    // Question view
    if (!$("#item_variations").length) {
        return;
    }

    function update_variation_summary($el) {
        var var_names = Object.fromEntries(
          $el
            .find("input[name*=-value_]")
            .filter(function () {
              return !!this.value;
            })
            .map(function () {
              return [[this.getAttribute("lang"), this.value]];
            })
            .get()
        );
        var var_name = i18nToString(var_names);
        var price = $el.find("input[name*=-default_price]").val();
        if (price) {
            var currency = $el.find("[name*=-default_price] + .input-group-addon").text();
            price = formatPrice(price, currency);
        }

        $el.find(".variation-name").text(var_name);
        $el.find(".variation-price").text(price);
        $el.find(".variation-timeframe").toggleClass("variation-icon-hidden", !(
            !!$el.find("input[name$=-available_from_0]").val() ||
            !!$el.find("input[name$=-available_until_0]").val()
        ));
        $el.find(".variation-name").toggleClass("variation-disabled", !(
            !!$el.find("input[name$=-active]").prop("checked")
        ));
        $el.find(".variation-voucher").toggleClass("variation-icon-hidden", !(
            !!$el.find("input[name$=-hide_without_voucher]").prop("checked")
        ));
        $el.find(".variation-membership").toggleClass("variation-icon-hidden", !(
            !!$el.find("input[name$=-require_membership]").prop("checked")
        ));
        $el.find(".variation-warning").toggleClass("hidden", !(
            $el.find(".alert-warning").length
        ));
        $el.find(".variation-error").toggleClass("hidden", !(
            $el.find(".alert-danger, .has-error").length
        ));
        $el.find("input[name$=-sales_channels]").each(function () {
            $el.find(".variation-channel-" + $(this).val()).toggleClass("variation-icon-hidden", !(
                $(this).prop("checked") && $("input[name=sales_channels][value=" + $(this).val() + "]").prop("checked")
            ));
        })
    }

    $("#item_variations [data-formset-form]").each(function () {
        var $el = $(this);
        update_variation_summary($el);
        $(this).on("change dp.change", "input", function () {update_variation_summary($el)});
    });
    $("input[name=sales_channels]").on("change", function() {
        $("#item_variations [data-formset-form]").each(function () {
            update_variation_summary($(this));
        });
    });
    $("#item_variations").on("formAdded", "details", function (event) {
        console.log("added", event.target)
        var $el = $(event.target);
        update_variation_summary($el);
        $(this).on("change dp.change", "input", function () {update_variation_summary($el)});
        setup_collapsible_details($("#item_variations"));
        form_handlers($(event.target));
    });
});
