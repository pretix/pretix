<template>
    <g>
        <path v-for="e in edges" :d="e" class="edge"></path>
        <path v-if="rootEdge" :d="rootEdge" class="edge"></path>
        <path v-if="!node.children.length" :d="checkEdge" class="edge"></path>
        <rect :width="boxWidth" :height="boxHeight" :x="x" :y="y" class="node" rx="5">
        </rect>
        <text text-anchor="middle" :x="x + boxWidth/2" :y="y + boxHeight/2">
            {{ nodeid }} {{ Object.keys(node.rule)[0] }} {{ node.children.length }}
        </text>

        <g v-if="!node.children.length" :transform="`translate(${x + boxWidth + 25}, ${y + boxHeight/2 - 15})`">
            <path d="m 25.078125,11.835938 c 0,-0.332032 -0.117188,-0.664063 -0.351563,-0.898438 L 22.949219,9.1796875 c -0.234375,-0.234375 -0.546875,-0.3710937 -0.878907,-0.3710937 -0.332031,0 -0.644531,0.1367187 -0.878906,0.3710937 L 13.222656,17.128906 8.8085938,12.714844 C 8.5742188,12.480469 8.2617188,12.34375 7.9296875,12.34375 c -0.3320313,0 -0.6445313,0.136719 -0.8789063,0.371094 l -1.7773437,1.757812 c -0.234375,0.234375 -0.3515625,0.566407 -0.3515625,0.898438 0,0.332031 0.1171875,0.644531 0.3515625,0.878906 l 7.0703125,7.070312 c 0.234375,0.234375 0.566406,0.371094 0.878906,0.371094 0.332032,0 0.664063,-0.136719 0.898438,-0.371094 L 24.726562,12.714844 c 0.234375,-0.234375 0.351563,-0.546875 0.351563,-0.878906 z M 30,15 C 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 23.28125,0 30,6.71875 30,15 Z"
                  class="check" />
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
          const p0X = endX - 40
          const p0Y = startY
          const p1X = p0X + 40
          const p1Y = p0Y
          const p2X = endX - 40
          const p2Y = endY

          return `M ${startX} ${startY} L ${p0X} ${p0Y} C ${p1X} ${p1Y} ${p2X} ${p2Y} ${endX} ${endY}`
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
        const p0X = endX - 40
        const p0Y = startY
        const p1X = p0X + 40
        const p1Y = p0Y
        const p2X = endX - 40
        const p2Y = endY

        return `M ${startX} ${startY} L ${p0X} ${p0Y} C ${p1X} ${p1Y} ${p2X} ${p2Y} ${endX} ${endY}`
      },
    },
    methods: {},
  }
</script>
