/**
 * Shared Share behavior for generated content pages (Study, Currents,
 * Resonance, Workshop): a whole-page Share button, plus a floating
 * "Share" popover that appears when a user highlights text inside a
 * content container.
 *
 * Uses the native Web Share API (navigator.share) so each user shares
 * through whatever they're already logged into on their own device -
 * no OAuth or per-platform API integration needed. Falls back to copying
 * to the clipboard where navigator.share isn't available (most desktop
 * browsers).
 */
(function () {
    function pageTitle() {
        var el = document.querySelector('[data-share-title]');
        return (el && el.dataset.shareTitle) || document.title;
    }

    function buildSharePayload(selectionText) {
        var title = pageTitle();
        var url = window.location.href;
        if (selectionText) {
            return {
                title: title,
                text: '"' + selectionText.trim() + '"\n\n— from ' + title,
                url: url
            };
        }
        return {
            title: title,
            text: title + ' — from The Lectionary Engines',
            url: url
        };
    }

    function showToast(message) {
        var toast = document.getElementById('share-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'share-toast';
            toast.className = 'share-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.classList.add('visible');
        window.clearTimeout(toast._hideTimer);
        toast._hideTimer = window.setTimeout(function () {
            toast.classList.remove('visible');
        }, 2500);
    }

    function shareOrCopy(payload) {
        if (navigator.share) {
            navigator.share(payload).catch(function (err) {
                if (err && err.name === 'AbortError') return; // user cancelled - not an error
                copyToClipboard(payload);
            });
            return;
        }
        copyToClipboard(payload);
    }

    function copyToClipboard(payload) {
        var clipboardText = payload.text + '\n' + payload.url;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(clipboardText)
                .then(function () { showToast('Copied to clipboard'); })
                .catch(function () { showToast('Could not copy — select and copy manually'); });
        } else {
            showToast('Could not copy — select and copy manually');
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var shareBtn = document.getElementById('share-page-btn');
        if (shareBtn) {
            shareBtn.addEventListener('click', function () {
                shareOrCopy(buildSharePayload(null));
            });
        }

        var containers = document.querySelectorAll('[data-highlight-share]');
        if (!containers.length) return;

        var popover = document.createElement('button');
        popover.type = 'button';
        popover.className = 'highlight-share-popover';
        popover.textContent = 'Share this';
        popover.style.display = 'none';
        document.body.appendChild(popover);

        var currentSelectionText = '';

        function hidePopover() {
            popover.style.display = 'none';
        }

        function handleSelection() {
            var selection = window.getSelection();
            var text = selection ? selection.toString().trim() : '';

            if (!text || text.length < 10) {
                hidePopover();
                return;
            }

            var anchorNode = selection.anchorNode;
            var withinContainer = Array.prototype.some.call(containers, function (c) {
                return anchorNode && c.contains(anchorNode);
            });
            if (!withinContainer) {
                hidePopover();
                return;
            }

            var range = selection.getRangeAt(0);
            var rect = range.getBoundingClientRect();
            if (!rect || (rect.width === 0 && rect.height === 0)) {
                hidePopover();
                return;
            }

            currentSelectionText = text;
            popover.style.display = 'block';
            popover.style.top = (window.scrollY + rect.top - 44) + 'px';
            popover.style.left = (window.scrollX + rect.left + rect.width / 2) + 'px';
        }

        document.addEventListener('mouseup', handleSelection);
        document.addEventListener('touchend', handleSelection);

        popover.addEventListener('click', function () {
            shareOrCopy(buildSharePayload(currentSelectionText));
            hidePopover();
            window.getSelection().removeAllRanges();
        });

        document.addEventListener('mousedown', function (e) {
            if (e.target !== popover) hidePopover();
        });
    });
})();
