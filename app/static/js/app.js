/* Progressive enhancement only: every page works without JavaScript. */
(function () {
  "use strict";

  // Confirmation before destructive actions: <form data-confirm="Message">
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var message = form.getAttribute && form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
      return;
    }
    // Prevent duplicate submissions.
    if (!event.defaultPrevented && form.hasAttribute("data-once")) {
      form.setAttribute("data-submitting", "1");
      var buttons = form.querySelectorAll("button[type=submit]");
      for (var i = 0; i < buttons.length; i++) {
        buttons[i].disabled = true;
      }
    }
  });

  // Warn about unsaved changes on data-entry forms (<form data-warn-unsaved>).
  var guarded = document.querySelector("form[data-warn-unsaved]");
  if (guarded) {
    var dirty = false;
    guarded.addEventListener("input", function () { dirty = true; });
    guarded.addEventListener("change", function () { dirty = true; });
    guarded.addEventListener("submit", function () { dirty = false; });
    window.addEventListener("beforeunload", function (event) {
      if (dirty) { event.preventDefault(); event.returnValue = ""; }
    });
  }

  // Add / remove defect rows on the inspection form.
  var container = document.getElementById("defect-rows");
  var template = document.getElementById("defect-row-template");
  var addButton = document.getElementById("add-defect");
  if (container && template && addButton) {
    var max = parseInt(container.getAttribute("data-max") || "50", 10);
    var next = parseInt(container.getAttribute("data-next") || "0", 10);

    var count = function () { return container.querySelectorAll(".defect-row").length; };
    var refresh = function () {
      var rows = container.querySelectorAll(".defect-row");
      for (var i = 0; i < rows.length; i++) {
        var title = rows[i].querySelector(".row-title");
        if (title) { title.textContent = "Defect " + (i + 1); }
      }
      addButton.disabled = count() >= max;
      var empty = document.getElementById("no-defects");
      if (empty) { empty.hidden = count() > 0; }
    };

    addButton.addEventListener("click", function () {
      if (count() >= max) { return; }
      var html = template.innerHTML.replace(/__INDEX__/g, String(next));
      next += 1;
      var holder = document.createElement("div");
      holder.innerHTML = html.trim();
      var row = holder.firstElementChild;
      container.appendChild(row);
      refresh();
      var first = row.querySelector("select, input");
      if (first) { first.focus(); }
      if (guarded) { guarded.dispatchEvent(new Event("change")); }
    });

    container.addEventListener("click", function (event) {
      var button = event.target.closest(".remove-defect");
      if (!button) { return; }
      var row = button.closest(".defect-row");
      if (row) { row.parentNode.removeChild(row); refresh(); }
      if (guarded) { guarded.dispatchEvent(new Event("change")); }
    });
    refresh();
  }

  // Disposition form: show the running total against the inspected quantity.
  var total = document.getElementById("disp-total");
  if (total) {
    var inputs = document.querySelectorAll("input[data-disp-qty]");
    var inspected = parseInt(total.getAttribute("data-inspected"), 10);
    var update = function () {
      var sum = 0;
      for (var i = 0; i < inputs.length; i++) {
        var n = parseInt(inputs[i].value, 10);
        if (!isNaN(n)) { sum += n; }
      }
      var diff = inspected - sum;
      total.textContent = sum.toLocaleString() + " of " + inspected.toLocaleString() +
        (diff === 0 ? " - reconciled" : diff > 0 ? " - " + diff.toLocaleString() + " unallocated" : " - " + (-diff).toLocaleString() + " over");
    };
    for (var j = 0; j < inputs.length; j++) { inputs[j].addEventListener("input", update); }
    update();
  }
})();
