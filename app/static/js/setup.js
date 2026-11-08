(() => {
  const subjects = JSON.parse(document.getElementById('subjects-data').textContent);
  const $ = (id) => document.getElementById(id);
  const subjectSel = $('subject'), typeSel = $('type'), chaptersBox = $('chapters');
  const board = $('board'), year = $('year'), count = $('count'), avail = $('avail');
  const timed = $('timed'), minutes = $('minutes'), err = $('err');
  const preChapter = $('setup').dataset.preChapter;   // from the dashboard's "practise this chapter" link
  let firstRender = true;
  const current = () => subjects.find((s) => s.id === subjectSel.value);

  function fillSelect(sel, values, labelFn) {
    const first = sel.options[0];
    sel.innerHTML = '';
    sel.appendChild(first);
    values.forEach((v) => sel.appendChild(new Option(labelFn(v), v)));
  }

  function renderChapters() {
    const s = current(), t = typeSel.value;
    const prev = new Set([...chaptersBox.querySelectorAll('input:checked')].map((i) => i.value));
    chaptersBox.innerHTML = '';
    if (!s) return;
    s.chapters.forEach((c) => {
      const n = c.counts[t] || 0;
      const label = document.createElement('label');
      label.className = 'check' + (n ? '' : ' disabled');
      label.innerHTML = `<input type="checkbox" value="${c.number}" ${n ? '' : 'disabled'}>` +
        `<span>${bnDigits(c.number)}. </span><span class="grow"></span><em>${bnDigits(n)}টি</em>`;
      label.querySelector('.grow').textContent = c.name;
      const box = label.querySelector('input');
      const want = firstRender && preChapter ? String(c.number) === preChapter : (prev.size ? prev.has(String(c.number)) : true);
      if (n && want) box.checked = true;
      box.addEventListener('change', updateAvail);
      chaptersBox.appendChild(label);
    });
    firstRender = false;
    updateAvail();
  }

  function renderFilters() {
    // Boards/years come from the server per subject; they are rendered once from the embedded data.
    const s = current();
    fillSelect(board, s.boards, (b) => b);
    fillSelect(year, s.years, (y) => bnDigits(y));
  }

  function updateAvail() {
    const t = typeSel.value;
    const n = [...chaptersBox.querySelectorAll('input:checked')].reduce((sum, i) => {
      const c = current().chapters.find((c) => String(c.number) === i.value);
      return sum + (c.counts[t] || 0);
    }, 0);
    avail.textContent = `(সর্বোচ্চ ${bnDigits(n)}টি; বোর্ড/সাল ফিল্টারে কমতে পারে)`;
    count.max = n || 1;
  }

  $('all-ch').onclick = () => { chaptersBox.querySelectorAll('input:not(:disabled)').forEach((i) => (i.checked = true)); updateAvail(); };
  $('no-ch').onclick = () => { chaptersBox.querySelectorAll('input').forEach((i) => (i.checked = false)); updateAvail(); };
  subjectSel.onchange = () => { renderFilters(); renderChapters(); };
  typeSel.onchange = renderChapters;
  timed.onchange = () => { minutes.disabled = !timed.checked; };

  $('setup').addEventListener('submit', async (e) => {
    e.preventDefault();
    err.hidden = true;
    const chapters = [...chaptersBox.querySelectorAll('input:checked')].map((i) => Number(i.value));
    if (!chapters.length) { err.textContent = 'কমপক্ষে একটি অধ্যায় বেছে নাও।'; err.hidden = false; return; }
    const { ok, data } = await postJSON('/api/quiz/start', {
      subject: subjectSel.value, type: typeSel.value, chapters,
      board: board.value, year: year.value, count: Number(count.value) || 25,
      random: $('random').checked, timed: timed.checked, time_minutes: Number(minutes.value) || 0,
    });
    if (!ok) { err.textContent = data.error || 'কিছু একটা ভুল হয়েছে।'; err.hidden = false; return; }
    location.href = data.url;
  });

  renderFilters();
  renderChapters();
})();
