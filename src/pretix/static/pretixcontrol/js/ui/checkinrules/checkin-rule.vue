<template>
    <div v-bind:class="classObject">
        <div class="btn-group pull-right">
            <button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="duplicate"
                  v-if="level > 0" data-toggle="tooltip" :title="texts.duplicate">
              <span class="fa fa-copy"></span>
            </button>
            <button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="wrapWithOR">OR
            </button>
            <button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="wrapWithAND">AND
            </button>
            <button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="cutOut"
                    v-if="operands && operands.length == 1 && (operator === 'or' || operator == 'and')"><span
                    class="fa fa-cut"></span></button>
            <button type="button" class="checkin-rule-remove btn btn-xs btn-default" @click.prevent="remove"
                    v-if="level > 0"><span class="fa fa-trash"></span></button>
        </div>
        <select v-bind:value="variable" v-on:input="setVariable" required class="form-control">
            <option value="and">{{texts.and}}</option>
            <option value="or">{{texts.or}}</option>
            <option v-for="(v, name) in vars" :value="name">{{ v.label }}</option>
        </select>
        <select v-bind:value="operator" v-on:input="setOperator" required class="form-control"
                v-if="operator !== 'or' && operator !== 'and'">
            <option></option>
            <option v-for="(v, name) in operators" :value="name">{{ v.label }}</option>
        </select>
        <select v-bind:value="timeType" v-on:input="setTimeType" required class="form-control"
                v-if="vartype == 'datetime'">
            <option value="date_from">{{texts.date_from}}</option>
            <option value="date_to">{{texts.date_to}}</option>
            <option value="date_admission">{{texts.date_admission}}</option>
            <option value="custom">{{texts.date_custom}}</option>
            <option value="customtime">{{texts.date_customtime}}</option>
        </select>
        <datetimefield v-if="vartype == 'datetime' && timeType == 'custom'" :value="timeValue"
                       v-on:input="setTimeValue"></datetimefield>
        <timefield v-if="vartype == 'datetime' && timeType == 'customtime'" :value="timeValue"
            v-on:input="setTimeValue"></timefield>
        <input class="form-control" required type="number"
               v-if="vartype == 'datetime' && timeType && timeType != 'customtime' && timeType != 'custom'" v-bind:value="timeTolerance"
               v-on:input="setTimeTolerance" :placeholder="texts.date_tolerance">
        <input class="form-control" required type="number" v-if="vartype == 'int' && cardinality > 1"
               v-bind:value="rightoperand" v-on:input="setRightOperandNumber">
        <lookup-select2 required v-if="vartype == 'product' && operator == 'inList'" :multiple="true"
                        :value="rightoperand" v-on:input="setRightOperandProductList"
                        :url="productSelectURL"></lookup-select2>
        <lookup-select2 required v-if="vartype == 'variation' && operator == 'inList'" :multiple="true"
                        :value="rightoperand" v-on:input="setRightOperandVariationList"
                        :url="variationSelectURL"></lookup-select2>
        <div class="checkin-rule-childrules" v-if="operator === 'or' || operator === 'and'">
            <div v-for="(op, opi) in operands">
                <checkin-rule :rule="op" :index="opi" :level="level + 1" v-if="typeof op === 'object'"></checkin-rule>
            </div>
            <button type="button" class="checkin-rule-addchild btn btn-xs btn-default" @click.prevent="addOperand"><span
                    class="fa fa-plus-circle"></span> {{ texts.condition_add }}
            </button>
        </div>
    </div>
</template>
<script>
  export default {
    components: {
      LookupSelect2: LookupSelect2.default,
      Datetimefield: Datetimefield.default,
      Timefield: Timefield.default,
    },
    props: {
      rule: Object,
      level: Number,
      index: Number,
    },
    computed: {
      texts: function () {
        return this.$root.texts;
      },
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
        if (this.variable && this.$root.VARS[this.variable]) {
          return this.$root.VARS[this.variable]['type'];
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
        if (this.vartype && this.$root.TYPEOPS[this.vartype] && this.$root.TYPEOPS[this.vartype][this.operator]) {
          return this.$root.TYPEOPS[this.vartype][this.operator]['cardinality'];
        }
      },
      operators: function () {
        return this.$root.TYPEOPS[this.vartype];
      },
      productSelectURL: function () {
        return $("#product-select2").text();
      },
      variationSelectURL: function () {
        return $("#variations-select2").text();
      },
      vars: function () {
        return this.$root.VARS;
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
          if (current_val !== "and" && current_val !== "or" && current_val[0] && this.$root.VARS[event.target.value]['type'] === this.vartype) {
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
      duplicate: function () {
        var r = JSON.parse(JSON.stringify(this.rule));
        this.$parent.rule[this.$parent.operator].splice(this.index, 0, r);
      },
    }
  }
</script>
