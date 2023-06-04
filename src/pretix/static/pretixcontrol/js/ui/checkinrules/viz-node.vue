<template>
    <g>
        <path v-for="e in edges" :d="e" class="edge"></path>
        <path v-if="rootEdge" :d="rootEdge" class="edge"></path>
        <path v-if="!node.children.length" :d="checkEdge" class="edge"></path>
        <rect :width="boxWidth" :height="boxHeight" :x="x" :y="y" :class="nodeClass" rx="5">
        </rect>

        <foreignObject :width="boxWidth - 10" :height="boxHeight - 10" :x="x + 5" :y="y + 5">
            <div xmlns="http://www.w3.org/1999/xhtml" class="text">
                <span v-if="vardata && vardata.type === 'int'">
                    <span v-if="variable.startsWith('entries_')" class="fa fa-sign-in"></span>
                    {{ vardata.label }}
                    <br>
                    <span v-if="varresult !== null">
                      {{varresult}}
                    </span>
                    <strong>
                      {{ op.label }} {{ rightoperand }}
                    </strong>
                </span>
                <span v-else-if="vardata && variable === 'now'">
                    <span class="fa fa-clock-o"></span> {{ vardata.label }}<br>
                    <span v-if="varresult !== null">
                      {{varresult}}
                    </span>
                    <strong>
                        {{ op.label }}<br>
                        <span v-if="rightoperand.buildTime[0] === 'custom'">
                            {{ df(rightoperand.buildTime[1]) }}
                        </span>
                        <span v-else-if="rightoperand.buildTime[0] === 'customtime'">
                            {{ tf(rightoperand.buildTime[1]) }}
                        </span>
                        <span v-else>
                            {{ this.$root.texts[rightoperand.buildTime[0]] }}
                        </span>
                        <span v-if="operands[2]">
                            <span v-if="operator === 'isBefore'">+</span>
                            <span v-else>-</span>
                            {{ operands[2] }}
                            {{ this.$root.texts.minutes }}
                        </span>
                    </strong>
                </span>
                <span v-else-if="vardata && operator === 'inList'">
                    <span class="fa fa-ticket"></span> {{ vardata.label }}
                    <span v-if="varresult !== null">
                      ({{varresult}})
                    </span>
                    <br>
                    <strong>
                        {{ rightoperand.objectList.map((o) => o.lookup[2]).join(", ") }}
                    </strong>
                </span>
            </div>
        </foreignObject>

        <g v-if="result === false" :transform="`translate(${x + boxWidth - 15}, ${y - 10})`">
          <ellipse fill="#fff" cx="14.685823" cy="14.318233" rx="12.140151" ry="11.55523" />
          <path d="M 15,0 C 23.28125,0 30,6.71875 30,15 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 Z m 2.5,24.35547 V 20.64453 C 17.5,20.29297 17.22656,20 16.89453,20 h -3.75 C 12.79297,20 12.5,20.29297 12.5,20.64453 v 3.71094 C 12.5,24.70703 12.79297,25 13.14453,25 h 3.75 C 17.22656,25 17.5,24.70703 17.5,24.35547 Z M 17.4609,17.63672 17.81246,5.50781 c 0,-0.13672 -0.0586,-0.27343 -0.19531,-0.35156 C 17.49996,5.05855 17.32418,5 17.1484,5 h -4.29688 c -0.17578,0 -0.35156,0.0586 -0.46875,0.15625 -0.13672,0.0781 -0.19531,0.21484 -0.19531,0.35156 l 0.33203,12.12891 c 0,0.27344 0.29297,0.48828 0.66406,0.48828 h 3.61329 c 0.35156,0 0.64453,-0.21484 0.66406,-0.48828 z"
                class="error" />
        </g>
        <g v-if="result === true" :transform="`translate(${x + boxWidth - 15}, ${y - 10})`">
          <ellipse fill="#fff" cx="14.685823" cy="14.318233" rx="12.140151" ry="11.55523" />
          <path d="m 25.078125,11.835938 c 0,-0.332032 -0.117188,-0.664063 -0.351563,-0.898438 L 22.949219,9.1796875 c -0.234375,-0.234375 -0.546875,-0.3710937 -0.878907,-0.3710937 -0.332031,0 -0.644531,0.1367187 -0.878906,0.3710937 L 13.222656,17.128906 8.8085938,12.714844 C 8.5742188,12.480469 8.2617188,12.34375 7.9296875,12.34375 c -0.3320313,0 -0.6445313,0.136719 -0.8789063,0.371094 l -1.7773437,1.757812 c -0.234375,0.234375 -0.3515625,0.566407 -0.3515625,0.898438 0,0.332031 0.1171875,0.644531 0.3515625,0.878906 l 7.0703125,7.070312 c 0.234375,0.234375 0.566406,0.371094 0.878906,0.371094 0.332032,0 0.664063,-0.136719 0.898438,-0.371094 L 24.726562,12.714844 c 0.234375,-0.234375 0.351563,-0.546875 0.351563,-0.878906 z M 30,15 C 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 23.28125,0 30,6.71875 30,15 Z"
                class="check"/>
        </g>
        <g v-if="!node.children.length && (resultInclParents === null || resultInclParents === true)" :transform="`translate(${x + boxWidth + 25}, ${y + boxHeight/2 - 15})`">
          <path d="m 25.078125,11.835938 c 0,-0.332032 -0.117188,-0.664063 -0.351563,-0.898438 L 22.949219,9.1796875 c -0.234375,-0.234375 -0.546875,-0.3710937 -0.878907,-0.3710937 -0.332031,0 -0.644531,0.1367187 -0.878906,0.3710937 L 13.222656,17.128906 8.8085938,12.714844 C 8.5742188,12.480469 8.2617188,12.34375 7.9296875,12.34375 c -0.3320313,0 -0.6445313,0.136719 -0.8789063,0.371094 l -1.7773437,1.757812 c -0.234375,0.234375 -0.3515625,0.566407 -0.3515625,0.898438 0,0.332031 0.1171875,0.644531 0.3515625,0.878906 l 7.0703125,7.070312 c 0.234375,0.234375 0.566406,0.371094 0.878906,0.371094 0.332032,0 0.664063,-0.136719 0.898438,-0.371094 L 24.726562,12.714844 c 0.234375,-0.234375 0.351563,-0.546875 0.351563,-0.878906 z M 30,15 C 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 23.28125,0 30,6.71875 30,15 Z"
                class="check"/>
        </g>
        <g v-if="!node.children.length && (resultInclParents === false)" :transform="`translate(${x + boxWidth + 25}, ${y + boxHeight/2 - 15})`">
          <path d="M 15,0 C 23.28125,0 30,6.71875 30,15 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 Z m 2.5,24.35547 V 20.64453 C 17.5,20.29297 17.22656,20 16.89453,20 h -3.75 C 12.79297,20 12.5,20.29297 12.5,20.64453 v 3.71094 C 12.5,24.70703 12.79297,25 13.14453,25 h 3.75 C 17.22656,25 17.5,24.70703 17.5,24.35547 Z M 17.4609,17.63672 17.81246,5.50781 c 0,-0.13672 -0.0586,-0.27343 -0.19531,-0.35156 C 17.49996,5.05855 17.32418,5 17.1484,5 h -4.29688 c -0.17578,0 -0.35156,0.0586 -0.46875,0.15625 -0.13672,0.0781 -0.19531,0.21484 -0.19531,0.35156 l 0.33203,12.12891 c 0,0.27344 0.29297,0.48828 0.66406,0.48828 h 3.61329 c 0.35156,0 0.64453,-0.21484 0.66406,-0.48828 z"
                class="error" />
        </g>
    </g>
