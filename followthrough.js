const followSessionKey = 'liver-chip-followthrough-v1';
let followPlans = [];
let activePlan = null;
let followSequence = 0;
let followStorageAvailable = true;
try {
    followPlans = JSON.parse(sessionStorage.getItem(followSessionKey))?.plans || [];
} catch (error) {
    followStorageAvailable = false;
    console.warn('Follow-through storage is unavailable.', error);
}

const outcomeOptions = {
    INSPECT: [['pending','Not performed yet'],['confirmed','Source inspected; original reading retained'],['evidence_update','Documented correction or new evidence available'],['unresolved','Concern still unresolved']],
    COMPARE: [['pending','Not performed yet'],['interpretation','Assumptions reviewed; interpretation documented'],['unresolved','Concern still unresolved']],
    RECOVER: [['pending','Search pending'],['evidence_update','Missing original retrieved; ready to import'],['not_found','Original not found']],
    REPEAT: [['pending','Experiment pending'],['evidence_update','New documented measurement obtained'],['unavailable','Repeat unavailable']],
    EXTEND: [['pending','Laboratory discussion pending'],['discussion','Laboratory discussion recorded'],['evidence_update','New documented dose measurement obtained'],['unavailable','Additional experiment unavailable']],
    REPORT: [['pending','Report pending'],['reported','Bounded reporting decision documented']],
    FIX: [['pending','Correction pending'],['evidence_update','Corrected compatible input available'],['unresolved','Input concern unresolved']],
    ABSTAIN: [['pending','Not reviewed yet'],['acknowledged','Unsupported request acknowledged'],['unresolved','Request still unresolved']]
};

function evidenceSignature(records) {
    const rows = [];
    for (const record of records) {
        const fields = [];
        for (const key of Object.keys(record).sort()) {
            let value = record[key] ?? '';
            if (['day','dose_cmax_multiple','value'].includes(key) && value !== '') value = Number(value);
            else if (key === 'missing') value = value === true || ['true','1'].includes(String(value).toLowerCase());
            else value = String(value);
            fields.push([key,value]);
        }
        rows.push(fields);
    }
    rows.sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
    return JSON.stringify(rows);
}

function persistFollowPlans() {
    try {
        sessionStorage.setItem(followSessionKey, JSON.stringify({version:1,plans:followPlans}));
        followStorageAvailable = true;
        el('plan-storage-warning').hidden = true;
        return true;
    } catch (error) {
        followStorageAvailable = false;
        el('plan-storage-warning').textContent = 'Browser storage is unavailable or full. Export the complete record before leaving this page.';
        el('plan-storage-warning').hidden = false;
        return false;
    }
}

function hideFollowthrough() {
    followSequence += 1;
    activePlan = null;
    el('followthrough').hidden = true;
    el('plan-context-note').hidden = true;
}

function rememberNewPlan(result) {
    activePlan = {
        id:crypto.randomUUID(), compound:result.compound, created_at:new Date().toISOString(),
        baseline_signature:evidenceSignature(result.audit.records),
        goal:el('goal').value, plan:JSON.parse(JSON.stringify(result)), outcomes:[], reassessment:null,
        draft:{outcome:'pending',notes:'',reference:'',compatibility:''}, follow_open:false
    };
    followPlans.push(activePlan);
    el('plan-history-export').hidden = false;
    const url = new URL(location.href);
    url.searchParams.delete('newplan');
    history.replaceState(null,'',url);
    persistFollowPlans();
    prepareFollowForm();
}

