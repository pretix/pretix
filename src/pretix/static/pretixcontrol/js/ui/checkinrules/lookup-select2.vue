<template>
    <select>
        <slot></slot>
    </select>
</template>
<script>
  export default {
    props: ["required", "value", "placeholder", "url", "multiple"],
    template: ('<select>\n' +
        '        <slot></slot>\n' +
        '      </select>'),
    mounted: function () {
      var vm = this;
      var multiple = this.multiple;
      $(this.$el)
          .select2(this.opts())
          .val(this.value || "")
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
  }
</script>
