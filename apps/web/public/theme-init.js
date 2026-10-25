// Sahifa chizilishidan oldin foydalanuvchi tanlagan mavzu (lib/theme.ts bilan bir xil qoida; CSP — tashqi fayl).
(function () {
  try {
    var t = localStorage.getItem("up.theme");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  } catch (e) {
    // localStorage yopiq — tizim sozlamasi
  }
})();
