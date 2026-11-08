// Results page: filter the review list (all / wrong / skipped).
(() => {
  const bar = document.getElementById('filters');
  if (!bar) return;
  bar.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-f]');
    if (!btn) return;
    bar.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.review').forEach((r) => {
      r.hidden = btn.dataset.f !== 'all' && r.dataset.state !== btn.dataset.f;
    });
  });
})();
