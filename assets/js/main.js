// ── HAMBURGER ────────────────────────────────────────────────
const hamburger = document.getElementById('hamburger');
const mobileNav = document.getElementById('mobileNav');
if (hamburger) {
  hamburger.addEventListener('click', () => mobileNav.classList.toggle('open'));
}

// ── PUBLICATION FILTER ────────────────────────────────────────
document.querySelectorAll('.pub-filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pub-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const filter = btn.dataset.filter;
    document.querySelectorAll('.pub-item').forEach(item => {
      const show = filter === 'all' || item.dataset.type === filter;
      item.style.display = show ? 'grid' : 'none';
    });
    // Update count
    const visible = document.querySelectorAll('.pub-item:not([style*="none"])').length;
    const counter = document.getElementById('pub-count');
    if (counter) counter.textContent = visible;
  });
});

// ── SCROLL REVEAL ─────────────────────────────────────────────
if ('IntersectionObserver' in window) {
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.style.opacity = '1';
        e.target.style.transform = 'translateY(0)';
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.07 });
  document.querySelectorAll('.pub-item, .pos-item, .edu-item, .tl-item, .thesis-card, .project-card, .award-item').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(10px)';
    el.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
    obs.observe(el);
  });
}
