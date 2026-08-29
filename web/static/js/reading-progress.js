/**
 * Scroll-based reading progress: tracks how far the reader has scrolled
 * through a content-detail page and saves it (debounced) to
 * POST /api/progress. See
 * docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md.
 *
 * No-ops entirely if the page has no [data-content-type]/[data-content-id]
 * container - safe to include unconditionally.
 */
(function () {
    var container = document.querySelector('[data-content-type][data-content-id]');
    if (!container) {
        return;
    }

    var contentType = container.dataset.contentType;
    var contentId = parseInt(container.dataset.contentId, 10);
    var debounceTimer = null;
    var highestSent = 0;

    function currentPercent() {
        var scrollable = document.documentElement.scrollHeight - window.innerHeight;
        if (scrollable <= 0) {
            return 100;
        }
        var percent = Math.round((window.scrollY / scrollable) * 100);
        return Math.max(0, Math.min(100, percent));
    }

    function sendProgress(percent, useBeacon) {
        if (percent <= highestSent) {
            return;
        }
        highestSent = percent;

        var payload = JSON.stringify({
            content_type: contentType,
            content_id: contentId,
            percent: percent
        });

        if (useBeacon && navigator.sendBeacon) {
            var blob = new Blob([payload], { type: 'application/json' });
            navigator.sendBeacon('/api/progress', blob);
            return;
        }

        fetch('/api/progress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: payload
        });
    }

    function onScroll() {
        var percent = currentPercent();
        if (debounceTimer) {
            clearTimeout(debounceTimer);
        }
        debounceTimer = setTimeout(function () {
            sendProgress(percent, false);
        }, 2000);
    }

    window.addEventListener('scroll', onScroll, { passive: true });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') {
            sendProgress(currentPercent(), true);
        }
    });
})();
