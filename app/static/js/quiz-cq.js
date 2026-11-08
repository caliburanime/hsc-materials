(() => {
  const root = document.getElementById('quiz');
  const sessionId = Number(root.dataset.session), total = Number(root.dataset.total);
  const slides = [...root.querySelectorAll('.slide')];
  const KEY = `hsc-quiz-${sessionId}`;
  const grades = (store.get(KEY) || {}).grades || {};
  let cur = 0, shownAt = Date.now(), submitting = false;
  const spent = {};

  function render() {
    slides.forEach((s, i) => (s.hidden = i !== cur));
    const s = slides[cur];
    s.querySelector('.selfgrade').value = grades[s.dataset.id] ?? '';
    document.getElementById('graded').textContent = bnDigits(Object.keys(grades).length);
    document.getElementById('pos').textContent = `${bnDigits(cur + 1)} / ${bnDigits(total)}`;
    document.getElementById('prev').disabled = cur === 0;
    document.getElementById('next').disabled = cur === total - 1;
  }
  function go(i) {
    if (i < 0 || i >= total) return;
    const id = slides[cur].dataset.id;
    spent[id] = (spent[id] || 0) + Math.round((Date.now() - shownAt) / 1000);
    shownAt = Date.now(); cur = i; render(); window.scrollTo({ top: 0 });
  }
  root.addEventListener('input', (e) => {
    if (!e.target.classList.contains('selfgrade')) return;
    const s = slides[cur], id = s.dataset.id, max = Number(s.dataset.marks);
    if (e.target.value === '') delete grades[id];
    else grades[id] = Math.max(0, Math.min(max, Number(e.target.value)));
    store.set(KEY, { grades });
    document.getElementById('graded').textContent = bnDigits(Object.keys(grades).length);
  });
  document.getElementById('prev').onclick = () => go(cur - 1);
  document.getElementById('next').onclick = () => go(cur + 1);
  document.getElementById('submit-top').onclick = async () => {
    if (submitting) return;
    submitting = true; go(cur);
    const answers = slides.map((s) => ({ question_id: s.dataset.id, self_grade: grades[s.dataset.id] ?? null, time_spent: spent[s.dataset.id] || 0 }));
    const { ok, data } = await postJSON('/api/quiz/submit', { session_id: sessionId, answers });
    if (ok || data.url) { store.del(KEY); location.href = data.url; return; }
    submitting = false; alert(data.error || 'জমা দেওয়া যায়নি।');
  };
  render();
})();
