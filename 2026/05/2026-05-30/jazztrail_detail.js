// JazzTrail detail extraction JS
function jazztrailGetDetail() {
    var article = document.querySelector('article') || document.querySelector('.post') || document.querySelector('main') || document;
    var clone = article.cloneNode(true);
    var removeTags = ['SCRIPT','STYLE','NAV','FOOTER','ASIDE','IFRAME','NOSCRIPT'];
    for (var ri = 0; ri < removeTags.length; ri++) {
        var els = clone.querySelectorAll(removeTags[ri]);
        for (var ei = 0; ei < els.length; ei++) els[ei].remove();
    }
    var body = clone.innerText ? clone.innerText.trim() : '';
    body = body.replace(/\n{3,}/g, '\n\n').replace(/  +/g, ' ').trim();

    // Score - read text before removing
    var scoreText = '';
    var scoreEls = document.querySelectorAll('.score, .rating, [class*=score], [class*=rating]');
    for (var si = 0; si < scoreEls.length; si++) {
        var txt = scoreEls[si].textContent.trim();
        if (txt) { scoreText = txt; break; }
    }

    // Artist
    var artist = '';
    var artistEl = document.querySelector('.artist, [class*=artist]');
    if (artistEl) artist = artistEl.textContent.trim();

    // Tags
    var tags = [];
    var tagAnchors = document.querySelectorAll('a[href*="/tag/"]');
    for (var ti = 0; ti < tagAnchors.length; ti++) {
        var href = tagAnchors[ti].href;
        var idx = href.indexOf('/tag/');
        if (idx >= 0) {
            var tag = href.slice(idx + 5);
            var q = tag.indexOf('?');
            if (q >= 0) tag = tag.slice(0, q);
            tags.push(tag);
        }
    }

    return {body: body, scoreText: scoreText, artist: artist, tags: tags};
}
