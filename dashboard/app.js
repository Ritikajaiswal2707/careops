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
  'Rafiq Ahmed','Sudha Murthy','Hemant Desai','Nirmala Rao'];
function patientName(id){
  if(id in patientIndex) return PATIENT_NAMES[patientIndex[id] % PATIENT_NAMES.length];
  return OTHER_PATIENT_NAMES[hashId(id) % OTHER_PATIENT_NAMES.length];
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
const noBackup = v => (v.action || '').startsWith('Reassign needed');

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
function plainReason(r){
  let m;
  if((m = /^(\d+) prior no-shows? before this visit/.exec(r))) return `Missed ${m[1]} visits before`;
  if((m = /^([\d.]+)km from clinician/.exec(r))) return `${m[1]} km between nurse and patient`;
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
  if(a.startsWith('Send confirmation')) return 'Send a reminder and ask for a backup contact';
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
    <summary>${escapeHtml(opts.title || 'Message to family')} <span class="meta">ready to send</span> <span class="tag rules">Template</span></summary>
    <div class="draft-body">
      <div class="seg" role="group" aria-label="Language">
        <button type="button" class="${st.lang === 'hi' ? 'on' : ''}" onclick="setDraftLang('${escapeHtml(id)}','hi')">Hinglish</button>
        <button type="button" class="${st.lang === 'en' ? 'on' : ''}" onclick="setDraftLang('${escapeHtml(id)}','en')">English</button>
      </div>
      <textarea id="draft-${escapeHtml(id)}" aria-label="${escapeHtml(opts.title || 'Message to family')}" rows="4" oninput="draftState['${escapeHtml(id)}'].edits[draftState['${escapeHtml(id)}'].lang]=this.value">${escapeHtml(text)}</textarea>
      <div class="draft-actions"><button type="button" class="ghost" onclick="copyDraft('${escapeHtml(id)}', this)">Copy</button><span class="meta">Not sent. Edit it, then paste into WhatsApp.</span></div>
    </div>
  </details>`;
}
function setDraftLang(id, lang){
  const st = draftState[id]; st.lang = lang;
  const ta = document.getElementById('draft-' + id);
  if(!ta) return;
  ta.value = st.edits[lang] ?? st.draft[lang];
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
  if(v.rescheduleProposal){
    const p = v.rescheduleProposal;
    return draftFor('reschedule', {...ctx, date: fmtDate(p.new_date), nurse: provName(p.provider_id)});
  }
  const a = v.action || '';
  if(a.startsWith('Call to confirm') || a.startsWith('Send confirmation')) return draftFor('reminder', ctx);
  if(noBackup(v)) return draftFor('nobackup', ctx);
  return null;
}

// ---- Action history (this browser session only) ----------------------------------
const actionLog = [];
function logAction(text){
  const t = new Date();
  actionLog.unshift({time: t.toLocaleTimeString('en-IN', {hour: 'numeric', minute: '2-digit'}), text});
  renderHistory();
}
function renderHistory(){
  const el = document.getElementById('history');
  if(!el) return;
  el.innerHTML = actionLog.length ? `<div class="panel"><div class="panel-title">Your actions this session</div>
    ${actionLog.map(a => `<div class="hist-row"><span class="meta">${escapeHtml(a.time)}</span> ${escapeHtml(a.text)}</div>`).join('')}
    <div class="meta" style="margin-top:6px;">Kept in this browser tab only. A real deployment stores an audit trail of who approved what, and when.</div></div>` : '';
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
      ${startHere ? '<div class="start-here">Start here: a family\'s Hinglish message, turned into a fix and a reply ready to send</div>' : ''}
      <div class="card-top">
        <div>
          <div class="visit-title">${escapeHtml(patientName(v.id))}</div>
          <div class="meta">${escapeHtml(v.service)} · <b>${escapeHtml(time)}</b> · <span class="nowrap">${escapeHtml(phoneFor(v.id))}</span></div>
        </div>
        <span class="badge ${escapeHtml(v.tier)}" title="Model score ${pct}%">${label}</span>
      </div>
      <div class="reasons">${v.reasons.map(r => `<span>${escapeHtml(plainReason(r))}</span>`).join('')}</div>
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
  let items = DATA.flagged.filter(v => !isConfirmed(v) && (currentFilter === 'all' || v.tier === currentFilter));
  if(currentSort === 'time') items = [...items].sort((a, b) => timeMinutes(visitTime(a.id, a.time)) - timeMinutes(visitTime(b.id, b.time)));
  // Pin the clearest example first so a new visitor sees the core loop straight away.
  const pinned = currentFilter === 'all' && currentSort === 'risk' ? items.find(v => v.rescheduleProposal) : null;
  if(pinned) items = [pinned, ...items.filter(v => v !== pinned)];
  list.innerHTML = items.length ? items.map(v => visitCard(v, v === pinned)).join('') : '<div class="empty">Nothing in this view.</div>';
  const conf = DATA.flagged.filter(isConfirmed);
  document.getElementById('confirmed').innerHTML = conf.length ? `
    <details class="confirmed-group">
      <summary>Already confirmed by the family (${conf.length})</summary>
      ${conf.map(v => `<div class="conf-row"><div><b>${escapeHtml(patientName(v.id))}</b> · ${escapeHtml(v.service)} · ${escapeHtml(visitTime(v.id, v.time))}<div class="meta">${escapeHtml(v.patientSignal.channel)}: "${escapeHtml(v.patientSignal.message)}"</div></div><span class="badge Low">Confirmed</span></div>`).join('')}
    </details>` : '';
  renderOwner();
  renderHistory();
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
  const label = v.recovery ? (v.recovery.startsWith('Backup available') ? `Send ${provName(v.recovery)} instead` : 'No backup nurse free. Agree a later time with the family') : plainAction(v);
  const flow = flowFor(v);
  const st = execState[v.id];
  let stepsHtml = '';
  if(st){
    stepsHtml = `<div class="exec-steps">` + flow.steps.map((s, i) => {
      const done = i < st.stepIndex || (i === st.stepIndex && !st.running);
      const active = i === st.stepIndex && st.running;
      const mark = done ? '✓' : (active ? '…' : '·');
      return `<div class="${done ? 'ok' : ''}" style="opacity:${i <= st.stepIndex ? 1 : 0.4}"><span class="mk">${mark}</span>${escapeHtml(s)}</div>`;
    }).join('') + `</div>`;
  }
  const isDone = st && st.stepIndex >= flow.steps.length - 1 && !st.running;
  let replyHtml = '';
  if(isDone && v.rescheduleProposal){
    const p = v.rescheduleProposal, nurse = provName(p.provider_id);
    if(!st.reply){
      replyHtml = `<div class="reply-row"><span class="meta">When the family replies:</span>
        <button class="ghost" onclick="familyReplied('${escapeHtml(v.id)}','yes')">Family said yes</button>
        <button class="ghost" onclick="familyReplied('${escapeHtml(v.id)}','no')">Family said no</button></div>`;
    } else if(st.reply === 'yes'){
      replyHtml = `<div class="exec-steps"><div class="ok"><span class="mk">✓</span>${escapeHtml(nurse)} told about the new visit</div><div class="ok"><span class="mk">✓</span>Visit moved to ${escapeHtml(fmtDate(p.new_date))}, ${escapeHtml(visitTime(v.id, v.time))}. Done</div></div>`;
    } else {
      replyHtml = `<div class="exec-steps"><div><span class="mk">!</span>Family said no. The slot is released and ${escapeHtml(nurse)} was never told. Ask for a day that suits them:</div></div>
        ${renderDraft('ask-' + v.id, draftFor('move', {...visitCtx(v), date: fmtDate(addDays(p.new_date, 1))}), {open: true, title: 'Ask the family for another day'})}`;
    }
  }
  const replyDone = st && st.reply;
  const flowDone = replyDone ? (st.reply === 'yes' ? 'Rescheduled' : 'Asking for another day') : flow.done;
  const flowDoneClass = replyDone ? (st.reply === 'yes' ? 'done' : 'warn') : flow.doneClass;
  const btnLabel = !st ? flow.button : (st.running ? 'Working…' : (isDone ? flowDone : flow.button));
  const disabled = st && (st.running || isDone);
  const canAct = !v.recovery || v.recovery.startsWith('Backup available');
  const secondary = noBackup(v) ? `<button class="ghost" onclick="findAnotherDay('${escapeHtml(v.id)}')">Find another day</button>` : '';
  return `
    <div class="action-row">
      <div class="action-main">
        <div class="action">Suggested: <b>${escapeHtml(label)}</b></div>
        <div class="btns">${secondary}${canAct ? `<button class="approve ${isDone ? flowDoneClass : ''}" ${disabled ? 'disabled' : ''} onclick="approveItem('${escapeHtml(v.id)}')">${escapeHtml(btnLabel)}</button>` : ''}</div>
      </div>
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
  const v = DATA.flagged.find(f => f.id === id);
  logAction(`${patientName(id)}: family said ${answer}${answer === 'yes' ? `, visit moved to ${fmtDate(v.rescheduleProposal.new_date)}` : ', asking for another day'}`);
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
    else { st.running = false; rerenderAll(); }
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
          <div class="step problem"><div class="dot"></div><div>Only <b>${slack} min</b> of spare time left before ${escapeHtml(firstName(c.id))}'s visit starts late.${c.locGap ? ' The previous address was hard to find, which added to the delay.' : ''}</div></div>
          <div class="step ${hasBackup ? 'fix' : 'problem'}"><div class="dot"></div><div>${hasBackup ? `Backup: <b>${escapeHtml(backup)}</b> · ${escapeHtml(why)}` : 'No backup nurse is free. Tell the family now and agree a later start.'}</div></div>
        </div>
        ${renderDraft('late-' + c.id, draft, {open: true})}
        ${hasBackup ? renderActionRow({...c, id: 'late-' + c.id}) : ''}
        <div class="id-line">Visit ${escapeHtml(c.id)} · ${escapeHtml(c.provider)}</div>
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
    const vitals = [...new Set(unver.split(':')[1].split(',').map(s => (VITAL_LABEL[s.trim()] || s.trim()).toLowerCase()))].join(' and ');
    return {hi: `Shukriya! Kripya ${vitals} ki reading number mein boliye, jaise "oxygen 97", aur note dobara bhej dijiye.`,
            en: `Thank you! Please say the ${vitals} reading as a number, like "oxygen 97", and send the note again.`};
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
    ${r.model_vitals && Object.keys(r.model_vitals).length ? `<div class="meta">AI reported <span class="tag ai">AI</span></div><div class="vr-vitals">${vrChips(r.model_vitals, '')}</div>` : ''}
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
    `Recorded examples from a real ${VR_EXAMPLES.model} run on ${VR_EXAMPLES.recorded_at.slice(0, 10)}, with safety checks v${VR_EXAMPLES.safety_version} re-applied offline.`;
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
        ${rows.map(({v, pick}) => {
          const name = patientName(v.appointment_id), time = visitTime(v.appointment_id, v.time_slot);
          const msg = pick ? draftFor('replacement', {name, service: v.service_type, time, slot: v.time_slot, nurse: provName(pick.provider_id)}) : null;
          return `<div class="cover-row">
            <div><b>${escapeHtml(name)}</b> · ${escapeHtml(v.service_type)} · ${escapeHtml(time)}
              <div class="meta">${pick ? `Cover: <b>${escapeHtml(provName(pick.provider_id))}</b> · ${(pick.reasons || []).slice(0, 2).map(x => escapeHtml(plainWhy(x))).join(' · ')}` : 'No nurse with room today'}</div></div>
            ${pick ? `<button class="ghost" onclick="copyText(this, ${escapeHtml(JSON.stringify(msg.hi))})">Copy message</button>`
                   : `<button class="ghost" onclick="coverLater(this, '${escapeHtml(v.appointment_id)}')">Find another day</button>`}
          </div>`;
        }).join('')}
        <div class="meta" style="margin-top:8px;">Recommendation only. Nothing is booked and no one is contacted from this demo.</div>
      </div>`;
    logAction(`${nurseOut} out: cover found for ${covered} of ${rows.length} visits`);
  } catch(e){
    el.innerHTML = `<div class="empty">Could not check cover (${escapeHtml(e.message)}). It may still be starting up.</div>`;
  }
  btn.disabled = false; btn.textContent = 'Find cover for all her visits';
}
async function coverLater(btn, apptId){
  btn.disabled = true; btn.textContent = 'Checking…';
  for(let i = 1; i <= 7; i++){
    const date = addDays(DATA.today, i);
    const r = await fetch('/api/recover', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({appointment_id: apptId, target_date: date})}).catch(() => null);
    const data = r && r.ok ? await r.json() : null;
    const c = data && (data.candidates || [])[0];
    if(c){
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
      <div class="meta" style="margin-top:8px;">Next: confirm with ${escapeHtml(nurse)} first, then send the family message. Nothing has been booked. <span class="id-line">${escapeHtml(c.provider_id || '')}</span></div>
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
function findAnotherDay(id){
  showView('live');
  document.getElementById('live-appt').value = id;
  renderIncidentSummary();
  window.scrollTo({top: document.getElementById('live-view').offsetTop - 20, behavior: 'smooth'});
  findNextFreeDay(id);
}

// ---- Day board ------------------------------------------------------------------
function renderSummary(){
  const s = DATA.summary || {};
  const total = Number(s.total) || 0;
  const open = DATA.flagged.filter(v => !isConfirmed(v));
  const high = open.filter(v => v.tier === 'High').length;
  const med = open.filter(v => v.tier === 'Medium').length;
  const conf = DATA.flagged.length - open.length;
  const ok = Math.max(0, total - high - med - conf);
  document.getElementById('hero-title').textContent = `${high + med} of today's ${total} visits need you`;
  const board = document.getElementById('board');
  const marks = [...Array(high).fill('high'), ...Array(med).fill('med'), ...Array(conf).fill('conf'), ...Array(ok).fill('ok')];
  board.innerHTML = marks.map((c, i) => `<i class="${c}" style="animation-delay:${Math.min(i * 12, 900)}ms"></i>`).join('');
  board.classList.add('animate');
  board.setAttribute('aria-label', `${high} likely to go wrong, ${med} worth a check, ${conf} already confirmed, ${ok} on track, out of ${total} visits`);
  document.getElementById('legend').innerHTML = `
    <span><i style="background:var(--high)"></i><b>${high}</b> likely to go wrong</span>
    <span><i style="background:var(--med)"></i><b>${med}</b> worth a check</span>
    <span><i class="conf-key"></i><b>${conf}</b> family confirmed</span>
    <span><i style="background:color-mix(in srgb, var(--ok) 35%, var(--card))"></i><b>${ok}</b> on track</span>`;
}

renderSummary();
render();
