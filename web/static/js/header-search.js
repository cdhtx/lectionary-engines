/**
 * Focuses the header search input on Cmd+K / Ctrl+K. The search form
 * itself is plain HTML (works via normal submission with JS entirely
 * absent) - this is a pure keyboard-shortcut enhancement.
 */
(function () {
    var input = document.querySelector('.topbar-search input[name="q"]');
    if (!input) {
        return;
    }

    document.addEventListener('keydown', function (event) {
        var isShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
        if (isShortcut) {
            event.preventDefault();
            input.focus();
        }
    });
})();
