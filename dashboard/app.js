// Escape all dynamic strings before inserting template-rendered dashboard HTML.
function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[ch]);
}

// ---- People layer --------------------------------------------------------
// Coordinators think in people and clock times, not IDs. Every name, time and
// phone number below is synthetic and derived deterministically from the IDs,
// which stay visible in small type for traceability.
const PATIENT_NAMES = ['Kamala Iyer','Rajendra Sharma','Shanti Devi','Mohan Rao','Lakshmi Menon','Harbhajan Singh',
  'Sarojini Nair','Prakash Joshi','Fatima Begum','Gopal Krishnan','Usha Patil','Ramesh Gupta','Meenakshi Sundaram',
  'Abdul Rahman','Savitri Mishra','Vinod Kulkarni','Leela Fernandes','Suresh Reddy','Kusum Agarwal','Narayan Hegde',
  'Pushpa Kaur','Dinesh Chauhan','Annamma Thomas','Bhaskar Pillai'];
const PROVIDER_NAMES = ['Sunita Rao','Priya Menon','Anjali Kumar','Rekha Shetty','Mary Joseph','Kavita Desai','Deepa Nair',
  'Asha Pillai','Ritu Bansal','Nisha Verma','Geeta Lobo','Pooja Thakur','Farah Khan','Shalini Gowda','Latha Raman',
  'Jyoti Antony','Rani Chacko','Bindu Shah','Neha Patel','Swati Hegde'];
const SLOT_TIMES = {
  Morning: ['8:30 am','9:00 am','9:30 am','10:00 am','10:30 am','11:00 am'],
  Afternoon: ['12:30 pm','1:00 pm','1:30 pm','2:00 pm','2:30 pm','3:00 pm'],
  Evening: ['4:30 pm','5:00 pm','5:30 pm','6:00 pm','6:30 pm','7:00 pm'],
};
const SLOT_HI = {Morning: 'subah', Afternoon: 'dopahar', Evening: 'shaam'};

