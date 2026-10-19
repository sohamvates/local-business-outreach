/* Country names the person can choose. The canonical name is the English one Google confirms.
   Extra words are only search aliases, so "bras" can find Brazil. */

const COUNTRY_CHOICES = [
  ["AF", "Afghanistan"],
  ["AL", "Albania"],
  ["DZ", "Algeria"],
  ["AR", "Argentina"],
  ["AM", "Armenia"],
  ["AU", "Australia"],
  ["AT", "Austria", "Österreich"],
  ["AZ", "Azerbaijan"],
  ["BH", "Bahrain"],
  ["BD", "Bangladesh"],
  ["BY", "Belarus"],
  ["BE", "Belgium", "België", "Belgique"],
  ["BO", "Bolivia"],
  ["BA", "Bosnia and Herzegovina"],
  ["BR", "Brazil", "Brasil"],
  ["BG", "Bulgaria"],
  ["KH", "Cambodia"],
  ["CM", "Cameroon"],
  ["CA", "Canada"],
  ["CL", "Chile"],
  ["CN", "China"],
  ["CO", "Colombia"],
  ["CR", "Costa Rica"],
  ["HR", "Croatia", "Hrvatska"],
  ["CU", "Cuba"],
  ["CY", "Cyprus"],
  ["CZ", "Czechia", "Czech Republic"],
  ["DK", "Denmark", "Danmark"],
  ["DO", "Dominican Republic"],
  ["EC", "Ecuador"],
  ["EG", "Egypt"],
  ["SV", "El Salvador"],
  ["EE", "Estonia"],
  ["ET", "Ethiopia"],
  ["FI", "Finland", "Suomi"],
  ["FR", "France", "França"],
  ["GE", "Georgia"],
  ["DE", "Germany", "Alemanha", "Deutschland"],
  ["GH", "Ghana"],
  ["GR", "Greece", "Ελλάδα"],
  ["GT", "Guatemala"],
  ["HN", "Honduras"],
  ["HK", "Hong Kong"],
  ["HU", "Hungary", "Magyarország"],
  ["IS", "Iceland"],
  ["IN", "India"],
  ["ID", "Indonesia"],
  ["IR", "Iran"],
  ["IQ", "Iraq"],
  ["IE", "Ireland"],
  ["IL", "Israel"],
  ["IT", "Italy", "Italia"],
  ["JM", "Jamaica"],
  ["JP", "Japan"],
  ["JO", "Jordan"],
  ["KZ", "Kazakhstan"],
  ["KE", "Kenya"],
  ["KW", "Kuwait"],
  ["LV", "Latvia"],
  ["LB", "Lebanon"],
  ["LY", "Libya"],
  ["LT", "Lithuania"],
  ["LU", "Luxembourg"],
  ["MY", "Malaysia"],
  ["MT", "Malta"],
  ["MX", "Mexico", "México"],
  ["MD", "Moldova"],
  ["MA", "Morocco"],
  ["MZ", "Mozambique", "Moçambique"],
  ["MM", "Myanmar"],
  ["NP", "Nepal"],
  ["NL", "Netherlands", "Nederland", "Holanda"],
  ["NZ", "New Zealand"],
  ["NI", "Nicaragua"],
  ["NG", "Nigeria"],
  ["NO", "Norway", "Norge"],
  ["OM", "Oman"],
  ["PK", "Pakistan"],
  ["PA", "Panama"],
  ["PY", "Paraguay"],
  ["PE", "Peru", "Perú"],
  ["PH", "Philippines"],
  ["PL", "Poland", "Polska"],
  ["PT", "Portugal"],
  ["QA", "Qatar"],
  ["RO", "Romania"],
  ["RU", "Russia"],
  ["SA", "Saudi Arabia"],
  ["SN", "Senegal"],
  ["RS", "Serbia"],
  ["SG", "Singapore"],
  ["SK", "Slovakia"],
  ["SI", "Slovenia"],
  ["ZA", "South Africa"],
  ["KR", "South Korea", "Korea"],
  ["ES", "Spain", "Espanha", "España"],
  ["LK", "Sri Lanka"],
  ["SE", "Sweden", "Sverige"],
  ["CH", "Switzerland", "Schweiz", "Suisse"],
  ["TW", "Taiwan"],
  ["TZ", "Tanzania"],
  ["TH", "Thailand"],
  ["TN", "Tunisia"],
  ["TR", "Turkey", "Türkiye"],
  ["UG", "Uganda"],
  ["UA", "Ukraine"],
  ["AE", "United Arab Emirates", "UAE", "Emirados"],
  ["GB", "United Kingdom", "UK", "Britain", "Reino Unido", "England"],
  ["US", "United States", "USA", "EUA", "Estados Unidos", "United States of America"],
  ["UY", "Uruguay"],
  ["UZ", "Uzbekistan"],
  ["VE", "Venezuela"],
  ["VN", "Vietnam"],
  ["ZM", "Zambia"],
  ["ZW", "Zimbabwe"],
];

function foldPlaceText(value) {
  return (value || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

function filterCountries(query) {
  const folded = foldPlaceText(query).trim();
  if (folded.length < 2) return [];
  const ranked = [];
  COUNTRY_CHOICES.forEach((entry) => {
    const code = entry[0];
    const name = entry[1];
    const aliases = entry.slice(2);
    let score = 0;
    [name, ...aliases].forEach((label) => {
      const text = foldPlaceText(label);
      if (text.startsWith(folded)) score = Math.max(score, 2);
      else if (text.includes(folded)) score = Math.max(score, 1);
    });
    if (score) ranked.push({ score: score, code: code, name: name, alias: aliases[0] || "" });
  });
  ranked.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  return ranked.slice(0, 8);
}

function countryByCode(code) {
  const wanted = (code || "").toUpperCase();
  const found = COUNTRY_CHOICES.find((entry) => entry[0] === wanted);
  return found ? { code: found[0], name: found[1] } : null;
}