function restorePlanForCase() {
    const entries = followPlans.filter(entry => entry.compound === current.compound);
    el('plan-history-export').hidden = entries.length === 0;
    if (new URL(location.href).searchParams.get('newplan') === '1') return;
    const signature = evidenceSignature(current.records);
    activePlan = [...entries].reverse().find(entry => entry.baseline_signature === signature || (entry.reassessment && evidenceSignature(entry.reassessment.updated.records) === signature)) || null;
    if (!activePlan) {
        if (entries.length) {
            el('plan-context-note').textContent = 'An earlier action uses different source records for this compound. Run the planner for the current evidence. Earlier case records remain available in the export.';
            el('plan-context-note').hidden = false;
        }
        return;
    }
    lastResult = activePlan.plan;
    el('goal').value = activePlan.goal;
    el('request').value = lastResult.request;
    el('request-preview').textContent = lastResult.request;
    el('engine').value = lastResult.engine;
    el('record-review').checked = lastResult.resources.record_review;
    el('repeat-available').checked = lastResult.resources.repeat_budget > 0;
    el('missing-access').checked = lastResult.resources.missing_record_access;
    el('new-dose').checked = lastResult.resources.new_dose_allowed;
    updateMethod();
    showResult(lastResult,false);
    prepareFollowForm();
    if (activePlan.follow_open) el('followthrough').hidden = false;
    el('plan-context-note').textContent = 'Saved action restored for this evidence version. Its original audit and any follow-up outcomes are retained.';
    el('plan-context-note').hidden = false;
}

function followButtonLabel(action) {
    return {INSPECT:'Record review outcome',COMPARE:'Record review outcome',RECOVER:'Add updated evidence',REPEAT:'Add updated evidence',EXTEND:'Add updated evidence',FIX:'Add updated evidence',REPORT:'Record reporting decision',ABSTAIN:'Record unresolved limitation'}[action];
}

function prepareFollowForm() {
    if (!activePlan) return;
    const options = outcomeOptions[activePlan.plan.delivered_action];
    el('follow-outcome').innerHTML = options.map(([value,label])=>`<option value="${value}">${escapeHtml(label)}</option>`).join('');
    el('follow-outcome').value = activePlan.draft.outcome;
    el('follow-notes').value = activePlan.draft.notes;
    el('follow-reference').value = activePlan.draft.reference;
    el('follow-compatibility').value = activePlan.draft.compatibility;
    el('follow-csv').value = '';
    el('follow-selected').textContent = activePlan.compound + ' · ' + activePlan.plan.action.title;
    el('follow-error').hidden = true;
    el('follow-draft-status').textContent = '';
    for (const element of el('follow-form').elements) element.disabled = Boolean(activePlan.reassessment);
    updateOutcomeFields();
    renderFollowResult();
}

function openFollowthrough() {
    if (!activePlan) return;
    activePlan.follow_open = true;
    persistFollowPlans();
    el('followthrough').hidden = false;
    el('follow-heading').scrollIntoView({block:'start'});
    el('follow-heading').focus({preventScroll:true});
}

function updateOutcomeFields() {
    const updating = el('follow-outcome').value === 'evidence_update';
    el('follow-update-fields').hidden = !updating || Boolean(activePlan?.reassessment);
    el('follow-save').textContent = activePlan?.reassessment?'Reassessment recorded':updating?'Analyse updated CSV and record outcome':'Record outcome';
    if (updating && location.protocol === 'file:') {
        el('follow-error').textContent = 'Updated CSV analysis requires the local server. See Guide for setup. Your original record is retained.';
        el('follow-error').hidden = false;
    }
}

function saveFollowDraft() {
    if (!activePlan || activePlan.reassessment) return;
    followSequence += 1;
    activePlan.draft = {outcome:el('follow-outcome').value,notes:el('follow-notes').value,reference:el('follow-reference').value,compatibility:el('follow-compatibility').value};
    el('follow-error').hidden = true;
    updateOutcomeFields();
    const retained = persistFollowPlans();
    el('follow-draft-status').textContent = retained?'Draft retained in this browser tab. Use Record outcome to document the result.':'Draft is available on this page only. Export before leaving.';
}