function hashId(id){ let h = 7; for(const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; }
const patientIndex = {};
[...DATA.flagged.map(v => v.id), ...DATA.cascades.map(c => c.id)].forEach(id => {
  if(!(id in patientIndex)) patientIndex[id] = Object.keys(patientIndex).length;
});
// Visits outside today's flagged list (e.g. a nurse's full day) draw from a separate
// pool, so they never share a name with a flagged visit.
const OTHER_PATIENT_NAMES = ['Vasanthi Rao','Om Prakash Yadav','Gurpreet Kaur','Sushila Bhat','Francis D\'Souza',
  'Kamal Nath Tiwari','Radha Krishnan','Zarina Sheikh','Balbir Sandhu','Indira Joshi','Anand Kamath','Parvati Das',
  'Rafiq Ahmed','Sudha Murthy','Hemant Desai','Nirmala Rao','Jagdish Patel','Mariamma George','Satish Kulkarni',
  'Shobha Iyengar','Harish Malhotra','Rukmini Bose','Yusuf Qureshi','Chandrika Menon','Prem Saxena','Kalpana Reddy',
  'Bhupinder Gill','Shakuntala Pandey','Edwin Lobo','Vimala Natarajan'];
const otherPatients = {};   // patient_id -> name, assigned in order so names never clash
function patientName(id, patientId){
  if(id in patientIndex) return PATIENT_NAMES[patientIndex[id] % PATIENT_NAMES.length];
  const key = patientId || id;
  if(!(key in otherPatients)){
    const n = Object.keys(otherPatients).length;
    otherPatients[key] = OTHER_PATIENT_NAMES[n % OTHER_PATIENT_NAMES.length]
      + (n >= OTHER_PATIENT_NAMES.length ? ` ${Math.floor(n / OTHER_PATIENT_NAMES.length) + 1}` : '');
  }
  return otherPatients[key];
}
function firstName(id){ return patientName(id).split(' ')[0]; }
function provName(pid){
  const m = /PR0*(\d+)/.exec(String(pid || ''));
  return m ? PROVIDER_NAMES[(Number(m[1]) - 1) % PROVIDER_NAMES.length] : 'Provider';
}
function visitTime(id, slot){ const opts = SLOT_TIMES[slot] || SLOT_TIMES.Morning; return opts[hashId(id) % opts.length]; }
function phoneFor(id){ const d = String(id).replace(/\D/g, '').slice(-3).padStart(3, '0'); return `98••• ••${d}`; }
const WEEKDAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function fmtDate(iso){
  const d = new Date(iso + 'T00:00:00Z');
  return isNaN(d) ? iso : `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}
function timeMinutes(t){
  const m = /(\d+):(\d+) (am|pm)/.exec(t); if(!m) return 0;
  let h = Number(m[1]) % 12; if(m[3] === 'pm') h += 12; return h * 60 + Number(m[2]);
}
const isConfirmed = v => !!(v.patientSignal && v.patientSignal.intent === 'Confirm' && !v.patientSignal.escalate_to_human);
// The family turned down the proposed day: the visit is back with the coordinator.
const saidNo = v => !!(v.rescheduleProposal && execState[v.id] && execState[v.id].reply === 'no');
const isDoneToday = v => !!(execState[v.id] && execState[v.id].reply === 'yes');
const hasMessage = v => !!v.patientSignal && !isConfirmed(v);
const isReminder = v => /^(Call to confirm|Send confirmation)/.test(v.action || '');
// Acted on and now waiting for someone else (a family reply, the operations head).
const isWaiting = v => { const st = execState[v.id]; return !!(st && !st.running && !isDoneToday(v) && st.reply !== 'no'); };
const needsBackup = v => (v.action || '').startsWith('Reassign needed');
// Once "Find another day" has found a free nurse, the visit has a proposed fix and is no longer a gap.
const noBackup = v => needsBackup(v) && !v.rescheduleProposal;

// ---- Plain language -------------------------------------------------------
function plainWhy(r, sameDay = true){
  let m;
  if(/current provider, free on this date/.test(r)) return 'Usual nurse, free that day';
  if((m = /^(\d+) slot\(s\) free today$/.exec(r))) return `${m[1]} open slots ${sameDay ? 'today' : 'that day'}`;
  if((m = /^room in the same (\w+) slot$/.exec(r))) return `Free in the same ${m[1]} slot`;
  if((m = /^([\d.]+) km from patient \(inferred\)$/.exec(r))) return `About ${m[1]} km from the patient`;
  if((m = /^(.+?) — primary fit for (.+)$/.exec(r))) return `Qualified: ${m[1]}`;
  if(r === 'has treated this patient before') return 'Has treated this patient before';
  return r.charAt(0).toUpperCase() + r.slice(1);
}
const FAR_KM = 20;
const reasonHas = (v, re) => (v.reasons || []).some(r => re.test(r));
const isFar = v => (v.reasons || []).some(r => { const m = /^([\d.]+)km from clinician/.exec(r); return m && +m[1] >= FAR_KM; });
function plainReason(r){
  let m;
  if((m = /^(\d+) prior no-shows? before this visit/.exec(r))) return `Missed ${m[1]} visits before`;
  // Distance is on nearly every visit, so it is only a reason when the nurse is far away.
  if((m = /^([\d.]+)km from clinician/.exec(r))) return +m[1] >= FAR_KM ? `Nurse is far away: ${Math.round(+m[1])} km` : null;
  if(r === 'Evening slot') return 'Evening visit';
  if(r === 'Low message response rate so far') return 'Family rarely replies';
  return r;
}
function plainAction(v){
  const a = v.action || '';
  if(v.rescheduleProposal){
    const p = v.rescheduleProposal;
    const usual = (p.reasons || []).some(r => r.includes('current provider'));
    return `Move to ${fmtDate(p.new_date)} with ${provName(p.provider_id)}${usual ? ', the usual nurse' : ''}`;
  }
  if(a.startsWith('Call to confirm')) return 'Call the family to confirm';
  if(a.startsWith('Send confirmation')){
    // Same action underneath; the wording names the reason this visit is on the list.
    if(reasonHas(v, /prior no-show/)) return 'Send a reminder and ask for a second contact number';
    if(reasonHas(v, /^Evening slot/)) return 'Send a reminder this afternoon, before the evening visit';
    if(isFar(v)) return 'Send a reminder and check the nurse can reach on time';
    return 'Send a reminder and ask for a backup contact';
  }
  if(a.startsWith('Reassign needed')) return 'Needs a backup nurse, but none is free today';
  if(a.startsWith('Patient confirmed')) return 'Family confirmed. Nothing to do';
  return a;
}
function plainSteps(v){
  const steps = [];
  const sig = v.patientSignal || {};
  steps.push(`Read the message: the family wants to ${String(sig.intent || '').toLowerCase()}${sig.reason ? ` (${sig.reason.toLowerCase()})` : ''}${sig.next_week ? ', next week' : ''}.`);
  (v.agentTrace || []).forEach(line => {
    let m;
    if((m = /^Checked (\d{4}-\d\d-\d\d).*no eligible/.exec(line))) steps.push(`${fmtDate(m[1])}: no suitable nurse free.`);
    else if((m = /^Checked (\d{4}-\d\d-\d\d).*?(\d+) eligible/.exec(line)) && v.rescheduleProposal){
      steps.push(`${fmtDate(m[1])}: ${provName(v.rescheduleProposal.provider_id)} is free in the same ${v.time.toLowerCase()} slot.`);
    }
  });
  if(v.rescheduleProposal){
    const p = v.rescheduleProposal;
    steps.push(`Why ${provName(p.provider_id)}: ${(p.reasons || []).map(r => plainWhy(r, false).toLowerCase()).join('; ')}.`);
    steps.push('Proposed the new day. Nothing is booked until the family says yes.');
  }
  return steps;
}

// ---- Family message drafts --------------------------------------------------
// Templates, not AI: the wording is predictable and the coordinator edits it.
function draftFor(kind, ctx){
  const {name, service, time, slot, date, nurse, backup} = ctx;
  const n = name + ' ji';
  switch(kind){
    case 'reschedule': return {
      hi: `Namaste! ${n} ki ${service} visit ${date} ko ${SLOT_HI[slot] || ''} ${time} baje ${nurse} ke saath rakh sakte hain. Kya yeh theek rahega? "Haan" likh kar confirm karein, ya koi aur din batayein.`,
      en: `Hello! We can move ${name}'s ${service} visit to ${date} at ${time}, with ${nurse}. Does that work? Reply "Yes" to confirm, or suggest another day.`};
    case 'reminder': return {
      hi: `Namaste! Aaj ${time} baje ${n} ki ${service} visit hai. Kripya "Haan" likh kar confirm karein. Agar aap ghar par na hon, to parivaar ke kisi aur sadasya ka number bhej dein.`,
      en: `Hello! ${name}'s ${service} visit is today at ${time}. Please reply "Yes" to confirm. If you won't be home, please share another family member's number.`};
    case 'nobackup': return {
      hi: `Namaste! Aaj ${time} wali ${n} ki visit ke liye hum nurse confirm kar rahe hain. Agar zaroorat pade, to kya kal isi samay visit rakh sakte hain? Kripya batayein.`,
      en: `Hello! We are confirming a nurse for ${name}'s visit today at ${time}. If needed, could we move it to the same time tomorrow? Please let us know.`};
    case 'late': return backup ? {
      hi: `Namaste! ${n} ki ${time} wali visit ke liye aaj ${backup} aayengi, kyunki ${nurse} pichhli visit mein ruk gayi hain. Samay wahi rahega.`,
      en: `Hello! ${backup} will do ${name}'s ${time} visit today, as ${nurse} is held up at an earlier visit. The time stays the same.`} : {
      hi: `Namaste! ${nurse} pichhli visit se thodi der se nikal rahi hain. ${n} ki ${time} wali visit thodi late shuru ho sakti hai. Hum aapko update karte rahenge. Asuvidha ke liye kshama karein.`,
      en: `Hello! ${nurse} is running a little late from an earlier visit, so ${name}'s ${time} visit may start a bit late. We'll keep you updated. Sorry for the inconvenience.`};
    case 'replacement': return {
      hi: `Namaste! Aaj ${n} ki ${service} visit ke liye ${nurse} aayengi. Samay wahi rahega: ${time}.`,
      en: `Hello! ${nurse} will do ${name}'s ${service} visit today. The time stays the same: ${time}.`};
    case 'askday': return {
      hi: `Theek hai, koi baat nahi. ${n} ki ${service} visit ke liye aapko kaun sa din aur samay theek rahega? Hum us din nurse ki availability dekh kar confirm karenge.`,
      en: `No problem. Which day and time would suit you for ${name}'s ${service} visit? We will check a nurse is free then and confirm.`};
    case 'move': return {
      hi: `Namaste! Aaj ${n} ki visit ke liye koi nurse uplabdh nahi hai. Kya hum ${date} ko ${time} baje visit rakh sakte hain? Kripya batayein.`,
      en: `Hello! No nurse is free for ${name}'s visit today. Could we move it to ${date} at ${time}? Please let us know.`};
  }
  return null;
}
const draftState = {};   // id -> {lang, edits:{hi,en}, open}
function renderDraft(id, draft, opts = {}){
  if(!draft) return '';
  const st = draftState[id] || (draftState[id] = {lang: 'hi', edits: {}, open: !!opts.open});
  st.draft = draft;
  const text = st.edits[st.lang] ?? draft[st.lang];
  return `<details class="draft" ${st.open ? 'open' : ''} ontoggle="draftState['${escapeHtml(id)}'].open=this.open">
    <summary>${escapeHtml(opts.title || 'Message to family')} <span class="meta">ready to edit and send</span> <span class="tag rules">Template</span></summary>
    <div class="draft-body">
      <div class="seg" role="group" aria-label="Language">
        <button type="button" class="${st.lang === 'hi' ? 'on' : ''}" onclick="setDraftLang('${escapeHtml(id)}','hi')">Hinglish</button>
        <button type="button" class="${st.lang === 'en' ? 'on' : ''}" onclick="setDraftLang('${escapeHtml(id)}','en')">English</button>
      </div>
      <textarea id="draft-${escapeHtml(id)}" aria-label="${escapeHtml(opts.title || 'Message to family')}" rows="4" oninput="draftEdited('${escapeHtml(id)}', this.value)">${escapeHtml(text)}</textarea>
      <div class="draft-actions">
        <button type="button" class="ghost" onclick="editDraft('${escapeHtml(id)}')">Edit message</button>
        <button type="button" class="ghost" onclick="copyDraft('${escapeHtml(id)}', this)">Copy</button>
        <button type="button" class="link-btn" id="reset-${escapeHtml(id)}" ${st.edits[st.lang] === undefined ? 'hidden' : ''} onclick="resetDraft('${escapeHtml(id)}')">Edited · undo changes</button>
        <span class="meta">Not sent. Change anything you like, then copy it into WhatsApp.</span>
      </div>
    </div>
  </details>`;
}
// The draft was always editable, but a coordinator did not notice: make it an explicit action.
function editDraft(id){
  const ta = document.getElementById('draft-' + id);
  if(!ta) return;
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}
function draftEdited(id, value){
  const st = draftState[id];
  st.edits[st.lang] = value;
  const r = document.getElementById('reset-' + id);
  if(r) r.hidden = false;
}
function resetDraft(id){
  const st = draftState[id];
  delete st.edits[st.lang];
  const ta = document.getElementById('draft-' + id);
  if(ta) ta.value = st.draft[st.lang];
  const r = document.getElementById('reset-' + id);
  if(r) r.hidden = true;
}
function setDraftLang(id, lang){
  const st = draftState[id]; st.lang = lang;
  const ta = document.getElementById('draft-' + id);
  if(!ta) return;
  ta.value = st.edits[lang] ?? st.draft[lang];
  const r = document.getElementById('reset-' + id);
  if(r) r.hidden = st.edits[lang] === undefined;
  ta.closest('.draft').querySelectorAll('.seg button').forEach(b => b.classList.toggle('on', b.textContent === (lang === 'hi' ? 'Hinglish' : 'English')));
}
function copyDraft(id, btn){
  const ta = document.getElementById('draft-' + id);
  const done = () => { btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = 'Copy'; }, 1500); };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(ta.value).then(done, () => { ta.select(); document.execCommand('copy'); done(); });
  } else { ta.select(); document.execCommand('copy'); done(); }
}
function visitCtx(v){
  return {name: patientName(v.id), service: v.service, time: visitTime(v.id, v.time), slot: v.time};
}
function draftForVisit(v){
  const ctx = visitCtx(v);
  if(saidNo(v)) return draftFor('askday', ctx);
  if(v.rescheduleProposal){
    const p = v.rescheduleProposal;
    // A day the coordinator found: the family has not asked to move, so ask them rather than confirm.
    if(p.found) return draftFor('move', {...ctx, date: fmtDate(p.new_date)});
    return draftFor('reschedule', {...ctx, date: fmtDate(p.new_date), nurse: provName(p.provider_id)});
  }
  const a = v.action || '';
  if(a.startsWith('Call to confirm') || a.startsWith('Send confirmation')) return draftFor('reminder', ctx);
  if(noBackup(v)) return draftFor('nobackup', ctx);
  return null;
}

