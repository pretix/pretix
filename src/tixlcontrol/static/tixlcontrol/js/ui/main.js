"use strict";
$(function () {
    $("[data-formset]").formset({
        animateForms: true,
        reorderMode: 'animate'
    });
    $('.collapse').collapse();
});