function auditSummary(analysis) {
    const primary = analysis.primary || {state:'fit_failed',crossing:null};
    let conclusion = 'No usable fit.';
    if (primary.state === 'within_range') conclusion = `50% crossing: ${Number(primary.crossing).toFixed(2)}× unbound Cmax.`;
    if (primary.state === 'right_censored') conclusion = 'Fitted response stays above 50%; no crossing within the measured range.';
    if (primary.state === 'left_censored') conclusion = 'Fitted response is already at or below 50% at the lowest measured dose.';
    const doses = analysis.doses || [];
    const range = doses.length?`${Number(doses[0]).toPrecision(4)}–${Number(doses.at(-1)).toPrecision(4)}× unbound Cmax`:'Unavailable';
    const observed = analysis.records.filter(row=>!row.missing).length;
    return `<p>${escapeHtml(conclusion)}</p><p class="small">Measured range: ${escapeHtml(range)}<br>${observed} observed · ${analysis.records.length-observed} missing</p>`;
}

function openChecksHtml(analysis) {
    const triggered = analysis.checklist.filter(item=>item.status==='Fail');
    const unassessed = analysis.checklist.filter(item=>item.status==='Not assessed');
    let html = '<h3>What remains open?</h3>';
    html += triggered.length?'<ul>'+triggered.map(item=>`<li><strong>${escapeHtml(item.label)}</strong><br><span class="small">${escapeHtml(item.evidence)}</span></li>`).join('')+'</ul>':'<p class="small">No named computational check triggers in this version. Experimental validity remains unassessed.</p>';
    html += '<h3>Still unassessed</h3><p class="small">'+unassessed.map(item=>escapeHtml(item.label)).join(' · ')+'</p>';
    return html;
}

function comparisonHtml(result) {
    let html = '<p class="notice">Updated evidence analysed. This documents a reassessment, not confirmation of experimental validity.</p>';
    html += '<div class="comparison-summary"><article><h3>Original evidence</h3>'+auditSummary(result.baseline)+'</article><article><h3>Updated evidence</h3>'+auditSummary(result.updated)+'</article></div>';
    html += '<p class="small">'+(result.material_conclusion_change?'The crossing/censoring state changed, or the crossing shifted by more than a factor of two.':'The frozen material-change criterion does not trigger. Exact estimates and individual checks may still differ.')+'</p>';
    html += '<h3>Source records that changed</h3><div class="table-wrap"><table><thead><tr><th>Record</th><th>Change</th><th>Before / after</th></tr></thead><tbody>';
    for (const change of result.record_changes) {
        const fields = change.fields.map(field=>`<p><strong>${escapeHtml(field.field)}</strong>: ${escapeHtml(field.before===null?'Absent':String(field.before))} → ${escapeHtml(String(field.after))}</p>`).join('');
        html += `<tr><td>${escapeHtml(change.source_location)}<br><code>${escapeHtml(change.source_record_id)}</code></td><td>${escapeHtml(change.kind)}</td><td><details><summary>${change.fields.length} changed field${change.fields.length===1?'':'s'}</summary>${fields}</details></td></tr>`;
    }
    html += '</tbody></table></div><details><summary>Compare individual computed checks</summary><div class="table-wrap"><table><thead><tr><th>Check</th><th>Original</th><th>Updated</th></tr></thead><tbody>';
    html += result.check_changes.map(item=>`<tr><td>${escapeHtml(item.label)}</td><td>${escapeHtml(item.before)}<br>${escapeHtml(item.before_evidence)}</td><td>${escapeHtml(item.after)}<br>${escapeHtml(item.after_evidence)}</td></tr>`).join('') || '<tr><td colspan="3">No computed check status or evidence changed.</td></tr>';
    html += '</tbody></table></div></details>'+openChecksHtml(result.updated);
    html += '<p class="small">Compatibility is researcher-reported: '+escapeHtml(result.compatibility_note)+'</p><p class="small">'+escapeHtml(result.interpretation)+'</p><p class="small">This action now has one preserved reassessment. Start a new plan from the updated evidence for later changes.</p><button id="follow-new-plan" type="button">Plan another action</button>';
    return html;
}