// ---- Action history and saved progress (this browser only) -------------------------
// A refresh must not wipe a coordinator's morning, so finished steps and the action
// history are kept in this browser's storage for the simulated day.
const STORE_KEY = 'careops-progress-v1';
const actionLog = [];
function saveProgress(){
  try {
    const done = {};
    Object.entries(execState).forEach(([id, st]) => { if(!st.running) done[id] = {reply: st.reply || null}; });
    const found = {};
    Object.entries(foundDays).forEach(([id, f]) => { if(f.date || f.none) found[id] = f; });
    const retry = {};
    DATA.flagged.forEach(v => { if(v.rescheduleProposal && v.rescheduleProposal.retry) retry[v.id] = {p: v.rescheduleProposal, declined: declinedDays[v.id] || []}; });
    localStorage.setItem(STORE_KEY, JSON.stringify({day: DATA.today, done, found, retry, cover: coverAsked, log: actionLog.slice(0, 60)}));
  } catch(e) {}
}
function loadProgress(){
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    if(!saved || saved.day !== DATA.today) return;
    Object.entries(saved.found || {}).forEach(([id, f]) => {
      const v = DATA.flagged.find(x => x.id === id);
      if(v){ foundDays[id] = f; applyFoundDay(v); }
    });
    Object.entries(saved.retry || {}).forEach(([id, r]) => {
      const v = DATA.flagged.find(x => x.id === id);
      if(v && r && r.p){ if(!v.origProposal) v.origProposal = v.rescheduleProposal; v.rescheduleProposal = r.p; declinedDays[id] = r.declined || []; }
    });
    Object.assign(coverAsked, saved.cover || {});
    Object.entries(saved.done || {}).forEach(([id, st]) => {
      const item = DATA.flagged.find(f => f.id === id)
        || DATA.cascades.map(c => ({...c, id: 'late-' + c.id})).find(c => c.id === id);
      if(!item) return;
      const steps = flowFor(item).steps;
      execState[id] = {running: false, stepIndex: steps.length - 1, steps, reply: st.reply || undefined};
    });
    (saved.log || []).forEach(a => actionLog.push(a));
  } catch(e) {}
}
function clearProgress(){
  Object.keys(execState).forEach(k => delete execState[k]);
  Object.keys(foundDays).forEach(k => delete foundDays[k]);
  Object.keys(nextAfterNo).forEach(k => delete nextAfterNo[k]);
  Object.keys(declinedDays).forEach(k => delete declinedDays[k]);
  Object.keys(coverAsked).forEach(k => delete coverAsked[k]);
  DATA.flagged.forEach(v => {
    if(v.origProposal){ v.rescheduleProposal = v.origProposal; delete v.origProposal; }
    else if(v.rescheduleProposal && v.rescheduleProposal.found) delete v.rescheduleProposal;
  });
  actionLog.length = 0;
  try { localStorage.removeItem(STORE_KEY); } catch(e) {}
  rerenderAll();
}
function logAction(text){
  const t = new Date();
  actionLog.unshift({time: t.toLocaleTimeString('en-IN', {hour: 'numeric', minute: '2-digit'}), text});
  saveProgress();
  renderHistory();
}
function renderHistory(){
  const el = document.getElementById('history');
  if(!el) return;
  el.innerHTML = actionLog.length ? `<div class="panel"><div class="panel-title">Your actions this session</div>
    ${actionLog.map(a => `<div class="hist-row"><span class="meta">${escapeHtml(a.time)}</span> ${escapeHtml(a.text)}</div>`).join('')}
    <div class="meta" style="margin-top:6px;">Saved in this browser, so a refresh keeps your progress. A real deployment stores an audit trail of who approved what, and when. <button type="button" class="link-btn" onclick="clearProgress()">Start the day again</button></div></div>` : '';
}

// ---- For the operations head: staffing gaps -----------------------------------------
function renderOwner(){
  const el = document.getElementById('owner');
  if(!el) return;
  const open = DATA.flagged.filter(v => !isConfirmed(v));
  const gaps = open.filter(noBackup);
  const bySlot = {};
  gaps.forEach(v => { bySlot[v.time] = (bySlot[v.time] || 0) + 1; });
  const lateNoBackup = DATA.cascades.filter(c => !(c.recovery || '').startsWith('Backup available')).length;
  const worst = Object.entries(bySlot).sort((a, b) => b[1] - a[1])[0];
  el.innerHTML = `<details class="panel owner"><summary class="panel-title">For the operations head: where today is short of nurses</summary>
    <p><b>${gaps.length} of ${open.length}</b> visits that need attention have <b>no backup nurse free</b> today${worst ? `, ${worst[1]} of them in the ${worst[0].toLowerCase()}` : ''}. ${lateNoBackup} of ${DATA.cascades.length} running-late visits also have no backup.</p>
    <div class="bars">${['Morning','Afternoon','Evening'].map(slot => `<div class="bar-row"><span>${slot}</span><div class="bar"><i style="width:${(bySlot[slot] || 0) / Math.max(1, gaps.length) * 100}%"></i></div><b>${bySlot[slot] || 0}</b></div>`).join('')}</div>
    <p class="meta">${worst ? `An extra ${worst[0].toLowerCase()} nurse would cover most of these gaps. ` : ''}This is one simulated day; a weekly view of missed visits and staff use is the next step for owners.</p>
  </details>`;
}

// ---- Operator view vs demo notes -------------------------------------------------
// A real coordinator sees today's work first. The portfolio framing (banner, pitch,
// "where AI is used") is for visitors and can be hidden; the choice is remembered.
function setOperatorView(on){
  document.body.classList.toggle('operator', on);
  try { localStorage.setItem('careops-operator-view', on ? '1' : '0'); } catch(e) {}
  render();
  if(on) window.scrollTo({top: 0, behavior: 'smooth'});
}
function initOperatorView(){
  let on = false;
  try { on = localStorage.getItem('careops-operator-view') === '1'; } catch(e) {}
  document.body.classList.toggle('operator', on);
}
function renderTodayLine(){
  const open = DATA.flagged.filter(v => !isConfirmed(v) && !isDoneToday(v));
  const msgs = open.filter(v => hasMessage(v) && !isWaiting(v)).length;
  const gaps = open.filter(noBackup).length;
  const late = DATA.cascades.length;
  const part = (n, one, many, action) => `<button type="button" class="today-chip" onclick="${action}"><b>${n}</b> ${n === 1 ? one : many}</button>`;
  const waitingN = open.filter(isWaiting).length;
  document.getElementById('today-line').innerHTML = [
    ...(waitingN ? [`<span class="today-wait"><b>${waitingN}</b> waiting on someone else</span>`] : []),
    part(msgs, 'family wrote in', 'families wrote in', "applyFilter('msg')"),
    part(gaps, 'visit has no backup nurse', 'visits have no backup nurse', "applyFilter('gap')"),
    part(late, 'nurse running late', 'nurses running late', "showView('cascade')"),
  ].join('<span class="dot-sep" aria-hidden="true">·</span>');
}
const SPECIAL_FILTERS = {msg: ['with a family message', hasMessage], gap: ['with no backup nurse', noBackup]};
function applyFilter(f){
  showView('risk');
  currentFilter = f;
  document.querySelectorAll('#risk-view .tab[data-f]').forEach(x => {
    const on = x.dataset.f === f; x.classList.toggle('active', on); x.setAttribute('aria-pressed', on);
  });
  render();
  document.getElementById('risk-view').scrollIntoView({behavior: 'smooth', block: 'start'});
}

// ---- "Needs you" list --------------------------------------------------------
let currentFilter = 'all';
let currentSort = 'risk';

function visitCard(v, startHere){
  const pct = Math.round(v.risk * 100);
  const label = v.tier === 'High' ? 'Likely to go wrong' : 'Worth a check';
  const time = visitTime(v.id, v.time);
  const sig = v.patientSignal;
  return `
    <div class="card visit ${escapeHtml(v.tier)}${startHere ? ' start' : ''}">
      ${startHere ? '<div class="start-here visitor">Start here: a family\'s Hinglish message, turned into a fix and a reply ready to send</div>' : ''}
      <div class="card-top">
        <div>
          <div class="visit-title">${escapeHtml(patientName(v.id))}</div>
          <div class="meta facts"><span>${escapeHtml(v.service)}</span><span><b>${escapeHtml(time)}</b></span><span>${escapeHtml(phoneFor(v.id))}</span></div>
        </div>
        <span class="badge ${escapeHtml(v.tier)}" title="Model score ${pct}%">${label}</span>
      </div>
      <div class="reasons">${v.reasons.map(plainReason).filter(Boolean).map(r => `<span>${escapeHtml(r)}</span>`).join('')}</div>
      ${sig ? `
      <div class="signal">
        <div class="meta">${escapeHtml(sig.channel)} from the family · <span class="tag ${sig.source === 'rule' ? 'rules' : 'ai'}">${sig.source === 'rule' ? 'Read by rules' : 'Read by AI'}</span></div>
        <div class="quote">"${escapeHtml(sig.message)}"</div>
        <div style="margin-top:4px;"><b>${escapeHtml(sig.intent === 'Reschedule' ? 'Wants to reschedule' : sig.intent)}</b>${sig.reason ? ' · ' + escapeHtml(sig.reason) : ''}${sig.next_week ? ' · next week' : ''}</div>
        ${v.agentTrace ? `<details class="trace"><summary>How CareOps decided</summary><ol>${plainSteps(v).map(l => `<li>${escapeHtml(l)}</li>`).join('')}</ol>
          <details class="trace tech"><summary>Technical log</summary><ol>${v.agentTrace.map(l => `<li>${escapeHtml(l)}</li>`).join('')}</ol></details></details>` : ''}
      </div>` : ''}
      ${renderDraft(v.id, draftForVisit(v), {open: !!v.rescheduleProposal})}
      ${renderActionRow(v)}
      <div class="id-line">Visit ${escapeHtml(v.id)}</div>
    </div>`;
}

