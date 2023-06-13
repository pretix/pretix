<template>
  <div :class="'checkin-rules-visualization ' + (maximized ? 'maximized' : '')">
    <div class="tools">
      <button v-if="maximized" class="btn btn-default" type="button" @click.prevent="maximized = false"><span class="fa fa-window-close"></span></button>
      <button v-if="!maximized" class="btn btn-default" type="button" @click.prevent="maximized = true"><span class="fa fa-window-maximize"></span></button>
    </div>
    <svg :width="graph.columns * (boxWidth + marginX) + 2 * paddingX" :height="graph.height * (boxHeight + marginY)"
        :viewBox="viewBox" ref="svg">
      <g :transform="zoomTransform.toString()">
        <viz-node v-for="(node, nodeid) in graph.nodes_by_id" :key="nodeid" :node="node"
            :children="node.children.map(n => graph.nodes_by_id[n])" :nodeid="nodeid"
            :boxWidth="boxWidth" :boxHeight="boxHeight" :marginX="marginX" :marginY="marginY"
            :paddingX="paddingX"></viz-node>
      </g>
    </svg>
  </div>
</template>
<script>
export default {
  components: {
    VizNode: VizNode.default,
  },
  computed: {
    boxWidth() {
      return 300
    },
    boxHeight() {
      return 62
    },
    paddingX() {
      return 50
    },
    marginX() {
      return 50
    },
    marginY() {
      return 20
    },
    contentWidth() {
      return this.graph.columns * (this.boxWidth + this.marginX) + 2 * this.paddingX
    },
    contentHeight() {
      return this.graph.height * (this.boxHeight + this.marginY)
    },
    viewBox() {
      return `0 0 ${this.contentWidth} ${this.contentHeight}`
    },
    graph() {
      /**
       * Converts a JSON logic rule into a "flow chart".
       *
       * A JSON logic rule has a structure like an operator tree:
       *
       *  OR
       *  |-- AND
       *      |-- A
       *      |-- B
       *  |-- AND
       *      |-- OR
       *          |-- C
       *          |-- D
       *      |-- E
       *
       * For our visualization, we want to visualize that tree as a graph one can follow along to reach a
       * decision, which has the structure of a directed graph:
       *
       *         --- A --- B --- OK!
       *       /
       *      /
       *     /
       *  --
       *     \
       *      \       --- C ---
       *       \    /           \
       *        ---              --- E --- OK!
       *            \           /
       *              --- D ---
       */
      const graph = {
        nodes_by_id: {},
        children: [],
        columns: -1,
      }

      // Step 1: Start building the graph by finding all nodes and edges
      let counter = 0;
      const _add_to_graph = (rule) => {  // returns [heads, tails]
        if (typeof rule !== 'object' || rule === null) {
          const node_id = (counter++).toString()
          graph.nodes_by_id[node_id] = {
            rule: rule,
            column: -1,
            children: [],
          }
          return [[node_id], [node_id]]
        }

        const operator = Object.keys(rule)[0]
        const operands = rule[operator]

        if (operator === "and") {
          let children = []
          let tails = null
          operands.reverse()
          for (let operand of operands) {
            let [new_children, new_tails] = _add_to_graph(operand)
            for (let new_child of new_tails) {
              graph.nodes_by_id[new_child].children.push(...children)
              for (let c of children) {
                graph.nodes_by_id[c].parent = graph.nodes_by_id[new_child]
              }
            }
            if (tails === null) {
              tails = new_tails
            }
            children = new_children
          }
          return [children, tails]
        } else if (operator === "or") {
          const children = []
          const tails = []
          for (let operand of operands) {
            let [new_children, new_tails] = _add_to_graph(operand)
            children.push(...new_children)
            tails.push(...new_tails)
          }
          return [children, tails]
        } else {
          const node_id = (counter++).toString()
          graph.nodes_by_id[node_id] = {
            rule: rule,
            column: -1,
            children: [],
          }
          return [[node_id], [node_id]]
        }

      }
      graph.children = _add_to_graph(JSON.parse(JSON.stringify(this.$root.rules)))[0]

      // Step 2: We compute the "column" of every node, which is the maximum number of hops required to reach the
      // node from the root node
      const _set_column_to_min = (nodes, mincol) => {
        for (let node of nodes) {
          if (mincol > node.column) {
            node.column = mincol
            graph.columns = Math.max(mincol + 1, graph.columns)
            _set_column_to_min(node.children.map(nid => graph.nodes_by_id[nid]), mincol + 1)
          }
        }
      }
      _set_column_to_min(graph.children.map(nid => graph.nodes_by_id[nid]), 0)

      // Step 3: Align each node on a grid. The x position is already given by the column computed above, but we still
      // need the y position. This part of the algorithm is opinionated and probably not yet the nicest solution we
      // can use!
      const _set_y = (node, offset) => {
        if (typeof node.y === "undefined") {
          // We only take the first value we found for each node
          node.y = offset
        }

        let used = 0
        for (let cid of node.children) {
          used += Math.max(0, _set_y(graph.nodes_by_id[cid], offset + used) - 1)
          used++
        }
        return used
      }
      _set_y(graph, 0)

      // Step 4: Compute the "height" of the graph by looking at the node with the highest y value
      graph.height = 1
      for (let node of [...Object.values(graph.nodes_by_id)]) {
        graph.height = Math.max(graph.height, node.y + 1)
      }

      return graph
    }
  },
  mounted() {
    this.createZoom()
  },
  created() {
    window.addEventListener('resize', this.createZoom)
  },
  destroyed() {
    window.removeEventListener('resize', this.createZoom)
  },
  watch: {
    maximized() {
      this.$nextTick(() => {
        this.createZoom()
      })
    }
  },
  methods: {
    createZoom() {
      if (!this.$refs.svg) return

      const viewportHeight = this.$refs.svg.clientHeight
      const viewportWidth = this.$refs.svg.clientWidth
      this.defaultScale = 1

      this.zoom = d3
          .zoom()
          .scaleExtent([Math.min(this.defaultScale * 0.5, 1), Math.max(5, this.contentHeight / viewportHeight, this.contentWidth / viewportWidth)])
          .extent([[0, 0], [viewportWidth, viewportHeight]])
          .filter(event => {
            const wheeled = event.type === 'wheel'
            const mouseDrag =
                event.type === 'mousedown' ||
                event.type === 'mouseup' ||
                event.type === 'mousemove'
            const touch =
                event.type === 'touchstart' ||
                event.type === 'touchmove' ||
                event.type === 'touchstop'
            return (wheeled || mouseDrag || touch) && this.maximized
          })
          .wheelDelta(event => {
            // In contrast to default implementation, do not use a factor 10 if ctrl is pressed
            return -event.deltaY * (event.deltaMode === 1 ? 0.05 : event.deltaMode ? 1 : 0.002)
          })
          .on('zoom', (event) => {
            this.zoomTransform = event.transform
          })

      const initTransform = d3.zoomIdentity
          .scale(this.defaultScale)
          .translate(
              0,
              0
          )
      this.zoomTransform = initTransform

      // This sets correct d3 internal state for the initial centering
      d3.select(this.$refs.svg)
          .call(this.zoom.transform, initTransform)

      const svg = d3.select(this.$refs.svg).call(this.zoom)
      svg.on('touchmove.zoom', null)
      // TODO touch support
    },
  },
  data() {
    return {
      maximized: false,
      zoom: null,
      defaultScale: 1,
      zoomTransform: d3.zoomTransform({k: 1, x: 0, y: 0}),
    }
  }
}
</script>
