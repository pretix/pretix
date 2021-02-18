window.vapp = new Vue({
    components: {
        App: App.default
    },
    render: function (h) {
        return h('App')
    },
    el: '#app'
})
