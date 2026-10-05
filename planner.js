const el = id => document.getElementById(id);
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let saved = null;
try { saved = JSON.parse(sessionStorage.getItem('liver-chip-review-v1')); } catch (error) { console.warn(error); }
const drugs = [...output.drug_results];
for (const drug of saved?.importedCases || []) {
    const previous = drugs.findIndex(item => item.compound === drug.compound);
    if (previous >= 0) drugs[previous] = drug;
    else drugs.push(drug);
}
const query = new URLSearchParams(location.search);
let current = drugs.find(drug => drug.compound === (query.get('compound') || saved?.compound)) || drugs[0];
let lastResult = null;
let requestSequence = 0;
const goals = {
    review: {request:'Only source-record review is possible today. What should I inspect first?', repeat:false, missing:false, dose:false},
    repeat: {request:'One independent repeat at an existing dose is possible. Which condition should I prioritise?', repeat:true, missing:false, dose:false},
    recover: {request:'I can search the archive for missing original readings. What should I retrieve?', repeat:false, missing:true, dose:false},
    finite: {request:'A finite 50% albumin crossing is required. What is the next feasible action?', repeat:true, missing:true, dose:true},
    report: {request:'No finite crossing is needed. Report the current conclusion and its evidence limitations.', repeat:false, missing:false, dose:false},
    models: {request:'Review disagreement between the curve models and their assumptions.', repeat:false, missing:false, dose:false}
};

function clearResult() {
    requestSequence += 1;
    lastResult = null;
    el('plan-result').hidden = true;
    el('plan-empty').hidden = false;
    el('plan-export').disabled = true;
    el('plan-error').hidden = true;
    hideFollowthrough();
}

function updateCompound() {
    clearResult();
    const url = new URL(location.href);
    url.searchParams.set('compound', current.compound);
    history.replaceState(null, '', url);
    el('back-review').href = 'auditor_demo.html?compound=' + encodeURIComponent(current.compound);
    el('back-review').setAttribute('aria-label', 'Back to results for ' + current.compound);
    el('back-review-context').textContent = 'View the measurements and findings for ' + current.compound + '.';
    document.querySelector('nav a[href^="auditor_demo.html"]').setAttribute('href', el('back-review').getAttribute('href'));
    try {
        sessionStorage.setItem('liver-chip-review-v1', JSON.stringify({compound:current.compound, importedCases:saved?.importedCases || []}));
    } catch (error) { console.warn(error); }
    restorePlanForCase();
}

function setGoal() {
    const goal = goals[el('goal').value];
    el('request').value = goal.request;
    el('request-preview').textContent = goal.request;
    el('record-review').checked = true;
    el('repeat-available').checked = goal.repeat;
    el('missing-access').checked = goal.missing;
    el('new-dose').checked = goal.dose;
    clearResult();
}

