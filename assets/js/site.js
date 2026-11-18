/* marcoledda.it: theme toggle, mobile menu, BibTeX/abstract panels. */
(function () {
  'use strict';
  var root = document.documentElement;

  /* Theme: explicit choice is remembered; otherwise the OS setting applies. */
  function currentTheme() {
    var t = root.getAttribute('data-theme');
    if (t) return t;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  var themeBtn = document.querySelector('.theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* storage unavailable */ }
    });
  }

  /* Mobile menu */
  var header = document.querySelector('.site-header');
  var menuBtn = document.querySelector('.menu-toggle');
  function setMenu(open) {
    if (!header || !menuBtn) return;
    header.classList.toggle('nav-open', open);
    menuBtn.setAttribute('aria-expanded', String(open));
    menuBtn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  }
  if (menuBtn) {
    menuBtn.addEventListener('click', function () {
      setMenu(!header.classList.contains('nav-open'));
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setMenu(false);
  });

  /* BibTeX / Abstract panels (one open at a time per paper) and copy button */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-panel]');
    if (btn) {
      var open = btn.getAttribute('aria-expanded') !== 'true';
      var group = btn.closest('.pub-actions');
      if (group) {
        group.querySelectorAll('[data-panel]').forEach(function (other) {
          if (other === btn) return;
          other.setAttribute('aria-expanded', 'false');
          var p = document.getElementById(other.getAttribute('aria-controls'));
          if (p) p.hidden = true;
        });
      }
      btn.setAttribute('aria-expanded', String(open));
      var panel = document.getElementById(btn.getAttribute('aria-controls'));
      if (panel) panel.hidden = !open;
      return;
    }

    var copy = e.target.closest('.copy-bib');
    if (copy) {
      var code = copy.parentNode.querySelector('code');
      var label = copy.querySelector('span');
      var done = function () {
        copy.classList.add('is-done');
        if (label) label.textContent = 'Copied';
        setTimeout(function () {
          copy.classList.remove('is-done');
          if (label) label.textContent = 'Copy';
        }, 1600);
      };
      var text = code ? code.textContent : '';
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { selectText(code); });
      } else {
        selectText(code);
      }
    }
  });

  /* Publication filters: type (arXiv / journal / conference / thesis) and year, kept in the URL */
  var bar = document.querySelector('.pub-filters');
  if (bar) {
    var items = [].slice.call(document.querySelectorAll('.pub[data-category]'));
    var sections = [].slice.call(document.querySelectorAll('.pub-section'));
    var chips = [].slice.call(bar.querySelectorAll('.chip[data-type]'));
    var yearSel = bar.querySelector('select[data-filter="year"]');
    var status = bar.querySelector('.filter-status');
    var reset = bar.querySelector('.filter-reset');
    var empty = document.querySelector('.filter-empty');
    var state = { type: '', year: '' };

    try {
      var params = new URLSearchParams(window.location.search);
      state.type = params.get('type') || '';
      state.year = params.get('year') || '';
    } catch (e) { /* old browser: start unfiltered */ }

    chips.forEach(function (chip) {
      chip.hidden = false;
      chip.setAttribute('role', 'button');
      chip.addEventListener('click', function (e) {
        e.preventDefault();
        var t = chip.getAttribute('data-type');
        state.type = state.type === t ? '' : t;
        apply(true);
      });
    });
    if (yearSel) {
      yearSel.addEventListener('change', function () {
        state.year = yearSel.value;
        apply(true);
      });
    }
    document.addEventListener('click', function (e) {
      if (e.target.closest('.filter-reset, .filter-reset-inline')) {
        state.type = '';
        state.year = '';
        apply(true);
      }
    });

    function apply(push) {
      var active = !!(state.type || state.year);
      var shown = 0;
      items.forEach(function (it) {
        var ok = (!state.type || it.getAttribute('data-category') === state.type) &&
          (!state.year || it.getAttribute('data-year') === state.year);
        it.hidden = !ok;
        if (ok) shown++;
      });
      sections.forEach(function (sec) {
        var visible = sec.querySelectorAll('.pub:not([hidden])');
        sec.hidden = active && visible.length === 0;
        sec.querySelectorAll('.pub.is-last').forEach(function (p) { p.classList.remove('is-last'); });
        if (visible.length) visible[visible.length - 1].classList.add('is-last');
      });
      chips.forEach(function (chip) {
        chip.setAttribute('aria-pressed', String(chip.getAttribute('data-type') === state.type));
      });
      if (yearSel && yearSel.value !== state.year) yearSel.value = state.year;
      if (reset) reset.hidden = !active;
      if (empty) empty.hidden = !active || shown > 0;
      if (status) {
        status.textContent = active
          ? 'Showing ' + shown + ' of ' + items.length + ' publications'
          : items.length + ' publications';
      }
      if (push) {
        try {
          var q = new URLSearchParams();
          if (state.type) q.set('type', state.type);
          if (state.year) q.set('year', state.year);
          var qs = q.toString();
          history.replaceState(null, '', window.location.pathname + (qs ? '?' + qs : ''));
        } catch (e) { /* URL update is optional */ }
      }
    }
    apply(false);
  }

  function selectText(node) {
    if (!node) return;
    var range = document.createRange();
    range.selectNodeContents(node);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }
})();
