(() => {
  const root = document.getElementById('quiz');
  const sessionId = Number(root.dataset.session), total = Number(root.dataset.total);
  const KEY = `hsc-quiz-${sessionId}`;
  const slides = [...root.querySelectorAll('.slide')];
  const palette = [...root.querySelectorAll('#palette button')];
  const saved = store.get(KEY) || {};
  const answers = saved.answers || {};      // question_id -> label
  const spent = saved.spent || {};          // question_id -> seconds
  let cur = Math.min(saved.cur || 0, total - 1), shownAt = Date.now(), submitting = false;

  const qid = (i) => slides[i].querySelector('.q').dataset.id;
  const persist = () => store.set(KEY, { answers, spent, cur });

  function bookTime() {
    const id = qid(cur);
    spent[id] = (spent[id] || 0) + Math.round((Date.now() - shownAt) / 1000);
    shownAt = Date.now();
  }

  function render() {
    slides.forEach((s, i) => (s.hidden = i !== cur));
    palette.forEach((b, i) => {
      b.classList.toggle('current', i === cur);
      b.classList.toggle('done', !!answers[qid(i)]);
    });
    const id = qid(cur);
    slides[cur].querySelectorAll('input[type=radio]').forEach((r) => (r.checked = answers[id] === r.value));
    document.getElementById('answered').textContent = bnDigits(Object.keys(answers).length);
    document.getElementById('prev').disabled = cur === 0;
    document.getElementById('next').disabled = cur === total - 1;
    persist();
  }

  function go(i) {
    if (i < 0 || i >= total) return;
    bookTime(); cur = i; render(); window.scrollTo({ top: 0 });
  }

  root.addEventListener('change', (e) => {
    if (e.target.type !== 'radio') return;
    answers[qid(cur)] = e.target.value; render();
  });
  palette.forEach((b) => b.addEventListener('click', () => go(Number(b.dataset.i))));
  document.getElementById('prev').onclick = () => go(cur - 1);
  document.getElementById('next').onclick = () => go(cur + 1);
  document.getElementById('clear').onclick = () => { delete answers[qid(cur)]; render(); };
  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input[type=number], textarea')) return;
    if (e.key === 'ArrowRight') go(cur + 1);
    else if (e.key === 'ArrowLeft') go(cur - 1);
    else if ('1234'.includes(e.key) && e.key) {
      const r = slides[cur].querySelectorAll('input[type=radio]')[Number(e.key) - 1];
      if (r) { r.checked = true; answers[qid(cur)] = r.value; render(); }
    }
  });

  async function submit(force) {
    if (submitting) return;
    const missing = total - Object.keys(answers).length;
    if (!force && missing && !confirm(`${bnDigits(missing)}টি প্রশ্নের উত্তর দেওয়া হয়নি। তবুও জমা দেবে?`)) return;
    submitting = true; bookTime();
    const payload = Object.keys({ ...answers, ...spent }).map((id) => ({ question_id: id, answer: answers[id] || null, time_spent: spent[id] || 0 }));
    const { ok, data } = await postJSON('/api/quiz/submit', { session_id: sessionId, answers: payload });
    if (ok || data.url) { store.del(KEY); location.href = data.url; return; }
    submitting = false; alert(data.error || 'জমা দেওয়া যায়নি।');
  }
  document.getElementById('submit-top').onclick = () => submit(false);

  const timer = document.getElementById('timer');
  if (timer) {
    const end = new Date(timer.dataset.started).getTime() + Number(timer.dataset.seconds) * 1000;
    const tick = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      timer.textContent = bnDigits(`${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`);
      timer.classList.toggle('low', left <= 60);
      if (left === 0) { clearInterval(iv); submit(true); }
    };
    const iv = setInterval(tick, 1000); tick();
  }
  render();
})();