function render(){
  const list = document.getElementById('list');
  const special = SPECIAL_FILTERS[currentFilter];
  let items = DATA.flagged.filter(v => !isConfirmed(v) && !isDoneToday(v)
    && (currentFilter === 'all' || (special ? special[1](v) : v.tier === currentFilter)));
  document.getElementById('filter-note').innerHTML = special
    ? `<div class="filter-note">Showing ${items.length} visit${items.length === 1 ? '' : 's'} ${special[0]} · <button type="button" class="link-btn" onclick="applyFilter('all')">Show all</button></div>` : '';
  if(currentSort === 'time') items = [...items].sort((a, b) => timeMinutes(visitTime(a.id, a.time)) - timeMinutes(visitTime(b.id, b.time)));
  // Pin the clearest example first so a new visitor sees the core loop straight away.
  const operator = document.body.classList.contains('operator');
  const pinned = !operator && currentFilter === 'all' && currentSort === 'risk' ? items.find(v => v.rescheduleProposal && !v.rescheduleProposal.found) : null;
  if(pinned) items = [pinned, ...items.filter(v => v !== pinned)];
  const todo = items.filter(v => !isWaiting(v)), waiting = items.filter(isWaiting);
  list.innerHTML = (todo.length ? todo.map(v => visitCard(v, v === pinned)).join('')
      : `<div class="empty">${waiting.length ? 'Nothing left to act on in this view. The visits below are waiting on someone else.' : 'Nothing in this view.'}</div>`)
    + (waiting.length ? `<div class="group-head">Waiting on someone else (${waiting.length})</div>` + waiting.map(v => visitCard(v, false)).join('') : '');
  const doneItems = DATA.flagged.filter(isDoneToday);
  document.getElementById('done').innerHTML = doneItems.length ? `
    <details class="confirmed-group done-group" open>
      <summary>Done today (${doneItems.length})</summary>
      ${doneItems.map(v => `<div class="conf-row"><div><b>${escapeHtml(patientName(v.id))}</b> · ${escapeHtml(v.service)}<div class="meta">${v.rescheduleProposal
        ? `Moved to ${escapeHtml(fmtDate(v.rescheduleProposal.new_date))}, ${escapeHtml(visitTime(v.id, v.time))} with ${escapeHtml(provName(v.rescheduleProposal.provider_id))}. Family and nurse both confirmed.`
        : `Family confirmed today's ${escapeHtml(visitTime(v.id, v.time))} visit.`}</div></div><span class="badge Low">Done</span></div>`).join('')}
    </details>` : '';
  const conf = DATA.flagged.filter(isConfirmed);
  document.getElementById('confirmed').innerHTML = conf.length ? `
    <details class="confirmed-group">
      <summary>Already confirmed by the family (${conf.length})</summary>
      ${conf.map(v => `<div class="conf-row"><div><b>${escapeHtml(patientName(v.id))}</b> · ${escapeHtml(v.service)} · ${escapeHtml(visitTime(v.id, v.time))}<div class="meta">${escapeHtml(v.patientSignal.channel)}: "${escapeHtml(v.patientSignal.message)}"</div></div><span class="badge Low">Confirmed</span></div>`).join('')}
    </details>` : '';
  renderOwner();
  renderHistory();
  renderTodayLine();
  renderSummary();
}

// ---- What approving does ------------------------------------------------------
// Order matters: the family is asked first, a nurse is told only after a yes, and
// nothing is ever marked handled while a visit is still unassigned.
const execState = {};

function flowFor(v){
  if(v.rescheduleProposal){
    const p = v.rescheduleProposal, nurse = provName(p.provider_id);
    return {button: 'Approve', done: 'Waiting for family', doneClass: 'wait', steps: [
      'Message to the family is ready above. Send it from WhatsApp',
      `Slot on ${fmtDate(p.new_date)} held for ${nurse}. She is not told yet`,
      'Waiting for the family to say yes',
      `After a yes, ${nurse} is told and the visit moves. Until then the schedule is unchanged`]};
  }
  const a = v.action || '';
  if(a.startsWith('Call to confirm') || a.startsWith('Send confirmation')){
    return {button: 'Approve', done: 'Reminder ready', doneClass: 'wait', steps: [
      'Reminder is ready above. Send it from WhatsApp, or call',
      'Follow-up set: call the family if there is no reply in 2 hours']};
  }
  if(noBackup(v)){
    return {button: 'Escalate', done: 'Escalated · unassigned', doneClass: 'warn', steps: [
      'Escalated to the operations head',
      'Still unassigned. It stays on this list until a nurse is confirmed']};
  }
  if(v.recovery && v.recovery.startsWith('Backup available')){
    const backup = provName(v.recovery);
    return {button: 'Approve', done: `Waiting for ${backup}`, doneClass: 'wait', steps: [
      `${backup} asked to cover. Waiting for her yes`,
      'Message to the family is ready above. Send it after she agrees',
      `After her yes, the original nurse is told to skip this visit`]};
  }
  return {button: 'Approve', done: 'Logged, not resolved', doneClass: 'warn', steps: ['Logged for follow-up. Not resolved yet']};
}

function renderActionRow(v){
  const declined = saidNo(v);
  const label = declined ? 'Ask the family which day suits them, or offer the next free day'
    : (v.recovery ? (v.recovery.startsWith('Backup available') ? `Send ${provName(v.recovery)} instead` : 'No backup nurse free. Agree a later time with the family') : plainAction(v));
  const flow = flowFor(v);
  const st = execState[v.id];
  let stepsHtml = '';
  if(st && !declined){
    stepsHtml = `<div class="exec-steps">` + flow.steps.map((s, i) => {
      const done = i < st.stepIndex || (i === st.stepIndex && !st.running);
      const active = i === st.stepIndex && st.running;
      const mark = done ? '✓' : (active ? '…' : '·');
      return `<div class="${done ? 'ok' : ''}" style="opacity:${i <= st.stepIndex ? 1 : 0.4}"><span class="mk">${mark}</span>${escapeHtml(s)}</div>`;
    }).join('') + `</div>`;
  }
  const isDone = st && st.stepIndex >= flow.steps.length - 1 && !st.running;
  let replyHtml = '';
  if(isDone && isReminder(v)){
    if(!st.reply){
      replyHtml = `<div class="reply-row"><span class="meta">When you hear back:</span>
        <button class="ghost" onclick="familyReplied('${escapeHtml(v.id)}','yes')">Family confirmed</button>
        <button class="ghost" onclick="familyReplied('${escapeHtml(v.id)}','no')">No reply</button></div>`;
    } else if(st.reply === 'no'){
      replyHtml = `<div class="exec-steps"><div><span class="mk">!</span>No reply to the reminder. Call ${escapeHtml(phoneFor(v.id))} now; if nobody answers, line up a backup contact before the nurse leaves.</div></div>`;
    }
  }
  if(isDone && v.rescheduleProposal){
    const p = v.rescheduleProposal, nurse = provName(p.provider_id);
    if(!st.reply){
      replyHtml = `<div class="reply-row"><span class="meta">When the family replies:</span>
        <button class="ghost" onclick="familyReplied('${escapeHtml(v.id)}','yes')">Family said yes</button>
        <button class="ghost" onclick="familyReplied('${escapeHtml(v.id)}','no')">Family said no</button></div>`;
    } else if(st.reply === 'yes'){
      replyHtml = `<div class="exec-steps"><div class="ok"><span class="mk">✓</span>${escapeHtml(nurse)} told about the new visit</div><div class="ok"><span class="mk">✓</span>Visit moved to ${escapeHtml(fmtDate(p.new_date))}, ${escapeHtml(visitTime(v.id, v.time))}. Done</div></div>`;
    } else {
      const nx = nextAfterNo[v.id] || {};
      replyHtml = `<div class="exec-steps"><div><span class="mk">!</span>Family said no to ${escapeHtml(fmtDate(p.new_date))}. The slot is released and ${escapeHtml(nurse)} was never told. The message above now asks which day suits them.</div>
        ${nx.none ? `<div><span class="mk">!</span>No suitable nurse is free in the 7 days after that either. Call the family to agree a day, then use Fix a visit.</div>` : ''}
        ${nx.error ? `<div><span class="mk">!</span>Could not check other days just now. Try again in a moment.</div>` : ''}</div>`;
    }
  }
  const replyDone = st && st.reply;
  const flowDone = replyDone ? (st.reply === 'yes' ? (v.rescheduleProposal ? 'Rescheduled' : 'Confirmed')
    : (v.rescheduleProposal ? 'Asking for another day' : 'Call the family')) : flow.done;
  const flowDoneClass = replyDone ? (st.reply === 'yes' ? 'done' : 'warn') : flow.doneClass;
  const btnLabel = !st ? flow.button : (st.running ? 'Working…' : (isDone ? flowDone : flow.button));
  const disabled = st && (st.running || isDone);
  const canAct = !v.recovery || v.recovery.startsWith('Backup available');
  const fd = foundDays[v.id] || {};
  const nxs = nextAfterNo[v.id] || {};
  const secondary = declined ? (nxs.none ? '' : `<button class="approve" ${nxs.checking ? 'disabled' : ''} onclick="findNextAfterNo('${escapeHtml(v.id)}')">${nxs.checking ? 'Checking the next 7 days…' : 'Offer the next free day'}</button>`)
    : !noBackup(v) || fd.none || isDone ? ''
    : `<button class="ghost" ${fd.checking ? 'disabled' : ''} onclick="findAnotherDay('${escapeHtml(v.id)}')">${fd.checking ? 'Checking the next 7 days…' : 'Find another day'}</button>`;
  const fdNote = !noBackup(v) ? '' : fd.none
    ? `<div class="exec-steps"><div><span class="mk">!</span>No nurse is free in the next 7 days. Escalate to the operations head or a partner agency.</div></div>`
    : (fd.error ? `<div class="exec-steps"><div><span class="mk">!</span>Could not check other days just now. Try again in a moment.</div></div>` : '');
  return `
    <div class="action-row">
      ${elsewhereNote(v.id, 'needs')}
      ${(declinedDays[v.id] || []).length ? `<div class="exec-steps"><div><span class="mk">i</span>Family already said no to ${declinedDays[v.id].map(d => escapeHtml(fmtDate(d))).join(', ')}.</div></div>` : ''}
      <div class="action-main">
        <div class="action">Suggested: <b>${escapeHtml(label)}</b></div>
        <div class="btns">${secondary}${canAct && !declined ? `<button class="approve ${isDone ? flowDoneClass : ''}" ${disabled ? 'disabled' : ''} onclick="approveItem('${escapeHtml(v.id)}')">${escapeHtml(btnLabel)}</button>` : ''}</div>
      </div>
      ${fdNote}
      ${stepsHtml}
      ${replyHtml}
    </div>`;
}