</template>
<script>
  export default {

    props: {
      node: Object,
      nodeid: String,
      children: Array,
      boxWidth: Number,
      boxHeight: Number,
      marginX: Number,
      marginY: Number,
      paddingX: Number,
    },
    computed: {
      x() {
        return this.node.column * (this.boxWidth + this.marginX) + this.marginX / 2 + this.paddingX
      },
      y() {
        return this.node.y * (this.boxHeight + this.marginY) + this.marginY / 2
      },
      edges() {
        const startX = this.x + this.boxWidth + 1
        const startY = this.y + this.boxHeight / 2
        return this.children.map((c) => {
          const endX = (c.column * (this.boxWidth + this.marginX) + this.marginX / 2 + this.paddingX) - 1
          const endY = (c.y * (this.boxHeight + this.marginY) + this.marginY / 2) + this.boxHeight / 2

          return `
            M ${startX} ${startY}
            L ${endX - 50} ${startY}
            C ${endX - 25} ${startY} ${endX - 25} ${startY} ${endX - 25} ${startY + 25 * Math.sign(endY - startY)}
            L ${endX - 25} ${endY - 25 * Math.sign(endY - startY)}
            C ${endX - 25} ${endY} ${endX - 25} ${endY} ${endX} ${endY}
          `
        })
      },
      checkEdge() {
        const startX = this.x + this.boxWidth + 1
        const startY = this.y + this.boxHeight / 2

        return `M ${startX} ${startY} L ${startX + 25} ${startY}`
      },
      rootEdge() {
        if (this.node.column > 0) {
          return
        }
        const startX = 0
        const startY = this.boxHeight / 2 + this.marginY / 2
        const endX = this.x - 1
        const endY = this.y + this.boxHeight / 2

        return `
            M ${startX} ${startY}
            L ${endX - 50} ${startY}
            C ${endX - 25} ${startY} ${endX - 25} ${startY} ${endX - 25} ${startY + 25 * Math.sign(endY - startY)}
            L ${endX - 25} ${endY - 25 * Math.sign(endY - startY)}
            C ${endX - 25} ${endY} ${endX - 25} ${endY} ${endX} ${endY}
        `
      },
      variable () {
        const op = this.operator;
        if (this.node.rule[op] && this.node.rule[op][0]) {
          return this.node.rule[op][0]["var"];
        } else {
          return "";
        }
      },
      vardata () {
        return this.$root.VARS[this.variable];
      },
      varresult () {
        const op = this.operator;
        if (this.node.rule[op] && this.node.rule[op][0]) {
          return this.node.rule[op][0]["__result"];
        } else {
          return "";
        }
      },
      rightoperand () {
        const op = this.operator;
        if (this.node.rule[op] && typeof this.node.rule[op][1] !== "undefined") {
          return this.node.rule[op][1];
        } else {
          return null;
        }
      },
      op: function () {
        return this.$root.TYPEOPS[this.vardata.type][this.operator]
      },
      operands: function () {
        return this.node.rule[this.operator]
      },
      operator: function () {
        return Object.keys(this.node.rule).filter(function (k) { return !k.startsWith("__") })[0];
      },
      result: function () {
        return typeof this.node.rule.__result == "undefined" ? null : !!this.node.rule.__result
      },
      resultInclParents: function () {
        if (typeof this.node.rule.__result == "undefined")
          return null

        function _p(node) {
          if (node.parent) {
            return node.rule.__result && _p(node.parent)
          }
          return node.rule.__result
        }
        return _p(this.node)
      },
      nodeClass: function () {
        return {
          "node": true,
          "node-true": this.result === true,
          "node-false": this.result === false,
        }
      }
    },
    methods: {
      df (val) {
        const format = $("body").attr("data-datetimeformat")
        return moment(val).format(format)
      },
      tf (val) {
        const format = $("body").attr("data-timeformat")
        return moment(val, "HH:mm:ss").format(format)
      }
    },
  }
</script>
