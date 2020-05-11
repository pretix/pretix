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
            'label': gettext('Current time'),
            'type': 'datetime',
        },
        'scans_number': {
            'label': gettext('Number of scans'),
            'type': 'int',
        },
        'scans_today': {
            'label': gettext('Number of scans since midnight'),
            'type': 'int',
        },
        'scans_days': {
            'label': gettext('Number of days with a scan'),
            'type': 'int',
        },
    };

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
            for (var i = 0; i < vm.value["objectList"].length; i++) {
                var option = new Option(vm.value["objectList"][i]["lookup"][2], vm.value["objectList"][i]["lookup"][1], true, true);
                $(vm.$el).append(option);
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
            + '<button type="button" class="checkin-rule-remove pull-right btn btn-xs btn-default" @click.prevent="remove" v-if="level > 0"><span class="fa fa-trash"></span></button> '
            + '<select v-bind:value="variable" v-on:input="setVariable" required class="form-control">'
            + '<option value="and">' + gettext('All of the conditions below (AND)') + '</option>'
            + '<option value="or">' + gettext('At least one of the conditions below (OR)') + '</option>'
            + '<option v-for="(v, name) in vars" :value="name">{{ v.label }}</option>'
            + '</select> '
            + '<select v-bind:value="operator" v-on:input="setOperator" required class="form-control" v-if="operator !== \'or\' && operator !== \'and\'">'
            + '<option></option>'
            + '<option v-for="(v, name) in operators" :value="name">{{ v.label }}</option>'
            + '</select> '
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
            + '<checkin-rule :rule="this.$root.rules" :level="0" :index="0"></checkin-rule>'
            + '</div>'
        ),
    });

    var app = new Vue({
        el: '#rules-editor',
        data: function () {
            return {
                rules: {},
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
