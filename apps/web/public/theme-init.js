// Sahifa chizilishidan oldin foydalanuvchi tanlagan mavzu (lib/theme.ts bilan bir xil qoida; CSP — tashqi fayl).
(function () {
  try {
    // Standart — yorug' (ADR-048); "system" — tanlangan: data-theme qo'yilmaydi, CSS tizim sozlamasiga qaraydi.
    var t = localStorage.getItem("up.theme");
    if (t !== "system") document.documentElement.setAttribute("data-theme", t === "dark" ? "dark" : "light");
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "light"); // localStorage yopiq — yorug'
  }
})();
