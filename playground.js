/**
 * jbook Formula Playground — lightweight slider → formula evaluator.
 * No dependencies. Vanilla JS.
 *
 * Each playground block has id="pg-<chapter_id>".
 * Sliders have id="pg-<chapter_id>-<symbol>" with data-symbol attr.
 * Result display has id="pg-<chapter_id>-result".
 * The formula is stored as a data attribute for safe evaluation.
 */
(function () {
  'use strict';

  function initPlayground(block) {
    const sliders = block.querySelectorAll('input[type="range"]');
    if (!sliders.length) return;

    const pgId = block.id;
    const resultEl = document.getElementById(pgId + '-result');

    // Collect variable references
    function getValues() {
      const vals = {};
      sliders.forEach(function (s) {
        vals[s.dataset.symbol] = parseFloat(s.value);
        // Update display value
        var valEl = document.getElementById(pgId + '-' + s.dataset.symbol + '-val');
        if (valEl) valEl.textContent = s.value;
      });
      return vals;
    }

    // Get the formula from data attr
    var formulaText = block.getAttribute('data-formula') || '';

    function compute(values) {
      if (!formulaText) return NaN;
      try {
        // Replace variable names with values
        var expr = formulaText;
        for (var k in values) {
          // Replace {SYMBOL} with the numeric value
          var re = new RegExp('\\{' + k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\}', 'g');
          expr = expr.replace(re, values[k]);
        }
        // Safe eval: only allow numbers, operators, parens, dots
        if (/^[\d+\-*/.() ]+$/.test(expr)) {
          var result = Function('"use strict"; return (' + expr + ')')();
          return result;
        }
        return NaN;
      } catch (e) {
        return NaN;
      }
    }

    function update() {
      var vals = getValues();
      var result = compute(vals);
      if (resultEl) {
        if (isNaN(result) || !isFinite(result)) {
          resultEl.textContent = '—';
        } else {
          resultEl.textContent = Number(result.toFixed(2)).toString();
        }
      }
    }

    sliders.forEach(function (s) {
      s.addEventListener('input', update);
    });

    // Initial compute
    update();
  }

  function initAll() {
    var blocks = document.querySelectorAll('.playground-block');
    for (var i = 0; i < blocks.length; i++) {
      initPlayground(blocks[i]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
