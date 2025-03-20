$(function() {
    var plugins = $(".plugin-container").toArray().map(function(el) {
        return {
            sortName: el.getAttribute('data-plugin-name').toLowerCase().replace(/pretix /g, ''),
            name: el.getAttribute('data-plugin-name').toLowerCase(),
            module: el.getAttribute('data-plugin-module').toLowerCase(),
            description: $(el).find('.plugin-description').text().toLowerCase(),
            html: el.outerHTML,
            category: $(el).closest('[data-plugin-category]').attr('data-plugin-category'),
            categoryLabel: $(el).closest('[data-plugin-category]').attr('data-plugin-category-label'),
            active: !!$(el).has('[data-is-active]').length,
        }
    });
    function SearchMatcher(term, fields) {
        this.searchFor = term.toLowerCase().split(/\s+/);
        this.fields = fields;
    }
    function inStringRanked(haystack, needle) {
        let pos = -1, rank = 0;
        do {
            pos = haystack.indexOf(needle, pos + 1);
            if (pos !== -1) rank = 10;
            if (pos === 0 || haystack.charCodeAt(pos - 1) <= 47)
                return 15;  // string start or word start (=char before match is special char)
        } while (pos !== -1);
        return rank;
    }
    SearchMatcher.prototype.isMatch = function(obj) {
        let rank = 0;
        for(let j = 0; j < this.searchFor.length; j++) {
            var searchFor = this.searchFor[j];
            for(let i = this.fields.length - 1; i >= 0; i--) {
                var result = inStringRanked(obj[this.fields[i]], searchFor);
                if (result) {
                    rank += (i + 1) * result;
                    break;
                }
            }
        }
        return rank;
    }
    function strcmp(a, b) {
        return a > b ? 1 : a < b ? -1 : 0;
    }
    var $results_box = $("#plugin_search_results");
    var $plugin_tabs = $("#plugin_tabs");
    var $results = $("#plugin_search_results .plugin-list");
    function search() {
        $results.html("");
        var value = $("#plugin_search_input").val();
        var only_active = $("input[name=plugin_state_filter][value=active]").prop("checked");
        if (!value && !only_active) {
            $results_box.hide(); $plugin_tabs.show();
            return;
        }
        $results_box.show(); $plugin_tabs.hide();
        var matcher = new SearchMatcher(value, ["description", "module", "name"]);
        var matches = [];
        for(const plugin of plugins) {
            if (only_active && !plugin.active) continue;
            var rank = matcher.isMatch(plugin);
            if (!rank) continue;
            matches.push([rank, plugin]);
        }
        matches.sort(function (a,b) { return (b[0]-a[0]) || strcmp(a[1].sortName, b[1].sortName); })
        $results.append(matches.map(function(res) { return $(res[1].html).prepend('<span class="pull-right">' + res[1].categoryLabel + '</span>'); }))
        $results.find(".panel-body, .panel, .featured-plugin, .btn-lg").removeClass("panel-body panel featured-plugin btn-lg");
        if (matches.length === 0) {
            $results.append(gettext("No results"));
        }
    }
    $("#plugin_search_input").on("input", search);
    $("input[name=plugin_state_filter]").on("change", search);
    $results_box.find("button.close").on("click", function() {
        $("input[name=plugin_state_filter][value=all]").prop("checked", true).trigger("click");
        $("#plugin_search_input").val("").trigger("input");
    });
    if (location.search) {
        var search = new URLSearchParams(location.search);
        if (search.has('q')) {
            $("#plugin_search_input").val(search.get("q")).trigger("input");
        }
    }
})
