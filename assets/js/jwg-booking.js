/*
 * jwgrootjen.com booking: replace the single service dropdown with a
 * "Service" dropdown (Office hours / Thesis meeting) plus a "Format" dropdown
 * (In person / Online). Behind the scenes each combination maps to one of the
 * underlying Easy!Appointments services (which carry the right location), so
 * the rest of the booking flow, confirmations and .ics stay unchanged.
 */
(function () {
    'use strict';

    var DURATIONS = { 'Office hours': '20 min', 'Thesis supervision meeting': '30 min' };

    function categoryKey(label) {
        if (/online/i.test(label)) { return 'online'; }
        if (/in[ -]?person/i.test(label)) { return 'inperson'; }
        return label;
    }

    function build() {
        var real = document.getElementById('select-service');
        if (!real) { return false; }
        if (document.getElementById('jwg-service')) { return true; }

        var optgroups = real.querySelectorAll('optgroup');
        if (optgroups.length < 1) { return false; } // services not populated yet

        // Map every underlying service: name + format -> option value.
        var entries = [];
        optgroups.forEach(function (g) {
            var cat = categoryKey(g.label);
            g.querySelectorAll('option').forEach(function (o) {
                entries.push({ name: o.textContent.trim(), cat: cat, value: o.value });
            });
        });
        if (!entries.length) { return false; }

        var names = [];
        entries.forEach(function (e) { if (names.indexOf(e.name) === -1) { names.push(e.name); } });

        var wrapper = real.closest('.mb-3') || real.parentNode;

        var holder = document.createElement('div');
        holder.innerHTML =
            '<div class="mb-3" id="jwg-service-field">' +
            '  <label for="jwg-service" class="fs-5 mb-2"><strong>Service</strong></label>' +
            '  <select id="jwg-service" class="form-select mb-4"><option value="">Please select</option></select>' +
            '</div>' +
            '<div class="mb-3" id="jwg-format-field">' +
            '  <label for="jwg-format" class="fs-5 mb-2"><strong>Format</strong></label>' +
            '  <select id="jwg-format" class="form-select mb-4">' +
            '    <option value="">Please select</option>' +
            '    <option value="inperson">In person (my office at TUM Garching)</option>' +
            '    <option value="online">Online (via Zoom)</option>' +
            '  </select>' +
            '</div>';
        while (holder.firstChild) { wrapper.parentNode.insertBefore(holder.firstChild, wrapper); }

        var svc = document.getElementById('jwg-service');
        names.forEach(function (n) {
            var o = document.createElement('option');
            o.value = n;
            o.textContent = DURATIONS[n] ? n + ' — ' + DURATIONS[n] : n;
            svc.appendChild(o);
        });

        wrapper.style.display = 'none'; // hide the underlying service field

        function sync() {
            var name = svc.value;
            var fmt = document.getElementById('jwg-format').value;
            if (!name || !fmt) { return; }
            var match = entries.filter(function (e) { return e.name === name && e.cat === fmt; })[0];
            if (match) {
                real.value = match.value;
                real.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
        svc.addEventListener('change', sync);
        document.getElementById('jwg-format').addEventListener('change', sync);
        return true;
    }

    function boot() {
        if (build()) { return; }
        var real = document.getElementById('select-service');
        if (real) {
            var mo = new MutationObserver(function () { if (build()) { mo.disconnect(); } });
            mo.observe(real, { childList: true });
        }
        var tries = 0;
        var timer = setInterval(function () { if (build() || ++tries > 40) { clearInterval(timer); } }, 250);
    }

    if (document.readyState !== 'loading') { boot(); }
    else { document.addEventListener('DOMContentLoaded', boot); }
})();