function showResult(result, focus=true) {
    const action = result.action;
    const baseline = result.audit || current;
    const records = baseline.records.filter(record => action.source_record_ids.includes(record.source_record_id));
    const scenarios = baseline.scenarios.filter(scenario => action.scenario_ids.includes(scenario.scenario_id));
    const sameEvidenceVersion = evidenceSignature(baseline.records) === evidenceSignature(current.records);
    let sourceHtml = '';
    if (records.length) {
        sourceHtml = '<details open><summary>Supporting readings when this action was selected</summary>';
        if (!sameEvidenceVersion) sourceHtml += '<p class="small">These values belong to the original action snapshot. Review opens the current evidence version, which may have different values. The original records remain in the complete export.</p>';
        sourceHtml += '<div class="table-wrap"><table><thead><tr><th>Source record</th><th>Dose / unbound Cmax</th><th>Albumin %</th></tr></thead><tbody>';
        for (const record of records) {
            const reviewUrl = 'auditor_demo.html?compound=' + encodeURIComponent(current.compound) + '&source=' + encodeURIComponent(record.source_record_id) + '#measurements-details';
            sourceHtml += `<tr><td>${escapeHtml(record.source_sheet + '!' + record.source_cell)}<br><a class="source-return" href="${escapeHtml(reviewUrl)}" aria-label="Inspect ${escapeHtml(record.source_sheet + '!' + record.source_cell)} in ${sameEvidenceVersion?'Review':'the current Review version'}">${sameEvidenceVersion?'Inspect in Review':'Inspect current version'} →</a></td><td>${Number(record.dose_cmax_multiple).toPrecision(5)}</td><td>${record.missing?'Missing':Number(record.value).toFixed(2)}</td></tr>`;
        }
        sourceHtml += '</tbody></table></div></details>';
    }
    let scenarioHtml = '';
    if (scenarios.length) {
        scenarioHtml = '<details><summary>Supporting sensitivity calculations</summary><div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Result</th><th>Changed</th></tr></thead><tbody>';
        for (const scenario of scenarios) {
            const state = {within_range:'Crossing within measured range',right_censored:'Crossing not observed in measured range',left_censored:'Already below 50% at lowest dose',fit_failed:'Fit failed'}[scenario.state] || scenario.state;
            scenarioHtml += `<tr><td>${escapeHtml(scenario.label)}</td><td>${escapeHtml(state)}${scenario.crossing===null?'':' · '+Number(scenario.crossing).toFixed(2)+'× unbound Cmax'}</td><td>${scenario.changed?'Yes':'No'}</td></tr>`;
        }
        scenarioHtml += '</tbody></table></div></details>';
    }
    const method = result.engine==='model'?'Local small language model · Experimental':'Request-aware rules · Default';
    const fallback = result.fallback?'<p class="notice">The model choice failed an eligibility or scope check. Rules supplied the delivered action. Both choices are preserved in the export.</p>':'';
    const resources = result.resources;
    const constraints = [resources.record_review?'Record review available':'Record review unavailable',resources.repeat_budget?'One repeat available':'No repeat available',resources.missing_record_access?'Archive access available':'Archive access unavailable',resources.new_dose_allowed?'Dose coverage discussion allowed':'Additional dose coverage unavailable'];
    const evidence = action.evidence_summary?.length?'<div class="report-evidence"><h3>Evidence to include in the report</h3>'+action.evidence_summary.map(text=>'<p>'+escapeHtml(text)+'</p>').join('')+'</div>':'';
    const limitations = action.limitations || [];
    const limitsHtml = limitations.length?'<div class="result-limitations"><h3>Experimental evidence still unassessed</h3><p class="small">'+limitations.map(item=>escapeHtml(item.label)).join(' · ')+'</p><details><summary>Why these checks remain unassessed</summary>'+limitations.map(item=>'<div class="detail-row"><h3>'+escapeHtml(item.label)+'</h3><p class="small">'+escapeHtml(item.evidence)+'</p></div>').join('')+'</details></div>':'';
    const future = action.future_action?'<details class="future-action"><summary>If resources change · repeat unavailable today</summary><p>'+escapeHtml(action.future_action)+'</p></details>':'';
    const outcomeRecorded = Boolean(activePlan?.outcomes.length);
    const continuation = `<div class="follow-entry"><p class="small">${outcomeRecorded?'The recorded outcome and remaining concerns are available below.':'After this action, record the outcome and check what remains open.'}</p><button class="primary" id="continue-action" type="button">${outcomeRecorded?'View recorded outcome':escapeHtml(followButtonLabel(result.delivered_action))} →</button></div>`;
    el('plan-result').innerHTML = `<span class="badge">${method}</span><p class="small result-case">${escapeHtml(result.compound)} · ${escapeHtml(el('goal').selectedOptions[0].textContent)}</p><div class="current-result"><strong>Response conclusion when this action was selected</strong><p>${escapeHtml(action.conclusion)}</p></div>${fallback}<article class="action-card"><h3>${escapeHtml(action.title)}</h3>${action.reason!==action.conclusion?'<p>'+escapeHtml(action.reason)+'</p>':''}<p class="action-step"><strong>${outcomeRecorded?'Selected action':'Do this now'}</strong>${escapeHtml(action.action)}</p><p class="action-step"><strong>Fits your resources</strong>${escapeHtml(action.feasibility)}</p><p class="small resource-summary">${constraints.map(escapeHtml).join(' · ')}</p>${action.interpretation?'<p class="small">'+escapeHtml(action.interpretation)+'</p>':''}${future}${continuation}</article>${evidence}${sourceHtml}${scenarioHtml}${limitsHtml}`;
    el('plan-result').hidden = false;
    el('plan-empty').hidden = true;
    el('plan-export').disabled = false;
    el('continue-action').onclick = openFollowthrough;
    if (focus) {
        if (window.innerWidth <= 780) el('result-heading').scrollIntoView({block:'start'});
        el('result-heading').focus({preventScroll:true});
    }
}