function renderFollowResult() {
    const record = activePlan.outcomes.at(-1);
    el('follow-review').href = 'auditor_demo.html?compound=' + encodeURIComponent(activePlan.compound);
    el('follow-review').textContent = activePlan.reassessment?'View updated results':'View results';
    el('follow-review').onclick = event => {
        try { if (activePlan.reassessment) publishUpdatedEvidence(); }
        catch (error) {
            event.preventDefault();
            el('follow-error').textContent = error.message;
            el('follow-error').hidden = false;
        }
    };
    if (activePlan.reassessment) {
        el('follow-result').innerHTML = comparisonHtml(activePlan.reassessment);
        el('follow-new-plan').onclick = startPlanFromUpdatedEvidence;
    } else if (record) {
        const message = {
            confirmed:'Source inspection recorded. The original reading is retained; any computed influence warning remains.',
            interpretation:'Assumption review recorded. The primary fitting method remains unchanged.',
            discussion:'Laboratory discussion recorded. No new exposure or measurement is inferred.',
            reported:'Reporting decision recorded. Keep the measured-range qualification and evidence limitations with the report.',
            acknowledged:'Unsupported request acknowledged. No unsupported scientific conclusion is produced.',
            unresolved:'The concern remains open.',not_found:'The missing original was not found; missingness is retained.',
            unavailable:'The experiment is unavailable; the evidence concern remains open.',pending:'The action remains pending.'
        }[record.outcome];
        el('follow-result').innerHTML = `<p class="notice">Analysis unchanged · outcome recorded</p><p>${escapeHtml(message)}</p><p class="small">Measurements, the numerical conclusion and its limitations remain unchanged.</p><p><strong>Your note</strong><br>${escapeHtml(record.notes||'No additional note.')}</p>${record.reference?'<p class="small">Reported reference: '+escapeHtml(record.reference)+'</p>':''}${auditSummary(activePlan.plan.audit)}${openChecksHtml(activePlan.plan.audit)}`;
    } else {
        el('follow-result').innerHTML = '<p>Document the outcome after performing the action. If you have changed measurements, supply the complete compatible CSV to compare it with the preserved baseline.</p><p class="small">No follow-up outcome has been recorded. The current numerical conclusion and limitations remain.</p>';
    }
}

async function recordFollowOutcome(event) {
    event.preventDefault();
    if (!activePlan || activePlan.reassessment) return;
    const entry = activePlan;
    const outcome = el('follow-outcome').value;
    const notes = el('follow-notes').value.trim();
    const reference = el('follow-reference').value.trim();
    const compatibility = el('follow-compatibility').value.trim();
    const runSequence = ++followSequence;
    el('follow-error').hidden = true;
    el('follow-save').disabled = true;
    try {
        if (outcome !== 'pending' && !notes) throw Error('Document what you found, or why the action remains unresolved.');
        if (['confirmed','interpretation','discussion','reported','acknowledged','evidence_update'].includes(outcome) && !reference) throw Error('Add the source or laboratory-record reference for this outcome.');
        let result = null;
        if (outcome === 'evidence_update') {
            const file = el('follow-csv').files[0];
            if (!file) throw Error('Select the complete updated CSV. The original evidence is retained until analysis succeeds.');
            if (!compatibility) throw Error('Document how sampling and normalisation are compatible, including any differences.');
            if (location.protocol==='file:') throw Error('Updated CSV analysis requires the local server; see Guide.');
            el('follow-save').textContent = 'Analysing updated evidence…';
            const response = await fetch('/reassess',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({baseline_records:entry.plan.audit.records,updated_csv:await file.text(),evidence_reference:reference,compatibility_note:compatibility,delivered_action:entry.plan.delivered_action,action_doses:entry.plan.action.dose_cmax_multiples})});
            result = await response.json();
            if (!response.ok) throw Error(result.error || 'The updated evidence could not be analysed.');
        }
        if (activePlan !== entry || runSequence !== followSequence) return;
        entry.draft = {outcome,notes,reference,compatibility};
        entry.outcomes.push({recorded_at:new Date().toISOString(),outcome,label:el('follow-outcome').selectedOptions[0].textContent,notes,reference,evidence_version_changed:Boolean(result),measurements_changed:result?.measurements_changed || false});
        entry.reassessment = result;
        const retained = persistFollowPlans();
        showResult(entry.plan,false);
        prepareFollowForm();
        el('follow-draft-status').textContent = retained?'Outcome retained in this browser tab. Export the complete record to keep a copy.':'Outcome recorded on this page only. Export now before leaving.';
        el('follow-result-heading').scrollIntoView({block:'start'});
        el('follow-result-heading').focus({preventScroll:true});
    } catch (error) {
        if (activePlan !== entry || runSequence !== followSequence) return;
        el('follow-error').textContent = error.message;
        el('follow-error').hidden = false;
    } finally {
        el('follow-save').disabled = Boolean(activePlan?.reassessment);
        updateOutcomeFields();
    }
}