function rerenderAll(){
  render();
  if(document.getElementById('cascade-view').style.display !== 'none') renderCascade();
}
function familyReplied(id, answer){
  execState[id].reply = answer;
  if(draftState[id]) draftState[id].edits = {};
  saveProgress();
  if(answer === 'yes') setTimeout(() => {
    const el = document.getElementById('done');
    if(el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
  }, 60);
  const v = DATA.flagged.find(f => f.id === id);
  logAction(v.rescheduleProposal
    ? `${patientName(id)}: family said ${answer}${answer === 'yes' ? `, visit moved to ${fmtDate(v.rescheduleProposal.new_date)}` : ', asking for another day'}`
    : `${patientName(id)}: ${answer === 'yes' ? 'family confirmed the visit' : 'no reply to the reminder, call needed'}`);
  rerenderAll();
}
function approveItem(id){
  const item = DATA.flagged.find(f => f.id === id)
    || DATA.cascades.map(c => ({...c, id: 'late-' + c.id})).find(c => c.id === id);
  execState[id] = {running: true, stepIndex: 0, steps: flowFor(item).steps};
  const flow = flowFor(item);
  const who = patientName(String(id).replace(/^late-/, ''));
  logAction(`${who}: ${flow.button === 'Escalate' ? 'escalated, still unassigned' : flow.done.toLowerCase()}`);
  rerenderAll();
  runStep(id);
}
function runStep(id){
  const st = execState[id];
  if(!st) return;
  setTimeout(() => {
    if(st.stepIndex < st.steps.length - 1){ st.stepIndex += 1; rerenderAll(); runStep(id); }
    else { st.running = false; saveProgress(); rerenderAll(); }
  }, 550);
}

// ---- Running late ---------------------------------------------------------------
function renderCascade(){
  const el = document.getElementById('cascade-view');
  el.innerHTML = `
    <div class="meta" style="margin-bottom:16px;">When a nurse runs over at one visit, the next family is often the last to know. A visit appears here once the delay has used up most of the spare minutes before the next visit.</div>
    ${DATA.cascades.map(c => {
      const nurse = provName(c.provider);
      const name = patientName(c.id);
      const time = visitTime(c.id, c.slot);
      const slack = Math.max(0, Number(c.buffer) - Number(c.delay));
      const hasBackup = (c.recovery || '').startsWith('Backup available');
      const backup = hasBackup ? provName(c.recovery) : null;
      const why = hasBackup ? c.recovery.replace(/^Backup available: PR\d+ — /, '').split(', ').map(r => plainWhy(r)).join(' · ') : '';
      const draft = draftFor('late', {name, service: c.service, time, slot: c.slot, nurse, backup});
      return `
      <div class="cascade-card">
        <div class="cascade-head">
          <b>${escapeHtml(nurse)} is ${Number(c.delay)} min behind</b>
          <span class="chip ${c.notified ? 'ok' : 'gap'}">${c.notified ? 'Family told' : 'Family not told yet'}</span>
        </div>
        <div class="meta">Next: <b>${escapeHtml(name)}</b> · ${escapeHtml(c.service)} · ${escapeHtml(time)}</div>
        <div class="flow">
          <div class="step problem"><div class="dot"></div><div>There was a <b>${c.buffer} min</b> gap before ${escapeHtml(firstName(c.id))}'s visit, so only ${slack} min is left to spare.${c.locGap ? ' The previous address was hard to find, which added to the delay.' : ''}</div></div>
          <div class="step ${hasBackup ? 'fix' : 'problem'}"><div class="dot"></div><div>${hasBackup ? `Backup: <b>${escapeHtml(backup)}</b> · ${escapeHtml(why)}` : 'No backup nurse is free. Tell the family now and agree a later start.'}</div></div>
        </div>
        ${renderDraft('late-' + c.id, draft, {open: true})}
        ${hasBackup ? renderActionRow({...c, id: 'late-' + c.id}) : ''}
        ${elsewhereNote(c.id, 'late')}
        <div class="id-line">Visit ${escapeHtml(c.id)}</div>
      </div>`;
    }).join('')}`;
}

// ---- Visit reports ------------------------------------------------------------
const VITAL_LABEL = {bp_systolic: 'BP', bp_diastolic: 'BP', blood_sugar_mg_dl: 'Sugar', spo2_pct: 'Oxygen',
  pulse_bpm: 'Pulse', temperature_f: 'Temperature'};
const VR_TITLES = {VR01: 'Routine visit, all clear', VR07: 'Companion visit, no readings', VR14: 'Hindi numbers the AI misheard',
  VR20: 'Low sugar the AI missed', VR22: 'A fall, with normal readings'};
function humanReason(r){
  if(/external LLM calls are disabled|LLM is not configured/.test(r)) return 'The live AI is off on this free public demo, so a person reviews every note.';
  if(r.startsWith('family update makes promises')) return `The AI's family update promises something the caregiver never said (${r.split(':')[1].trim()}). Check before sharing.`;
  if(r.startsWith('family update adds medical words')) return `The AI's family update uses medical words the caregiver never said (${r.split(':')[1].trim()}). Check before sharing.`;
  if(/report could not be generated/.test(r)) return 'The AI could not read this note, so a person reviews it.';
  if(r.startsWith('vital value not found')){
    const fields = r.split(':')[1].split(',').map(s => VITAL_LABEL[s.trim()] || s.trim());
    return `The AI reported ${[...new Set(fields)].join(' and ')}, but those numbers are not written in the note. Check before sharing.`;
  }
  if(r.startsWith('red flag: ')){
    const parts = r.slice(10).split(', ').map(p => {
      let m;
      if((m = /^keyword:(.+)$/.exec(p))) return `mentions "${m[1]}"`;
      if((m = /^(?:note mentions )?([a-z_]+)=([\d.]+)$/.exec(p))) return `${VITAL_LABEL[m[1]] || m[1]} ${Number(m[2])} is outside the safe range`;
      return p;
    });
    return 'Red flag: ' + [...new Set(parts)].join('; ') + '.';
  }
  return r;
}
function readingChips(readings){
  const out = [];
  const rs = readings || [];
  const rank = s => ({'red flag': 2, 'outside usual range': 1, 'usual': 0})[s] || 0;
  for(let i = 0; i < rs.length; i++){
    const r = rs[i];
    let label, status = r.status;
    if(r.vital === 'bp_systolic' && rs[i + 1] && rs[i + 1].vital === 'bp_diastolic'){
      label = `BP ${r.value}/${rs[i + 1].value}`;
      if(rank(rs[i + 1].status) > rank(status)) status = rs[i + 1].status;
      i++;
    } else {
      label = `${VITAL_LABEL[r.vital] || r.vital} ${r.value}`;
    }
    const cls = status === 'red flag' ? 'bad' : status === 'outside usual range' ? 'warn' : 'good';
    const tag = status === 'red flag' ? 'red flag' : status === 'outside usual range' ? 'outside usual range' : 'usual';
    out.push(`<span class="vr-chip ${cls}">${escapeHtml(label)} · ${tag}</span>`);
  }
  return out.join('');
}
function vrChips(obj, cls){
  return Object.entries(obj || {}).map(([k, v]) => `<span class="vr-chip ${cls}">${escapeHtml(k)} ${escapeHtml(String(v))}</span>`).join('');
}
// Family update timing: send now in the family's daytime (8 am to 9 pm), otherwise queue for 8 am.
const REPORT_READY_IST = 11 * 60 + 30;
function fmtClock(mins){
  const m = ((mins % 1440) + 1440) % 1440; let h = Math.floor(m / 60); const mm = String(m % 60).padStart(2, '0');
  const ap = h >= 12 ? 'pm' : 'am'; h = h % 12 || 12; return `${h}:${mm} ${ap}`;
}
function deliveryLine(){
  const sel = document.getElementById('family-tz');
  const off = sel ? Number(sel.value) : 330;
  const place = sel ? sel.options[sel.selectedIndex].text : 'India';
  const local = REPORT_READY_IST - 330 + off;
  const lm = ((local % 1440) + 1440) % 1440;
  if(lm >= 8 * 60 && lm <= 21 * 60) return `Sent at ${fmtClock(lm)} ${place === 'India' ? '' : place + ' time'}`.trim();
  const sendIst = 8 * 60 - off + 330;
  return `Queued: arrives at 8:00 am ${place} time (${fmtClock(sendIst)} IST), not at ${fmtClock(lm)}`;
}
function caregiverNote(r){
  const reasons = r.reasons || [];
  if(!r.needs_review) return null;
  const unver = reasons.find(x => x.startsWith('vital value not found'));
  if(unver){
    const names = [...new Set(unver.split(':')[1].split(',').map(s => VITAL_LABEL[s.trim()] || s.trim()))]
      .map(n => n === 'BP' ? 'BP' : n.toLowerCase());
    const vitals = names.join(' and ');
    return {hi: `Shukriya! Kripya ${vitals} ki reading number mein boliye, jaise "oxygen 97", aur note dobara bhej dijiye.`,
            en: `Thank you! Please say the ${vitals} ${names.length > 1 ? 'readings as numbers' : 'reading as a number'}, like "oxygen 97", and send the note again.`};
  }
  if(reasons.some(x => x.startsWith('red flag'))) return {
    hi: 'Shukriya, aapne sahi samay par bataya. Coordinator aapko 15 minute mein call karenge. Tab tak marij ke saath rahiye.',
    en: 'Thank you for flagging this. Your coordinator will call you within 15 minutes. Please stay with the patient until then.'};
  return null;
}
function vrCard(r, title, point, kind){
  const status = r.needs_review
    ? '<span class="badge High">Needs your review</span>'
    : '<span class="badge Low">Update sent to family</span>';
  const summary = r.family_summary
    ? ''
    : (r.draft_family_summary ? `<div class="meta" style="margin-top:8px;"><b>Family update on hold</b> until you review it: ${escapeHtml(r.draft_family_summary)}</div>` : '');
  return `<div class="card">
    <div style="display:flex; justify-content:space-between; gap:8px; align-items:center;">
      <div style="font-weight:700;">${escapeHtml(VR_TITLES[title] || title)}${kind ? ` <span class="kind">${escapeHtml(kind)}</span>` : ''}${VR_TITLES[title] ? ` <span class="id-inline">${escapeHtml(title)}</span>` : ''}</div>${status}
    </div>
    ${point ? `<div class="meta" style="margin-top:3px;">${escapeHtml(point)}</div>` : ''}
    <div class="vr-quote">${escapeHtml(r.transcript || '')}</div>
    ${(r.readings || []).length ? `<div class="meta">Readings in the note</div><div class="vr-vitals">${readingChips(r.readings)}</div>` : ''}
    ${r.model_vitals && Object.keys(r.model_vitals).length ? `<div class="meta">What the AI reported</div><div class="vr-vitals">${vrChips(r.model_vitals, '')}</div>` : ''}
    ${Object.keys(r.unverified || {}).length ? `<div class="meta">Not written in the note, held back</div><div class="vr-vitals">${vrChips(r.unverified, 'bad')}</div>` : ''}
    ${(r.reasons || []).length ? `<ul class="why">${r.reasons.map(x => `<li>${escapeHtml(humanReason(x))}</li>`).join('')}</ul>` : ''}
    ${summary}
    ${r.isExample !== false ? `<div class="family-view"><div class="meta"><b>What the family sees</b> · ${escapeHtml(deliveryLine())}</div>
      <div class="bubble">${escapeHtml(r.family_summary || 'Today\'s visit is done. Your coordinator is checking the visit report and will share it with you shortly.')}</div></div>` : ''}
    ${renderDraft('cg-' + (r.id || title), caregiverNote(r), {title: 'Message to the caregiver'})}
  </div>`;
}
function renderVisitReports(){
  const list = document.getElementById('vr-list');
  if(!VR_EXAMPLES){ list.innerHTML = '<div class="empty">No recorded examples in this build.</div>'; return; }
  document.getElementById('vr-provenance').textContent =
    `Examples recorded from a real AI run (${VR_EXAMPLES.model}, ${fmtDate(VR_EXAMPLES.recorded_at.slice(0, 10))}).`;
  list.innerHTML = VR_EXAMPLES.examples.map(e => vrCard({...e, readings: e.readings}, e.id, e.point,
    /companion visit/i.test(e.transcript) ? 'Companion visit' : 'Nursing visit')).join('');
}
async function tryVisitReport(){
  const text = document.getElementById('vr-input').value.trim();
  const el = document.getElementById('vr-result');
  if(!text){ el.innerHTML = '<div class="empty">Type a visit note first.</div>'; return; }
  el.innerHTML = '<div class="empty">Reading the note… (the first request after a quiet spell can take up to a minute)</div>';
  try {
    const res = await fetch('/api/visit-report', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({transcript: text})});
    const data = await res.json().catch(() => null);
    if(!res.ok || !data){ el.innerHTML = '<div class="empty">CareOps could not read that note. Please try again.</div>'; return; }
    const labels = {bp_systolic: 'BP sys', bp_diastolic: 'BP dia', blood_sugar_mg_dl: 'Sugar', spo2_pct: 'Oxygen', pulse_bpm: 'Pulse', temperature_f: 'Temp'};
    const pick = o => Object.fromEntries(Object.entries(o || {}).filter(([, x]) => x !== null).map(([k, x]) => [labels[k] || k, x]));
    el.innerHTML = vrCard({transcript: text, model_vitals: pick(data.vitals), unverified: pick(data.unverified_vitals),
      readings: data.readings, needs_review: data.needs_coordinator_review, reasons: data.review_reasons,
      family_summary: data.family_summary, draft_family_summary: data.draft_family_summary, id: 'own'}, 'Your note', null);
  } catch(e){
    el.innerHTML = `<div class="empty">Could not reach CareOps (${escapeHtml(e.message)}). It may still be starting up.</div>`;
  }
}

