// Shared behaviour: "show answer" buttons (CQ) on any page.
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.reveal');
  if (!btn) return;
  const box = btn.closest('.slide') || btn.previousElementSibling;
  if (!box) return;
  const answers = box.querySelectorAll('.answer');
  const show = [...answers].some((a) => a.hidden);
  answers.forEach((a) => (a.hidden = !show));
  btn.textContent = show ? 'উত্তর লুকাও' : 'উত্তর দেখাও';
});

// POST JSON helper used by the quiz pages.
window.postJSON = async (url, body) => {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
};
window.bnDigits = (n) => String(n).replace(/\d/g, (d) => '০১২৩৪৫৬৭৮৯'[d]);
window.store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
