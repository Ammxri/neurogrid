// NeuroGrid documentation (A-28): the search index is loaded by a web worker, which browsers do not start for
// pages opened from the disk (file://). There the search field is disabled and says how to search instead
// (serve the folder on 127.0.0.1, see Installation). No request leaves the page.
(function () {
  "use strict";
  if (window.location.protocol !== "file:") {
    return;
  }
  var hints = {
    en: "Search needs a local server (see Installation)",
    zh: "搜索需通过本地服务器打开（见“安装”）"
  };
  function disable() {
    var lang = (document.documentElement.lang || "en").toLowerCase().slice(0, 2);
    var text = hints[lang] || hints.en;
    var inputs = document.querySelectorAll("input.md-search__input");
    for (var i = 0; i < inputs.length; i++) {
      inputs[i].disabled = true;
      inputs[i].placeholder = text;
      inputs[i].setAttribute("aria-label", text);
      inputs[i].title = text;
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", disable);
  } else {
    disable();
  }
})();