// ---- Voice note recording (speech-to-text is off on the public demo) -----------------
let recorder = null, chunks = [];
async function toggleRecording(){
  const btn = document.getElementById('record-btn');
  const el = document.getElementById('vr-result');
  if(recorder && recorder.state === 'recording'){ recorder.stop(); btn.textContent = 'Record a voice note'; return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = e => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      el.innerHTML = '<div class="empty">Sending the voice note…</div>';
      const form = new FormData();
      form.append('file', new Blob(chunks, {type: 'audio/webm'}), 'note.webm');
      const res = await fetch('/api/visit-report/audio', {method: 'POST', body: form}).catch(() => null);
      if(!res || !res.ok){
        el.innerHTML = '<div class="empty">Voice notes need speech-to-text, which is off on this free public demo. Type the note instead, or run CareOps locally with a free Groq key to try voice.</div>';
        return;
      }
      const data = await res.json();
      document.getElementById('vr-input').value = data.transcript || '';
      tryVisitReport();
    };
    recorder.start();
    btn.textContent = 'Stop and send';
  } catch(e){
    el.innerHTML = '<div class="empty">The microphone is not available in this browser. Type the note instead.</div>';
  }
}
if(window.MediaRecorder && navigator.mediaDevices){ document.getElementById('record-btn').hidden = false; }

// ---- Tabs and filters ----------------------------------------------------------
function showView(v){
  document.querySelectorAll('#view-tabs .tab').forEach(x => {
    const on = x.dataset.v === v;
    x.classList.toggle('active', on); x.setAttribute('aria-selected', on); x.tabIndex = on ? 0 : -1;
  });
  document.getElementById('risk-view').style.display = v === 'risk' ? '' : 'none';
  document.getElementById('cascade-view').style.display = v === 'cascade' ? '' : 'none';
  document.getElementById('live-view').style.display = v === 'live' ? '' : 'none';
  document.getElementById('vr-view').style.display = v === 'vr' ? '' : 'none';
  if(v === 'cascade') renderCascade();
  if(v === 'vr') renderVisitReports();
  if(v === 'live') liveInit();
}
document.querySelectorAll('#view-tabs .tab').forEach(t => t.addEventListener('click', () => showView(t.dataset.v)));
document.getElementById('view-tabs').addEventListener('keydown', e => {
  if(!['ArrowRight', 'ArrowLeft'].includes(e.key)) return;
  const tabs = [...document.querySelectorAll('#view-tabs .tab')];
  const i = tabs.findIndex(t => t.classList.contains('active'));
  const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
  showView(next.dataset.v); next.focus();
});
document.querySelectorAll('#risk-view .tab[data-f]').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('#risk-view .tab[data-f]').forEach(x => { x.classList.remove('active'); x.setAttribute('aria-pressed', 'false'); });
  t.classList.add('active'); t.setAttribute('aria-pressed', 'true'); currentFilter = t.dataset.f; render();
}));
document.querySelectorAll('#risk-view .tab[data-s]').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('#risk-view .tab[data-s]').forEach(x => { x.classList.remove('active'); x.setAttribute('aria-pressed', 'false'); });
  t.classList.add('active'); t.setAttribute('aria-pressed', 'true'); currentSort = t.dataset.s; render();
}));

// ---- Fix a visit (calls the FastAPI backend in main.py) ---------------------------
let liveInitialized = false;
const LAST_DEMO_DATE = '2026-10-28';

