$(document).ready(function () {
    var TYPEOPS = {
        'product': {
            'inList': {
                'label': gettext('is one of'),
                'cardinality': 2,
            }
        },
        'variation': {
            'inList': {
                'label': gettext('is one of'),
                'cardinality': 2,
            }
        },
        'datetime': {
            'isBefore': {
                'label': gettext('is before'),
                'cardinality': 2,
            },
            'isAfter': {
                'label': gettext('is after'),
                'cardinality': 2,
            },
        },
        'int': {
            '<': {
                'label': '<',
                'cardinality': 2,
            },
            '<=': {
                'label': '≤',
                'cardinality': 2,
            },
            '>': {
                'label': '>',
                'cardinality': 2,
            },
            '>=': {
                'label': '≥',
                'cardinality': 2,
            },
            '==': {
                'label': '=',
                'cardinality': 2,
            },
            '!=': {
                'label': '≠',
                'cardinality': 2,
            },
        },
    };
    var VARS = {
        'product': {
            'label': gettext('Product'),
            'type': 'product',
        },
        'variation': {
            'label': gettext('Product variation'),
            'type': 'variation',
        },
        'now': {
            'label': gettext('Current date and time'),
            'type': 'datetime',
        },
        'entries_number': {
            'label': gettext('Number of previous entries'),
            'type': 'int',
        },
        'entries_today': {
            'label': gettext('Number of previous entries since midnight'),
            'type': 'int',
        },
        'entries_days': {
            'label': gettext('Number of days with a previous entry'),
            'type': 'int',
        },
    };

    Vue.component("datetimefield", {
        props: ["required", "value"],
        template: ('<input class="form-control">'),
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
    });

    Vue.component("lookup-select2", {
        props: ["required", "value", "placeholder", "url", "multiple"],
        template: ('<select>\n' +
            '        <slot></slot>\n' +
            '      </select>'),
        mounted: function () {
            var vm = this;
            var multiple = this.multiple;
            $(this.$el)
                .select2(this.opts())
                .val(this.value)
                .trigger("change")
                // emit event on change.
                .on("change", function (e) {
                    vm.$emit("input", $(this).select2('data'));
                });
            if (vm.value) {
                for (var i = 0; i < vm.value["objectList"].length; i++) {
                    var option = new Option(vm.value["objectList"][i]["lookup"][2], vm.value["objectList"][i]["lookup"][1], true, true);
                    $(vm.$el).append(option);
                }
            }
            $(vm.$el).trigger("change");
        },
        methods: {
            opts: function () {
                return {
                    theme: "bootstrap",
                    delay: 100,
                    width: '100%',
                    multiple: true,
                    allowClear: this.required,
                    language: $("body").attr("data-select2-locale"),
                    ajax: {
                        url: this.url,
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
                        return $ret;
                    },
                };
            }
        },
        watch: {
            placeholder: function (val) {
                $(this.$el).empty().select2(this.opts());
                this.build();
            },
            required: function (val) {
                $(this.$el).empty().select2(this.opts());
                this.build();
            },
            url: function (val) {
                $(this.$el).empty().select2(this.opts());
                this.build();
            },
        },
        destroyed: function () {
            $(this.$el)
                .off()
                .select2("destroy");
        }
    });

    Vue.component('checkin-rule', {
        template: ('<div v-bind:class="classObject">'
            + '<div class="btn-group pull-right">'
            + '<button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="wrapWithOR">OR</button>'
            + '<button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="wrapWithAND">AND</button> '
            + '<button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="cutOut" v-if="operands && operands.length == 1 && (operator === \'or\' || operator == \'and\')"><span class="fa fa-cut"></span></button>'
            + '<button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="remove" v-if="level > 0"><span class="fa fa-trash"></span></button>'
            + '</div>'
            + '<select v-bind:value="variable" v-on:input="setVariable" required class="form-control">'
            + '<option value="and">' + gettext('All of the conditions below (AND)') + '</option>'
            + '<option value="or">' + gettext('At least one of the conditions below (OR)') + '</option>'
            + '<option v-for="(v, name) in vars" :value="name">{{ v.label }}</option>'
            + '</select> '
            + '<select v-bind:value="operator" v-on:input="setOperator" required class="form-control" v-if="operator !== \'or\' && operator !== \'and\'">'
            + '<option></option>'
            + '<option v-for="(v, name) in operators" :value="name">{{ v.label }}</option>'
            + '</select> '
            + '<select v-bind:value="timeType" v-on:input="setTimeType" required class="form-control" v-if="vartype == \'datetime\'">'
            + '<option value="date_from">' + gettext('Event start') + '</option>'
            + '<option value="date_to">' + gettext('Event end') + '</option>'
            + '<option value="date_admission">' + gettext('Event admission') + '</option>'
            + '<option value="custom">' + gettext('custom time') + '</option>'
            + '</select> '
            + '<datetimefield v-if="vartype == \'datetime\' && timeType == \'custom\'" :value="timeValue" v-on:input="setTimeValue"></datetimefield>'
            + '<input class="form-control" required type="number" v-if="vartype == \'datetime\' && timeType && timeType != \'custom\'" v-bind:value="timeTolerance" v-on:input="setTimeTolerance" placeholder="' + gettext('Tolerance (minutes)') + '">'
            + '<input class="form-control" required type="number" v-if="vartype == \'int\' && cardinality > 1" v-bind:value="rightoperand" v-on:input="setRightOperandNumber">'
            + '<lookup-select2 required v-if="vartype == \'product\' && operator == \'inList\'" :multiple="true" :value="rightoperand" v-on:input="setRightOperandProductList" :url="productSelectURL"></lookup-select2>'
            + '<lookup-select2 required v-if="vartype == \'variation\' && operator == \'inList\'" :multiple="true" :value="rightoperand" v-on:input="setRightOperandVariationList" :url="variationSelectURL"></lookup-select2>'
            + '<div class="checkin-rule-childrules" v-if="operator === \'or\' || operator === \'and\'">'
            + '<div v-for="(op, opi) in operands">'
            + '<checkin-rule :rule="op" :index="opi" :level="level + 1" v-if="typeof op === \'object\'"></checkin-rule>'
            + '</div>'
            + '<button type="button" class="checkin-rule-addchild btn btn-xs btn-default" @click.prevent="addOperand"><span class="fa fa-plus-circle"></span> ' + gettext('Add condition') + '</button>'
            + '</div>'
            + '</div>'
        ),
        computed: {
            variable: function () {
                var op = this.operator;
                if (op === "and" || op === "or") {
                    return op;
                } else if (this.rule[op] && this.rule[op][0]) {
                    return this.rule[op][0]["var"];
                } else {
                    return null;
                }
            },
            rightoperand: function () {
                var op = this.operator;
                if (op === "and" || op === "or") {
                    return null;
                } else if (this.rule[op] && typeof this.rule[op][1] !== "undefined") {
                    return this.rule[op][1];
                } else {
                    return null;
                }
            },
            operator: function () {
                return Object.keys(this.rule)[0];
            },
            operands: function () {
                return this.rule[this.operator];
            },
            classObject: function () {
                var c = {
                    'checkin-rule': true
                };
                c['checkin-rule-' + this.variable] = true;
                return c;
            },
            vartype: function () {
                if (this.variable && VARS[this.variable]) {
                    return VARS[this.variable]['type'];
                }
            },
            timeType: function () {
                if (this.rightoperand && this.rightoperand['buildTime']) {
                    return this.rightoperand['buildTime'][0];
                }
            },
            timeTolerance: function () {
                var op = this.operator;
                if ((op === "isBefore" || op === "isAfter") && this.rule[op] && typeof this.rule[op][2] !== "undefined") {
                    return this.rule[op][2];
                } else {
                    return null;
                }
            },
            timeValue: function () {
                if (this.rightoperand && this.rightoperand['buildTime']) {
                    return this.rightoperand['buildTime'][1];
                }
            },
            cardinality: function () {
                if (this.vartype && TYPEOPS[this.vartype] && TYPEOPS[this.vartype][this.operator]) {
                    return TYPEOPS[this.vartype][this.operator]['cardinality'];
                }
            },
            operators: function () {
                return TYPEOPS[this.vartype];
            },
            productSelectURL: function () {
                return $("#product-select2").text();
            },
            variationSelectURL: function () {
                return $("#variations-select2").text();
            },
            vars: function () {
                return VARS;
            },
        },
        methods: {
            setVariable: function (event) {
                var current_op = Object.keys(this.rule)[0];
                var current_val = this.rule[current_op];

                if (event.target.value === "and" || event.target.value === "or") {
                    if (current_val[0] && current_val[0]["var"]) {
                        current_val = [];
                    }
                    this.$set(this.rule, event.target.value, current_val);
                    this.$delete(this.rule, current_op);
                } else {
                    if (current_val !== "and" && current_val !== "or" && current_val[0] && VARS[event.target.value]['type'] === this.vartype) {
                        this.$set(this.rule[current_op][0], "var", event.target.value);
                    } else {
                        this.$delete(this.rule, current_op);
                        this.$set(this.rule, "!!", [{"var": event.target.value}]);
                    }
                }
            },
            setOperator: function (event) {
                var current_op = Object.keys(this.rule)[0];
                var current_val = this.rule[current_op];
                this.$delete(this.rule, current_op);
                this.$set(this.rule, event.target.value, current_val);
            },
            setRightOperandNumber: function (event) {
                if (this.rule[this.operator].length === 1) {
                    this.rule[this.operator].push(parseInt(event.target.value));
                } else {
                    this.$set(this.rule[this.operator], 1, parseInt(event.target.value));
                }
            },
            setTimeTolerance: function (event) {
                if (this.rule[this.operator].length === 2) {
                    this.rule[this.operator].push(parseInt(event.target.value));
                } else {
                    this.$set(this.rule[this.operator], 2, parseInt(event.target.value));
                }
            },
            setTimeType: function (event) {
                var time = {
                    "buildTime": [event.target.value]
                };
                if (this.rule[this.operator].length === 1) {
                    this.rule[this.operator].push(time);
                } else {
                    this.$set(this.rule[this.operator], 1, time);
                }
                if (event.target.value === "custom") {
                    this.$set(this.rule[this.operator], 2, 0);
                }
            },
            setTimeValue: function (val) {
                console.log(val);
                this.$set(this.rule[this.operator][1]["buildTime"], 1, val);
            },
            setRightOperandProductList: function (val) {
                var products = {
                    "objectList": []
                };
                for (var i = 0; i < val.length; i++) {
                    products["objectList"].push({
                        "lookup": [
                            "product",
                            val[i].id,
                            val[i].text
                        ]
                    });
                }
                if (this.rule[this.operator].length === 1) {
                    this.rule[this.operator].push(products);
                } else {
                    this.$set(this.rule[this.operator], 1, products);
                }
            },
            setRightOperandVariationList: function (val) {
                var products = {
                    "objectList": []
                };
                for (var i = 0; i < val.length; i++) {
                    products["objectList"].push({
                        "lookup": [
                            "variation",
                            val[i].id,
                            val[i].text
                        ]
                    });
                }
                if (this.rule[this.operator].length === 1) {
                    this.rule[this.operator].push(products);
                } else {
                    this.$set(this.rule[this.operator], 1, products);
                }
            },
            addOperand: function () {
                this.rule[this.operator].push({"": []});
            },
            wrapWithOR: function () {
                var r = JSON.parse(JSON.stringify(this.rule));
                this.$delete(this.rule, this.operator);
                this.$set(this.rule, "or", [r]);
            },
            wrapWithAND: function () {
                var r = JSON.parse(JSON.stringify(this.rule));
                this.$delete(this.rule, this.operator);
                this.$set(this.rule, "and", [r]);
            },
            cutOut: function () {
                var cop = Object.keys(this.operands[0])[0];
                var r = this.operands[0][cop];
                this.$delete(this.rule, this.operator);
                this.$set(this.rule, cop, r);
            },
            remove: function () {
                this.$parent.rule[this.$parent.operator].splice(this.index, 1);
            },
        },
        props: {
            rule: Object,
            level: Number,
            index: Number,
        }
    });

    Vue.component('checkin-rules-editor', {
        template: ('<div class="checkin-rules-editor">'
            + '<checkin-rule :rule="this.$root.rules" :level="0" :index="0" v-if="hasRules"></checkin-rule>'
            + '<button type="button" class="checkin-rule-addchild btn btn-xs btn-default" v-if="!hasRules" @click.prevent="addRule"><span class="fa fa-plus-circle"></span> ' + gettext('Add condition') + '</button>'
            + '</div>'
        ),
        computed: {
            hasRules: function () {
                return hasRules = !!Object.keys(this.$root.rules).length;
            }
        },
        methods: {
            addRule: function () {
                this.$set(this.$root.rules, "and", []);
            },
        },
    });

    var app = new Vue({
        el: '#rules-editor',
        data: function () {
            return {
                rules: {},
                hasRules: false,
            };
        },
        created: function () {
            this.rules = JSON.parse($("#id_rules").val());
        },
        watch: {
            rules: {
                deep: true,
                handler: function (newval) {
                    $("#id_rules").val(JSON.stringify(newval));
                }
            },
        }
    })
});
