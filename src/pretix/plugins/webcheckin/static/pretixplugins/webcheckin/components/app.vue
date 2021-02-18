<template>
  <div id="app">
    <p>Hello World</p>
    <p>{{ random }}</p>
  </div>
</template>
<script>
export default {
  components: { },
  data () {
    return {
    }
  },
  computed: {
    random: () => {
      const isBabel = !(class {}.toString().indexOf('class ') === 0);
      console.log(isBabel);
      return Math.random()
    }
  },
}
</script>