function liveInit(){
  if(liveInitialized) return;
  liveInitialized = true;
  const sel = document.getElementById('live-appt');
  sel.innerHTML = DATA.flagged.filter(v => !isConfirmed(v)).map(v =>
    `<option value="${escapeHtml(v.id)}">${escapeHtml(patientName(v.id))} · ${escapeHtml(v.service)}, ${escapeHtml(visitTime(v.id, v.time))}</option>`).join('');
  // Open on a visit the snapshot already knows has a backup provider, so the first
  // click shows a recovery; visits without one remain selectable.
  const withBackup = (DATA.cascades || []).find(c => (c.recovery || '').startsWith('Backup available')
    && DATA.flagged.some(v => v.id === c.id));
  if(withBackup) sel.value = withBackup.id;
  renderIncidentSummary();
  const dates = [];
  for(let i = 1; i <= 60; i++){ const d = addDays(DATA.today, i); dates.push(`<option value="${d}">${fmtDate(d)}</option>`); }
  document.getElementById('recovery-date').innerHTML = dates.join('');
  document.getElementById('nurse-select').innerHTML = PROVIDER_NAMES.map((n, i) => {
    const pid = 'PR' + String(i + 1).padStart(3, '0');
    return `<option value="${pid}">${escapeHtml(n)} (${pid})</option>`;
  }).join('');
  document.getElementById('nurse-select').value = 'PR016';
}
function setFixMode(mode){
  document.getElementById('nurse-card').hidden = mode !== 'nurse';
  document.getElementById('visit-card').hidden = mode !== 'visit';
  document.getElementById('mode-nurse').classList.toggle('on', mode === 'nurse');
  document.getElementById('mode-visit').classList.toggle('on', mode === 'visit');
  document.getElementById('mode-nurse').setAttribute('aria-pressed', mode === 'nurse');
  document.getElementById('mode-visit').setAttribute('aria-pressed', mode === 'visit');
}
async function coverNurseDay(){
  const pid = document.getElementById('nurse-select').value;
  const el = document.getElementById('nurse-result');
  const btn = document.getElementById('nurse-button');
  btn.disabled = true; btn.textContent = 'Checking who is free…';
  el.innerHTML = '<div class="empty">Finding her visits and checking cover… (the first request after a quiet spell can take up to a minute)</div>';
  try {
    const res = await fetch('/api/nurse-day/' + encodeURIComponent(pid));
    const day = await res.json();
    if(!res.ok) throw new Error(day.detail || res.statusText);
    const used = {};
    const rows = [];
    for(const v of day.visits){
      const r = await fetch('/api/recover', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({appointment_id: v.appointment_id, target_date: day.date})});
      const data = r.ok ? await r.json() : {candidates: []};
      // Greedy: take the best candidate who still has room after earlier assignments.
      const pick = (data.candidates || []).find(c => {
        const m = /(\d+) slot\(s\) free today/.exec((c.reasons || []).join(' '));
        const room = m ? Number(m[1]) : 1;
        return (used[c.provider_id] || 0) < room;
      });
      if(pick) used[pick.provider_id] = (used[pick.provider_id] || 0) + 1;
      rows.push({v, pick});
    }
    const covered = rows.filter(r => r.pick).length;
    const nurseOut = provName(pid);
    el.innerHTML = `
      <div class="card result ${covered === rows.length ? 'ok' : 'warn'}">
        <div style="font-weight:700;">${covered} of ${rows.length} of ${escapeHtml(nurseOut)}'s visits can be covered today</div>
        <div class="meta" style="margin-bottom:8px;">${rows.length - covered ? `${rows.length - covered} need another day. They stay on your list until a nurse is confirmed.` : 'Confirm each cover nurse first, then message the families.'}</div>
        ${rows.length - covered > 1 ? `<button class="ghost" style="margin-bottom:6px;" onclick="coverAllLater(this)">Find days for all ${rows.length - covered}</button>` : ''}
        ${rows.map(({v, pick}) => {
          const name = patientName(v.appointment_id, v.patient_id), time = visitTime(v.appointment_id, v.time_slot);
          const msg = pick ? draftFor('replacement', {name, service: v.service_type, time, slot: v.time_slot, nurse: provName(pick.provider_id)}) : null;
          return `<div class="cover-row">
            <div><b>${escapeHtml(name)}</b> · ${escapeHtml(v.service_type)} · ${escapeHtml(time)}
              <div class="meta">${pick ? `Cover: <b>${escapeHtml(provName(pick.provider_id))}</b> · ${(pick.reasons || []).slice(0, 2).map(x => escapeHtml(plainWhy(x))).join(' · ')}` : 'No nurse with room today'}</div></div>
            ${pick ? `<span class="btns"><button class="approve" data-appt="${escapeHtml(v.appointment_id)}" data-nurse="${escapeHtml(provName(pick.provider_id))}" ${coverAsked[v.appointment_id] ? 'disabled' : ''} onclick="askCover(this, this.dataset.appt, this.dataset.nurse)">${coverAsked[v.appointment_id] ? `Waiting for ${escapeHtml(coverAsked[v.appointment_id])}` : `Ask ${escapeHtml(provName(pick.provider_id).split(' ')[0])} to cover`}</button><button class="ghost" onclick="copyText(this, ${escapeHtml(JSON.stringify(msg.hi))})">Copy message</button></span>`
                   : `<button class="ghost later-btn" data-appt="${escapeHtml(v.appointment_id)}" onclick="coverLater(this, this.dataset.appt)">Find another day</button>`}
          </div>`;
        }).join('')}
        <div class="meta" style="margin-top:8px;">Ask each cover nurse first, then send the family message. In this demo nothing is booked and no one is contacted.</div>
      </div>`;
    logAction(`${nurseOut} out: cover found for ${covered} of ${rows.length} visits`);
  } catch(e){
    el.innerHTML = `<div class="empty">Could not check cover (${escapeHtml(e.message)}). It may still be starting up.</div>`;
  }
  btn.disabled = false; btn.textContent = 'Find cover for all her visits';
}
async function coverAllLater(btn){
  btn.disabled = true; btn.textContent = 'Checking the next 7 days…';
  const pending = [...document.querySelectorAll('#nurse-result .later-btn')].filter(b => !b.disabled);
  for(const b of pending) await coverLater(b, b.dataset.appt);
  btn.textContent = 'Days found. Ask each family';
}
// Later-day offers made in this session, so one nurse is not offered for more
// visits on a day than she has room for. Keyed by date + nurse.
const laterUsed = {};
async function coverLater(btn, apptId){
  btn.disabled = true; btn.textContent = 'Checking…';
  const nurseOut = document.getElementById('nurse-select').value;
  for(let i = 1; i <= 7; i++){
    const date = addDays(DATA.today, i);
    const r = await fetch('/api/recover', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({appointment_id: apptId, target_date: date})}).catch(() => null);
    const data = r && r.ok ? await r.json() : null;
    // Skip the nurse who is out (she may still be unwell) and anyone already offered up to her room that day.
    const c = data && (data.candidates || []).find(x => {
      if(x.provider_id === nurseOut) return false;
      const m = /(\d+) slot\(s\) free/.exec((x.reasons || []).join(' '));
      return (laterUsed[date + x.provider_id] || 0) < (m ? Number(m[1]) : 1);
    });
    if(c){
      laterUsed[date + c.provider_id] = (laterUsed[date + c.provider_id] || 0) + 1;
      btn.outerHTML = `<span class="meta">${escapeHtml(fmtDate(date))} with <b>${escapeHtml(provName(c.provider_id))}</b>. Ask the family</span>`;
      return;
    }
  }
  btn.outerHTML = '<span class="badge High">No one free this week. Escalate</span>';
}
function copyText(btn, text){
  const done = () => { btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = 'Copy message'; }, 1500); };
  if(navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, done); else done();
}
async function liveCallApi(path, body, quiet){
  const el = document.getElementById('live-result');
  if(!quiet) el.innerHTML = '<div class="empty">Checking who is free… (the first request after a quiet spell can take up to a minute)</div>';
  try {
    const res = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await res.json().catch(() => null);
    if(!res.ok){
      const detail = (data && data.detail) || res.statusText;
      const friendly = /read.only|mutation|disabled|forbidden/i.test(String(detail))
        ? 'This public demo can recommend a fix, but cannot record an approval or change a schedule.'
        : 'CareOps could not complete that request. Please try again.';
      el.innerHTML = `<div class="empty">${escapeHtml(friendly)}</div>`;
      return null;
    }
    return data;
  } catch(e){
    el.innerHTML = `<div class="empty">Could not reach CareOps (${escapeHtml(e.message)}). It may still be starting up. Try again in a moment.</div>`;
    return null;
  }
}
function resetLiveResult(){ document.getElementById('live-result').innerHTML = ''; }
function updateRecoveryDate(){
  document.getElementById('recovery-date-wrap').style.display = document.getElementById('recovery-mode').value === 'future' ? 'block' : 'none';
  resetLiveResult();
}
function renderIncidentSummary(){
  const id = document.getElementById('live-appt').value;
  const visit = (DATA.flagged || []).find(v => v.id === id);
  const el = document.getElementById('incident-summary');
  if(!el) return;
  if(!visit){ el.innerHTML = '<div class="meta">Choose a visit to see its details.</div>'; return; }
  el.innerHTML = `
    <div class="card-top">
      <div>
        <div style="font-weight:700;">${escapeHtml(patientName(visit.id))}</div>
        <div class="meta" style="margin-top:3px;">${escapeHtml(visit.service)} · ${escapeHtml(visitTime(visit.id, visit.time))} · ${escapeHtml(phoneFor(visit.id))}</div>
      </div>
      <span class="badge ${escapeHtml(visit.tier)}">${visit.tier === 'High' ? 'Likely to go wrong' : 'Worth a check'}</span>
    </div>
    <div class="meta" style="margin-top:9px;"><b>Reported:</b> the assigned nurse can't make it.</div>`;
}
function addDays(iso, n){ const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }

