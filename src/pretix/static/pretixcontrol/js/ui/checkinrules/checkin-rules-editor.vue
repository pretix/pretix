<template>
    <div class="checkin-rules-editor">
        <checkin-rule :rule="this.$root.rules" :level="0" :index="0" v-if="hasRules"></checkin-rule>
        <button type="button" class="checkin-rule-addchild btn btn-xs btn-default" v-if="!hasRules"
                @click.prevent="addRule"><span class="fa fa-plus-circle"></span> {{ this.$root.texts.condition_add }}
        </button>
    </div>
</template>
<script>
  export default {
    components: {
      CheckinRule: CheckinRule.default,
    },
    computed: {
      hasRules: function () {
        return !!Object.keys(this.$root.rules).length;
      }
    },
    methods: {
      addRule: function () {
        this.$set(this.$root.rules, "and", []);
      },
    },
  }
</script>