function publishUpdatedEvidence() {
    const updated = JSON.parse(JSON.stringify(activePlan.reassessment.updated));
    updated.followthrough_revision = {plan_id:activePlan.id,evidence_reference:activePlan.reassessment.evidence_reference,compatibility_note:activePlan.reassessment.compatibility_note};
    let state;
    try { state = JSON.parse(sessionStorage.getItem('liver-chip-review-v1')) || {}; }
    catch (error) { state = {}; }
    const imports = state.importedCases || [];
    const index = imports.findIndex(item=>item.compound===updated.compound);
    if (index >= 0) imports[index] = updated;
    else imports.push(updated);
    try {
        sessionStorage.setItem('liver-chip-review-v1',JSON.stringify({compound:updated.compound,importedCases:imports}));
        saved = {compound:updated.compound,importedCases:imports};
    } catch (error) {
        throw Error('The updated Review cannot be retained in browser storage. Export the complete record before leaving.');
    }
    return updated;
}

function startPlanFromUpdatedEvidence() {
    try {
        const updated = publishUpdatedEvidence();
        const index = drugs.findIndex(drug=>drug.compound===updated.compound);
        drugs[index] = updated;
        current = updated;
        el('goal').value = 'review';
        setGoal();
        const url = new URL(location.href);
        url.searchParams.set('newplan','1');
        history.replaceState(null,'',url);
        el('plan-context-note').textContent = 'Updated evidence is selected. Set your next goal and confirm the available resources; the previous action record is preserved.';
        el('plan-context-note').hidden = false;
        el('goal').scrollIntoView({block:'center'});
        el('goal').focus({preventScroll:true});
    } catch (error) {
        el('follow-error').textContent = error.message;
        el('follow-error').hidden = false;
    }
}

function downloadFollowRecord(value, filename) {
    const blob = new Blob([JSON.stringify(value,null,2)],{type:'application/json'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
}

function exportActivePlan() {
    if (!activePlan) return;
    downloadFollowRecord({...activePlan.plan,followthrough:activePlan},activePlan.compound+'_action_and_outcome.json');
}

function initFollowthrough() {
    el('follow-form').onsubmit = recordFollowOutcome;
    for (const id of ['follow-outcome','follow-notes','follow-reference','follow-compatibility']) el(id).addEventListener('input',saveFollowDraft);
    el('follow-csv').addEventListener('change',()=>{followSequence+=1;el('follow-error').hidden=true;});
    el('follow-export').onclick = exportActivePlan;
    el('plan-history-export').onclick = () => downloadFollowRecord({compound:current.compound,plans:followPlans.filter(entry=>entry.compound===current.compound)},current.compound+'_case_records.json');
    if (!followStorageAvailable) {
        el('plan-storage-warning').textContent = 'Browser storage is unavailable. Export the complete record before leaving this page.';
        el('plan-storage-warning').hidden = false;
    }
}