function showResult(visit, date, candidates){
  const el = document.getElementById('live-result');
  const ctx = visitCtx(visit);
  const sameDay = date === DATA.today;
  if(!candidates.length){
    const draft = draftFor('move', {...ctx, date: fmtDate(addDays(DATA.today, 1))});
    el.innerHTML = `
      <div class="card result warn">
        <div style="font-weight:700; margin-bottom:5px;">No nurse is free ${sameDay ? 'today' : 'on ' + escapeHtml(fmtDate(date))} for this visit</div>
        <div class="meta">The visit is still unassigned and stays on your list. Next best options:</div>
        <div class="btns" style="margin-top:10px; justify-content:flex-start;">
          <button class="approve" onclick="findNextFreeDay('${escapeHtml(visit.id)}')">Find the next day with a free nurse</button>
        </div>
        ${renderDraft('move-' + visit.id, draft, {open: true})}
        <div class="meta" style="margin-top:8px;">If the family can't move it, escalate to the operations head or a partner agency.</div>
      </div>`;
    return;
  }
  const c = candidates[0];
  const nurse = provName(c.provider_id);
  const reasons = Array.isArray(c.reasons) ? c.reasons : [];
  const draft = sameDay ? draftFor('replacement', {...ctx, nurse})
    : draftFor('reschedule', {...ctx, date: fmtDate(date), nurse});
  el.innerHTML = `
    <div class="card result ok">
      <div class="card-top">
        <div>
          <div style="font-weight:700;">Best option: ${escapeHtml(nurse)}</div>
          <div class="meta" style="margin-top:3px;">${sameDay ? 'Today' : escapeHtml(fmtDate(date))}, ${escapeHtml(ctx.time)} · ${escapeHtml(c.area || '')}</div>
        </div>
        <span class="badge Medium">For your approval</span>
      </div>
      ${reasons.length ? `<div class="reasons">${reasons.map(r => `<span>${escapeHtml(plainWhy(r, sameDay))}</span>`).join('')}</div>` : ''}
      ${candidates.length > 1 ? `<details class="trace"><summary>${candidates.length - 1} other option(s)</summary>${candidates.slice(1).map(alt => `<div class="alt"><b>${escapeHtml(provName(alt.provider_id))}</b> <span class="meta">${escapeHtml(alt.provider_id || '')}</span><div class="meta">${(Array.isArray(alt.reasons) ? alt.reasons : []).map(r => escapeHtml(plainWhy(r, sameDay))).join(' · ')}</div></div>`).join('')}</details>` : ''}
      ${renderDraft('fix-' + visit.id + date, draft, {open: true})}
      <div class="meta" style="margin-top:8px;">Next: confirm with ${escapeHtml(nurse)} first, then send the family message. Nothing has been booked.</div>
    </div>`;
}
async function askCareOps(){
  const id = document.getElementById('live-appt').value;
  const el = document.getElementById('live-result');
  const button = document.getElementById('find-recovery-button');
  if(!id){ el.innerHTML = '<div class="empty">Choose a visit first.</div>'; return; }
  const visit = DATA.flagged.find(v => v.id === id);
  const mode = document.getElementById('recovery-mode').value;
  const selectedDate = mode === 'today' ? DATA.today : document.getElementById('recovery-date').value;
  if(mode === 'future' && (!selectedDate || selectedDate <= DATA.today || selectedDate > LAST_DEMO_DATE)){
    el.innerHTML = '<div class="empty">Choose a date within the 60 days after the simulated day.</div>';
    return;
  }
  button.disabled = true; button.textContent = 'Checking who is free…';
  const data = await liveCallApi('/api/recover', {appointment_id: id, target_date: selectedDate});
  button.disabled = false; button.textContent = 'Find a replacement';
  if(!data) return;
  showResult(visit, selectedDate, Array.isArray(data.candidates) ? data.candidates : []);
}
async function findNextFreeDay(id){
  const visit = DATA.flagged.find(v => v.id === id);
  const el = document.getElementById('live-result');
  el.innerHTML = '<div class="empty">Checking the next 7 days…</div>';
  for(let i = 1; i <= 7; i++){
    const date = addDays(DATA.today, i);
    const data = await liveCallApi('/api/recover', {appointment_id: id, target_date: date}, true);
    if(!data) return;
    if((data.candidates || []).length){
      document.getElementById('recovery-mode').value = 'future';
      document.getElementById('recovery-date-wrap').style.display = 'block';
      document.getElementById('recovery-date').value = date;
      showResult(visit, date, data.candidates);
      return;
    }
  }
  el.innerHTML = `<div class="card result warn"><div style="font-weight:700;">No nurse is free in the next 7 days</div><div class="meta">Escalate to the operations head or a partner agency. The visit stays on your list.</div></div>`;
}
// After a "no": look for the next free day after the one the family declined, and start a fresh proposal.
const nextAfterNo = {};
const declinedDays = {};   // visit id -> dates the family has turned down
async function findNextAfterNo(id){
  const v = DATA.flagged.find(f => f.id === id);
  if(!v || !v.rescheduleProposal || (nextAfterNo[id] && nextAfterNo[id].checking)) return;
  const from = v.rescheduleProposal.new_date;
  nextAfterNo[id] = {checking: true};
  rerenderAll();
  let result = {none: true};
  for(let i = 1; i <= 7; i++){
    const date = addDays(from, i);
    let data = null;
    try {
      const res = await fetch('/api/recover', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({appointment_id: id, target_date: date})});
      data = res.ok ? await res.json() : null;
    } catch(e) { data = null; }
    if(!data){ result = {error: true}; break; }
    const top = (data.candidates || [])[0];
    if(top){ result = {date, pid: top.provider_id, reasons: top.reasons || []}; break; }
  }
  if(result.date){
    if(!v.origProposal) v.origProposal = v.rescheduleProposal;
    (declinedDays[id] = declinedDays[id] || []).push(from);
    v.rescheduleProposal = {new_date: result.date, provider_id: result.pid, reasons: result.reasons, retry: true};
    delete execState[id];
    delete nextAfterNo[id];
    if(draftState[id]) draftState[id].edits = {};
    logAction(`${patientName(id)}: next free day is ${fmtDate(result.date)} with ${provName(result.pid)}, to offer the family`);
  } else {
    nextAfterNo[id] = result;
    if(result.none) logAction(`${patientName(id)}: no nurse free in the 7 days after ${fmtDate(from)}`);
  }
  saveProgress();
  rerenderAll();
}

// One visit can show up under Needs you, Running late and A nurse is out today. Say so on the card,
// so the coordinator does not handle the same visit twice.
const coverAsked = {};   // appointment id -> nurse asked to cover (from "A nurse is out today")
function elsewhereNote(id, here){
  const notes = [];
  const late = execState['late-' + id];
  if(here !== 'late' && late && !late.running) notes.push('Already in progress under Running late');
  if(here !== 'needs' && execState[id] && !execState[id].running && DATA.flagged.some(f => f.id === id)) notes.push('Already in progress under Needs you');
  if(coverAsked[id]) notes.push(`${coverAsked[id]} was asked to cover this visit under "A nurse is out today"`);
  return notes.length ? `<div class="exec-steps elsewhere">${notes.map(n => `<div><span class="mk">i</span>${escapeHtml(n)}. Check before acting again.</div>`).join('')}</div>` : '';
}
function askCover(btn, appt, nurse){
  coverAsked[appt] = nurse;
  btn.disabled = true; btn.textContent = `Waiting for ${nurse}`;
  logAction(`${patientName(appt)}: ${nurse} asked to cover`);
  rerenderAll();
}

// "Find another day" works in place on the visit's card: the coordinator keeps her place in the
// list, and a found day turns the visit into a proposed move that follows the usual approval steps.
const foundDays = {};
function applyFoundDay(v){
  const f = foundDays[v.id];
  if(f && f.date) v.rescheduleProposal = {new_date: f.date, provider_id: f.pid, reasons: f.reasons || [], found: true};
}
async function findAnotherDay(id){
  const v = DATA.flagged.find(f => f.id === id);
  if(!v || (foundDays[id] && foundDays[id].checking)) return;
  foundDays[id] = {checking: true};
  rerenderAll();
  let result = {none: true};
  for(let i = 1; i <= 7; i++){
    const date = addDays(DATA.today, i);
    let data = null;
    try {
      const res = await fetch('/api/recover', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({appointment_id: id, target_date: date})});
      data = res.ok ? await res.json() : null;
    } catch(e) { data = null; }
    if(!data){ result = {error: true}; break; }
    const top = (data.candidates || [])[0];
    if(top){ result = {date, pid: top.provider_id, reasons: top.reasons || []}; break; }
  }
  foundDays[id] = result;
  applyFoundDay(v);
  if(result.date) logAction(`${patientName(id)}: found ${fmtDate(result.date)} with ${provName(result.pid)}, not yet agreed with the family`);
  else if(result.none) logAction(`${patientName(id)}: no nurse free in the next 7 days`);
  saveProgress();
  rerenderAll();
}

// ---- Day board ------------------------------------------------------------------
function renderSummary(){
  const s = DATA.summary || {};
  const total = Number(s.total) || 0;
  const open = DATA.flagged.filter(v => !isConfirmed(v) && !isDoneToday(v));
  const done = DATA.flagged.filter(isDoneToday).length;
  const high = open.filter(v => v.tier === 'High').length;
  const med = open.filter(v => v.tier === 'Medium').length;
  const conf = DATA.flagged.length - open.length;
  const ok = Math.max(0, total - high - med - conf - done) + done;
  const todoN = open.filter(v => !isWaiting(v)).length;
  document.getElementById('hero-title').textContent = `${todoN} of today's ${total} visits need you`;
  const board = document.getElementById('board');
  const marks = [...Array(high).fill('high'), ...Array(med).fill('med'), ...Array(conf).fill('conf'), ...Array(ok).fill('ok')];
  board.innerHTML = marks.map((c, i) => `<i class="${c}" style="animation-delay:${Math.min(i * 12, 900)}ms"></i>`).join('');
  if(!board.dataset.drawn){ board.classList.add('animate'); board.dataset.drawn = '1'; } else board.classList.remove('animate');
  board.setAttribute('aria-label', `${high} likely to go wrong, ${med} worth a check, ${conf} already confirmed, ${ok} on track, out of ${total} visits`);
  document.getElementById('legend').innerHTML = `
    <span><i style="background:var(--high)"></i><b>${high}</b> likely to go wrong</span>
    <span><i style="background:var(--med)"></i><b>${med}</b> worth a check</span>
    <span><i class="conf-key"></i><b>${conf}</b> family confirmed</span>
    <span><i style="background:color-mix(in srgb, var(--ok) 35%, var(--card))"></i><b>${ok}</b> on track</span>`;
}

initOperatorView();
loadProgress();
render();
