/*global $, gettext*/
$(function () {
    // Question view
    if (!$(".form-order-change").length) {
        return;
    }
    $(".form-order-change").each(function () {
        var url = $(this).attr("data-pricecalc-endpoint");
        var $itemvar = $(this).find("[name*=itemvar]");
        var $subevent = $(this).find("[name*=subevent]");
        var $price = $(this).find("[name*=price]");
        var update_price = function () {
            console.log(url);
            var itemvar = $itemvar.val();
            var item = null;
            var variation = null;
            if (itemvar.indexOf("-")) {
                item = parseInt(itemvar.split("-")[0]);
                variation = parseInt(itemvar.split("-")[1]);
            } else {
                item = parseInt(itemvar);
            }
            $price.closest(".field-container").append("<small class=\"loading-indicator\"><span class=\"fa fa-cog fa-spin\"></span> " +
                gettext("Calculating default price…") + "</small>");
            $.ajax(
                {
                    'type': 'POST',
                    'url': url,
                    'headers': {'X-CSRFToken': $("input[name=csrfmiddlewaretoken]").val()},
                    'data': JSON.stringify({
                        'item': item,
                        'variation': variation,
                        'subevent': $subevent.val(),
                        'locale': $("body").attr("data-pretixlocale"),
                    }),
                    'contentType': "application/json",
                    'success': function (data) {
                        $price.val(data.gross_formatted);
                        $price.closest(".field-container").find(".loading-indicator").remove();
                    },
                    // 'error': …
                    'context': this,
                    'dataType': 'json',
                    'timeout': 30000
                }
            );
        };
        $itemvar.on("change", update_price);
        $subevent.on("change", update_price);
    });
    el.find('[data-model-select2=seat]').each(function () {
        var $s = $(this);
        $s.select2({
            theme: "bootstrap",
            delay: 100,
            allowClear: !$s.prop("required"),
            width: '100%',
            language: $("body").attr("data-select2-locale"),
            placeholder: $(this).attr("data-placeholder"),
            ajax: {
                url: $(this).attr('data-select2-url'),
                data: function (params) {
                    return {
                        query: params.term,
                        page: params.page || 1
                    }
                }
            },
            templateResult: function (res) {
                if (!res.id) {
                    return res.text;
                }
                var $ret = $("<span>").append(
                    $("<span>").addClass("primary").append($("<div>").text(res.text).html())
                );
                if (res.event) {
                    $ret.append(
                        $("<span>").addClass("secondary").append(
                            $("<span>").addClass("fa fa-calendar fa-fw")
                        ).append(" ").append($("<div>").text(res.event).html())
                    );
                }
                return $ret;
            },
        }).on("select2:select", function () {
            // Allow continuing to select
            if ($s.hasAttribute("multiple")) {
                window.setTimeout(function () {
                    $s.parent().find('.select2-search__field').focus();
                }, 50);
            }
        });
    });
});
