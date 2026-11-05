// ── MOBILE MENU ───────────────────────────────────────────────
const hamburger = document.getElementById('hamburger');
const mobileNav = document.getElementById('mobileNav');
if (hamburger && mobileNav) {
  hamburger.addEventListener('click', () => {
    const open = mobileNav.classList.toggle('open');
    hamburger.setAttribute('aria-expanded', open);
  });
}

// ── COLOUR THEME (auto / light / dark / paper) ────────────────
(function () {
  const root = document.documentElement;
  const buttons = document.querySelectorAll('[data-theme-choice]');
  let current = 'auto';
  try { current = localStorage.getItem('fd-theme') || 'auto'; } catch (e) {}
  const mark = t => buttons.forEach(b => b.setAttribute('aria-pressed', b.dataset.themeChoice === t));
  mark(current);
  buttons.forEach(b => b.addEventListener('click', () => {
    const t = b.dataset.themeChoice;
    if (t === 'auto') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', t);
    try { localStorage.setItem('fd-theme', t); } catch (e) {}
    mark(t);
  }));
})();

// ── PUBLICATION FILTER ────────────────────────────────────────
document.querySelectorAll('.pub-filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pub-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const filter = btn.dataset.filter;
    let visible = 0;
    document.querySelectorAll('.pub-item').forEach(item => {
      const show = filter === 'all' || item.dataset.type === filter;
      item.style.display = show ? 'grid' : 'none';
      if (show) visible++;
    });
    const counter = document.getElementById('pub-count');
    if (counter) counter.textContent = visible;
  });
});