function updateMethod() {
    el('engine-help').textContent = el('engine').value==='model'
        ? 'Local SmolLM2-135M chooses an action class. Eligibility checks and the auditor supply the evidence and action text.'
        : 'Rules choose an action from your request, resource limits and calculated evidence.';
}

el('plan-compound').innerHTML = drugs.map(drug => '<option>'+escapeHtml(drug.compound)+'</option>').join('');
el('plan-compound').value = current.compound;
el('plan-compound').onchange = () => {
    current = drugs.find(drug => drug.compound===el('plan-compound').value);
    const url = new URL(location.href);
    url.searchParams.delete('newplan');
    history.replaceState(null,'',url);
    updateCompound();
};
el('goal').onchange = setGoal;
for (const id of ['request','record-review','repeat-available','missing-access','new-dose','engine']) el(id).addEventListener('input', clearResult);
el('request').addEventListener('input', () => { el('request-preview').textContent = el('request').value; });
el('request').addEventListener('invalid', () => { el('custom-request').open = true; });
el('engine').addEventListener('change', updateMethod);
el('planner-form').onsubmit = async event => {
    event.preventDefault();
    clearResult();
    const runSequence = requestSequence;
    const runCompound = current.compound;
    el('plan-run').disabled = true;
    el('plan-run').textContent = 'Reviewing evidence…';
    const payload = {records:current.records, request:el('request').value, engine:el('engine').value, resources:{record_review:el('record-review').checked, repeat_budget:el('repeat-available').checked?1:0, missing_record_access:el('missing-access').checked, new_dose_allowed:el('new-dose').checked}};
    try {
        const response = await fetch('/plan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
        const result = await response.json();
        if (runSequence !== requestSequence || runCompound !== current.compound) return;
        if (!response.ok) throw new Error(result.error || 'The planner could not complete this request.');
        lastResult = {...result, compound:current.compound, request:payload.request, resources:payload.resources};
        rememberNewPlan(lastResult);
        showResult(lastResult);
    } catch (error) {
        if (runSequence !== requestSequence || runCompound !== current.compound) return;
        el('plan-error').textContent = error.message;
        el('plan-error').hidden = false;
    } finally {
        el('plan-run').disabled = false;
        el('plan-run').textContent = 'Find a next action';
    }
};
el('plan-export').onclick = exportActivePlan;
async function checkStatus() {
    if (location.protocol==='file:') {
        el('planner-status').textContent = 'Run the local server to use the action planner. See Guide for setup.';
        el('plan-run').disabled = true;
        return;
    }
    try {
        const response = await fetch('/planner-status');
        if (!response.ok) throw new Error('Start the updated demo.py server to enable the planner.');
        const status = await response.json();
        el('engine').querySelector('[value="model"]').disabled = !status.model_loaded;
        el('planner-status').textContent = status.model_loaded?'Local model available on this server. Rules are also available.':'Rules available. To enable the local model, follow the setup in Guide.';
    } catch (error) {
        el('planner-status').textContent = error.message;
        el('plan-run').disabled = true;
    }
}
initFollowthrough();
setGoal();
updateCompound();
if (location.hash === '#followthrough') openFollowthrough();
checkStatus();
