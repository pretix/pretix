/*global $,gettext,ngettext */

function typocheck() {
    var $target = $("input[data-typocheck-target]"),
        $sources = $("input[data-typocheck-source]"),
        orig_val = $target.val(),
        words = [];

    function regexEscape(str) {
        return str.replace(/[\-\[\]\/\{\}\(\)\*\+\?\.\\\^\$\|]/g, "\\$&");
    }

    $sources.each(function () {
        $.each($(this).val().toLowerCase().replace('-', '').split(' '), function (i, w) {
            if (w && w.length > 5) {
                words.push(w);
            }
        });
    });
    words.push(
        '@gmail.', '@web.', '@gmx.', '@hotmail.', '@live.', '@outlook.', '@yahoo.', '@msn.', '@me.',
        '@verizon.', '@mac.', '@icloud.', '@inbox.', '@rocketmail.', '@bt.', '@orange.',
        '@online.', '@t-online.', '@googlemail.'
    );

    var word, patterns, i, j, k, r,
        val = orig_val;
    for (i = 0; i < words.length; i++) {
        word = words[i];
        patterns = [];
        for (j = 0; j < word.length; j++) {
            if (j > 0) {
                patterns.push(regexEscape(word.slice(0, j)) + '.' + regexEscape(word.slice(j)));
            }
            if (j > 0 || word.slice(0, 1) !== '@') {
                patterns.push(regexEscape(word.slice(0, j)) + '.' + regexEscape(word.slice(j + 1)));
                patterns.push(regexEscape(word.slice(0, j)) + regexEscape(word.slice(j + 1, j + 2)) + regexEscape(word.slice(j, j + 1)) + regexEscape(word.slice(j + 2)));
            }
            patterns.push(regexEscape(word.slice(0, j)) + regexEscape(word.slice(j + 1)));
        }

        // Remove conflicting patterns (i.e. gmail.com shouldn't correct email.com)
        for (j = patterns.length - 1; j >= 0; j--) {
            r = new RegExp(patterns[j]);
            for (k = 0; k < words.length; k++) {
                if (k === i) {
                    continue;
                }
                if (words[k].match(r)) {
                    patterns.splice(j, 1);
                }
            }
        }
        var newval = val.replace(new RegExp('(' + patterns.join('|') + ')', 'i'), word);
        if (newval.split("@").length === 2) {
            val = newval;
        }
    }
    val = val.replace(/gmail\.(?!com$)[a-z]*$/i, 'gmail.com');

    var changed = (val.toLowerCase() != orig_val.toLowerCase());
    $(".typo-alert").toggle(changed).find("[data-typosuggest]").text(val);
    $(".typo-alert").find("[data-typodisplay]").text(orig_val);
}

$(document).ready(function () {
    if ($("input[data-typocheck-target]").length === 0) {
        return;
    }

    $('body').on('change', 'input[data-typocheck-target], input[data-typocheck-source]', function () {
        typocheck();
    });
    $(".typo-alert span[data-typosuggest]").click(function () {
        $("input[data-typocheck-target]").val($(this).text());
        $(".typo-alert").slideUp();
    })
    typocheck();
});
