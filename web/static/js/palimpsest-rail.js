/**
 * Palimpsest spatial rail: highlights the currently-visible layer in
 * the left rail as the reader scrolls, and smooth-scrolls to a layer
 * when its rail link is clicked. See
 * docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md.
 *
 * No-ops entirely if the rail isn't on the page (every non-Palimpsest
 * study, and any Palimpsest study whose content didn't parse into five
 * layers) - this file is safe to include unconditionally, though
 * study.html only includes it when palimpsest_rail is present.
 */
(function () {
    var rail = document.querySelector('.palimpsest-rail');
    if (!rail) {
        return;
    }

    var links = Array.prototype.slice.call(rail.querySelectorAll('.palimpsest-rail-link'));

    function setActive(key) {
        links.forEach(function (link) {
            if (link.dataset.layerKey === key) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    var sections = [];
    links.forEach(function (link) {
        var section = document.getElementById('layer-' + link.dataset.layerKey);
        if (section) {
            sections.push(section);
        }
    });

    if (sections.length > 0 && 'IntersectionObserver' in window) {
        var observer = new IntersectionObserver(function (entries) {
            var visible = entries.filter(function (entry) {
                return entry.isIntersecting;
            });
            visible.sort(function (a, b) {
                return b.intersectionRatio - a.intersectionRatio;
            });
            if (visible.length > 0) {
                setActive(visible[0].target.id.replace('layer-', ''));
            }
        }, {
            rootMargin: '-20% 0px -70% 0px',
            threshold: [0, 0.25, 0.5, 0.75, 1]
        });

        sections.forEach(function (section) {
            observer.observe(section);
        });
    }

    links.forEach(function (link) {
        link.addEventListener('click', function (event) {
            var section = document.getElementById('layer-' + link.dataset.layerKey);
            if (section) {
                event.preventDefault();
                section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
})();
