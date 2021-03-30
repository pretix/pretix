<template>
    <input class="form-control" :required="required">
</template>
<script>
export default {
    props: ["required", "value"],
    mounted: function () {
        var vm = this;
        var multiple = this.multiple;
        $(this.$el)
                .datetimepicker(this.opts())
                .trigger("change")
                .on("dp.change", function (e) {
                    vm.$emit("input", $(this).data('DateTimePicker').date().toISOString());
                });
        if (!vm.value) {
            $(this.$el).data("DateTimePicker").viewDate(moment().hour(0).minute(0).second(0).millisecond(0));
        } else {
            $(this.$el).data("DateTimePicker").date(moment(vm.value));
        }
    },
    methods: {
        opts: function () {
            return {
                format: $("body").attr("data-datetimeformat"),
                locale: $("body").attr("data-datetimelocale"),
                timeZone: $("body").attr("data-timezone"),
                useCurrent: false,
                showClear: this.required,
                icons: {
                    time: 'fa fa-clock-o',
                    date: 'fa fa-calendar',
                    up: 'fa fa-chevron-up',
                    down: 'fa fa-chevron-down',
                    previous: 'fa fa-chevron-left',
                    next: 'fa fa-chevron-right',
                    today: 'fa fa-screenshot',
                    clear: 'fa fa-trash',
                    close: 'fa fa-remove'
                }
            };
        }
    },
    watch: {
        value: function (val) {
            $(this.$el).data('DateTimePicker').date(moment(val));
        },
    },
    destroyed: function () {
        $(this.$el)
                .off()
                .datetimepicker("destroy");
    }
}
</script>