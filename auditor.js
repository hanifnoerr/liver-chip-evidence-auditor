const sessionKey = 'liver-chip-review-v1';
let savedCase = null;
try {
    savedCase = JSON.parse(sessionStorage.getItem(sessionKey));
} catch (error) {
    console.warn('Browser session storage is unavailable.', error);
}
let importedCases = savedCase?.importedCases || [];
let drugs = [...output.drug_results];
for (const drug of importedCases) {
    const previous = drugs.findIndex(item => item.compound === drug.compound);
    if (previous >= 0) drugs[previous] = drug;
    else drugs.push(drug);
}
const query = new URLSearchParams(location.search);
let current = drugs.find(drug => drug.compound === (query.get('compound') || savedCase?.compound)) || drugs[0];
const guarded = query.get('view') !== 'curve';
const el = id => document.getElementById(id);
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number = value => value === null || value === undefined ? '—' : Number(value).toFixed(2);
const stateLabel = value => ({within_range:'Crossing within measured range',left_censored:'Already below 50% at the lowest dose',right_censored:'Crossing not observed',fit_failed:'Fit failed'}[value] || value);
const modelNames = {isotonic:'Primary fit',raw_interpolation:'Raw interpolation',logistic:'Logistic'};
const reasonLabels = {model:'Alternative curve assumptions change the conclusion.',reading_deletion:'A single reading changes the conclusion.',dose_deletion:'The conclusion depends on specific dose coverage.',missing_probe:'Hypothetical missing-value scenarios change the conclusion.'};

function rememberCase() {
    const url = new URL(location.href);
    url.searchParams.set('compound', current.compound);
    if (url.searchParams.has('source') && !current.records.some(record => record.source_record_id === url.searchParams.get('source'))) {
        url.searchParams.delete('source');
        url.hash = '';
    }
    history.replaceState(null, '', url);
    el('reset-examples').hidden = importedCases.length === 0;
    try {
        sessionStorage.setItem(sessionKey, JSON.stringify({compound:current.compound, importedCases}));
        el('session-warning').hidden = true;
    } catch (error) {
        el('session-warning').hidden = false;
        el('session-warning').textContent = 'Browser storage is unavailable. Export this case before leaving the page.';
    }
}

function conclusionText(result) {
    if (result.state === 'within_range') return `Estimated crossing: ${number(result.crossing)} × unbound Cmax.`;
    if (result.state === 'right_censored') return 'The fitted response stays above 50% across the measured doses.';
    if (result.state === 'left_censored') return 'The fitted response is already at or below 50% at the lowest measured dose.';
    return 'This model did not produce a usable fit.';
}

function populate() {
    el('compound').innerHTML = drugs.map(drug => `<option>${escapeHtml(drug.compound)}</option>`).join('');
    el('compound').value = current.compound;
}

function locateMeasurements(sourceIds) {
    el('measurements-details').open=true;
    document.querySelectorAll('#records .source-focus').forEach(row=>row.classList.remove('source-focus'));
    let firstRow=null;
    current.records.forEach((record,index)=>{
        if(sourceIds.includes(record.source_record_id)) {
            const row=el(`record-${index}`);
            row.classList.add('source-focus');
            if(!firstRow) firstRow=row;
        }
    });
    if(firstRow) {
        firstRow.tabIndex=-1;
        firstRow.focus({preventScroll:true});
        firstRow.scrollIntoView({behavior:'auto',block:'center'});
    }
}

function locateScenarios(scenarioIds) {
    const selected=current.scenarios.filter(scenario=>scenarioIds.includes(scenario.scenario_id));
    if(selected.some(scenario=>!scenario.changed)) {
        el('changes-only').checked=false;
        render();
    }
    el('technical-details').open=true;
    let firstRow=null;
    el('scenarios').querySelectorAll('tr').forEach(row=>{
        row.classList.remove('source-focus');
        if(scenarioIds.includes(row.dataset.scenarioId)) {
            row.classList.add('source-focus');
            if(!firstRow) firstRow=row;
        }
    });
    if(firstRow) firstRow.scrollIntoView({behavior:'smooth',block:'center'});
}

function renderRecommendations(drug) {
    document.querySelectorAll('a[href^="planner.html"]').forEach(link => { link.href = 'planner.html?compound=' + encodeURIComponent(drug.compound) + (link.id==='return-to-action'?'#followthrough':''); });
    el('planner-link').setAttribute('aria-label', 'Choose what to do next for ' + drug.compound);
    el('next-step-case').textContent = 'Step 2 uses the results for ' + drug.compound + '.';
    const actions=drug.recommendations;
    el('legacy-actions').hidden=Boolean(actions);
    el('more-actions').hidden=!actions || actions.length<=3;
    el('additional-actions').innerHTML='';
    if(!actions) {
        el('recommendations').innerHTML='<ul>'+drug.next_steps.map(text=>`<li>${escapeHtml(text)}</li>`).join('')+'</ul>';
        return;
    }
    const cards=[];
    for(let index=0;index<actions.length;index++) {
        const action=actions[index];
        let links='';
        if(action.source_record_ids.length) links+=`<a href="#measurements-details" data-action-index="${index}" data-action-target="records">Locate measurements</a>`;
        if(action.scenario_ids.length) links+=`<a href="#technical-details" data-action-index="${index}" data-action-target="scenarios">View calculations</a>`;
        else if(action.check_codes.length) links+=`<a href="#checklist-details" data-action-index="${index}" data-action-target="checks">View related checks</a>`;
        cards.push(`<article class="action-card" data-action-rule="${escapeHtml(action.rule)}"><h3>${escapeHtml(action.title)}</h3><p>${escapeHtml(action.reason)}</p><p class="action-step"><strong>Next step</strong>${escapeHtml(action.action)}</p>${action.interpretation?`<p class="small">${escapeHtml(action.interpretation)}</p>`:''}<div class="action-links">${links}</div></article>`);
    }
    el('recommendations').innerHTML=cards.slice(0,3).join('');
    el('additional-actions').innerHTML=cards.slice(3).join('');
    el('more-actions-summary').textContent=`${Math.max(0,actions.length-3)} more finding${actions.length-3===1?'':'s'}`;
    document.querySelectorAll('[data-action-index]').forEach(link=>link.onclick=event=>{
        event.preventDefault();
        const action=drug.recommendations[Number(link.dataset.actionIndex)];
        if(link.dataset.actionTarget==='records') locateMeasurements(action.source_record_ids);
        else if(link.dataset.actionTarget==='scenarios') locateScenarios(action.scenario_ids);
        else {
            el('checklist-details').open=true;
            let firstRow=null;
            el('checklist').querySelectorAll('tr').forEach(row=>{
                row.classList.remove('source-focus');
                if(action.check_codes.includes(row.dataset.checkCode)) {
                    row.classList.add('source-focus');
                    if(!firstRow) firstRow=row;
                }
            });
            if(firstRow) firstRow.scrollIntoView({behavior:'smooth',block:'center'});
        }
    });
}

function drawChart(drug) {
    const mobile=window.innerWidth<=780;
    const width=mobile?360:640, height=mobile?320:360, left=mobile?50:60, right=18, top=20, bottom=55;
    const logs=drug.doses.map(Math.log10), xmin=Math.min(...logs), xmax=Math.max(...logs);
    const values=drug.records.filter(row=>!row.missing).map(row=>row.value);
    const compare=el('compare-models').checked;
    const visibleModels=drug.models.filter(model=>model.success && model.model!=='constant' && (model.model==='isotonic' || compare));
    visibleModels.forEach(model=>values.push(...model.fitted));
    const ymin=Math.min(0,...values), ymax=Math.max(110,...values)*1.08;
    const x=dose=>left+(Math.log10(dose)-xmin)/(xmax-xmin)*(width-left-right);
    const y=value=>height-bottom-(value-ymin)/(ymax-ymin)*(height-top-bottom);
    let shapes=`<rect x="${left}" y="${top}" width="${width-left-right}" height="${height-top-bottom}" fill="var(--surface)"/>`;
    for(let tick=0;tick<=4;tick++) {
        const value=ymin+(ymax-ymin)*tick/4;
        shapes+=`<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--line)"/><text x="${left-8}" y="${y(value)+4}" text-anchor="end" font-size="12" fill="var(--muted)">${Math.round(value)}</text>`;
    }
    drug.doses.forEach(dose=>shapes+=`<text x="${x(dose)}" y="${height-bottom+20}" text-anchor="middle" font-size="11" fill="var(--muted)">${Number(dose.toPrecision(3))}</text>`);
    shapes+=`<line x1="${left}" x2="${width-right}" y1="${y(50)}" y2="${y(50)}" stroke="var(--muted)" stroke-dasharray="4 4"/><text x="${width-right}" y="${y(50)-8}" text-anchor="end" font-size="11" fill="var(--ink)">50% reference</text>`;
    const colours={isotonic:'var(--primary)',raw_interpolation:'var(--plot-raw)',logistic:'var(--plot-logistic)'};
    const linePatterns={isotonic:'none',raw_interpolation:'8 5',logistic:'2 5'};
    visibleModels.forEach(model=>{
        if(!colours[model.model]) return;
        const points=[];
        for(let i=0;i<=150;i++) {
            const logdose=xmin+(xmax-xmin)*i/150, dose=10**logdose;
            let value;
            if(model.model==='logistic') {
                const [low,amp,mid,slope]=model.parameters;
                value=low+amp/(1+Math.exp(slope*(logdose-mid)));
            } else {
                let j=0;
                while(j<model.doses.length-2 && dose>model.doses[j+1]) j++;
                const fraction=(logdose-Math.log10(model.doses[j]))/(Math.log10(model.doses[j+1])-Math.log10(model.doses[j]));
                value=model.fitted[j]+fraction*(model.fitted[j+1]-model.fitted[j]);
            }
            points.push(`${x(dose)},${y(value)}`);
        }
        shapes+=`<polyline points="${points.join(' ')}" fill="none" stroke="${colours[model.model]}" stroke-width="2.6" stroke-dasharray="${linePatterns[model.model]}"><title>${escapeHtml(modelNames[model.model]||model.model)}</title></polyline>`;
    });
    drug.records.forEach(row=>{
        if(!row.missing) {
            const influential=guarded && drug.influential_observations.some(item=>item.source_record_ids.includes(row.source_record_id));
            shapes+=`<circle cx="${x(row.dose_cmax_multiple)}" cy="${y(row.value)}" r="${influential?5:4}" fill="var(--muted)" stroke="${influential?'var(--warning-line)':'none'}" stroke-width="3"><title>${escapeHtml(row.source_sheet+'!'+row.source_cell)}: ${number(row.value)}%</title></circle>`;
        } else shapes+=`<text x="${x(row.dose_cmax_multiple)}" y="${height-bottom-5}" text-anchor="middle" font-size="11" fill="var(--amber)">missing</text>`;
    });
    shapes+=`<text x="${width/2}" y="${height-6}" text-anchor="middle" font-size="12">Dose / unbound Cmax (log scale)</text><text transform="translate(15,${height/2}) rotate(-90)" text-anchor="middle" font-size="12">Normalised albumin (%)</text>`;
    el('chart').innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Measured albumin and fitted dose-response curves">${shapes}</svg>`;
    document.querySelectorAll('[data-comparison]').forEach(item=>item.hidden=!compare);
}

function render() {
    const drug=current;
    document.querySelectorAll('[data-guarded]').forEach(panel=>panel.hidden=!guarded);
    document.querySelector('.grid').style.gridTemplateColumns=guarded?'':'1fr';
    el('comparison-note').hidden=guarded;
    el('comparison-note').querySelector('a').href=`auditor_demo.html?view=guarded&compound=${encodeURIComponent(drug.compound)}`;
    el('state').textContent=stateLabel(drug.primary.state);
    const range=drug.doses.length?` Measured range: ${number(drug.doses[0])}–${number(drug.doses.at(-1))}× unbound Cmax.`:'';
    el('crossing').textContent=conclusionText(drug.primary)+range;
    const needsReview=drug.review || drug.source_warning;
    el('review').innerHTML=`<span class="badge ${guarded&&needsReview?'review':''}">${!guarded?'Curve-only view':needsReview?'Evidence needs review':'No tested sensitivity detected'}</span>`;
    const changedCount=drug.scenarios.filter(row=>row.changed).length;
    el('reasons').textContent=!guarded?'Open evidence review to inspect the supporting checks.':drug.review?`${changedCount} tested scenario${changedCount===1?'':'s'} change the conclusion.`:drug.source_warning?'Missing readings limit the available evidence.':'Limited to the scenarios tested; experimental validity remains unassessed.';
    const observed=drug.records.filter(row=>!row.missing).length;
    const missing=drug.records.length-observed;
    el('counts').textContent=`${observed} readings`;
    el('missing-count').textContent=`${drug.doses.length} measured doses · ${missing} missing reading${missing===1?'':'s'}`;
    el('issues').innerHTML=drug.issues.map(issue=>`<div class="detail-row"><h3>${escapeHtml(issue.code.replaceAll('_',' '))}</h3><p class="small">${escapeHtml(issue.message)}</p></div>`).join('')||'<p class="small">No source fault detected in the supplied input. This does not establish experimental independence.</p>';
    el('diagnostics').innerHTML=drug.diagnostics.map(item=>`<p class="small">${escapeHtml(modelNames[item.model]||item.model)}: ${escapeHtml(item.code.replaceAll('_',' '))}</p>`).join('')||'<p class="small">No specified numerical diagnostic triggered.</p>';
    const assessed=drug.checklist.filter(item=>item.layer!=='diagnostic');
    const failedChecks=assessed.filter(item=>item.status==='Fail');
    const fails=failedChecks.length;
    const unknown=assessed.filter(item=>item.status==='Not assessed').length;
    const passed=assessed.filter(item=>item.status==='Pass').length;
    const checkNotes=failedChecks.map(item=>item.code==='threshold_bracket'?'50% crossing is not bracketed.':item.code==='complete_readings'?'Some source readings are missing.':reasonLabels[item.code]||item.label);
    el('check-summary').innerHTML=`<div class="check-group ${fails?'attention':''}"><strong>${fails} check${fails===1?'':'s'} to inspect</strong>${checkNotes.length?checkNotes.map(note=>`<p>${escapeHtml(note)}</p>`).join(''):'<p>No named computational check needs attention.</p>'}</div><div class="check-group"><strong>${unknown} not assessed</strong><p>Includes unavailable laboratory controls and experimental independence.</p></div><div class="check-group"><strong>${passed} checks passed</strong><p>Individual computational checks only. Fit diagnostics are listed separately.</p></div>`;
    el('checklist-summary').textContent=`View all ${drug.checklist.length} checks and supporting evidence`;
    el('checklist').innerHTML=drug.checklist.map(item=>`<tr data-check-code="${escapeHtml(item.code)}"><td>${escapeHtml(item.label)}<br><span class="small">${escapeHtml(item.layer)}</span></td><td><span class="status ${item.status==='Pass'?'pass':item.status==='Fail'?'fail':''}">${escapeHtml(item.status)}</span></td><td>${escapeHtml(item.evidence)}</td><td>${escapeHtml(item.action)}</td></tr>`).join('');
    const unassessed=drug.checklist.filter(item=>item.status==='Not assessed' && item.layer==='evidence');
    el('unassessed-summary').textContent=`Unassessed experimental evidence (${unassessed.length})`;
    el('unassessed-evidence').innerHTML=unassessed.map(item=>`<div class="detail-row"><h3>${escapeHtml(item.label)}</h3><p class="small">${escapeHtml(item.evidence)}</p><p class="small">${escapeHtml(item.action)}</p></div>`).join('');
    el('influence-summary').textContent=`Inspect single-reading sensitivity · ${drug.influential_observations.length} influential reading${drug.influential_observations.length===1?'':'s'}`;
    el('influential').innerHTML=drug.influential_observations.map((item,index)=>`<div class="influence"><strong>${escapeHtml(item.source_cells.join(', '))} · ${item.affected_values.map(number).join(', ')}% albumin</strong><p><span class="small">With all readings</span><br>${escapeHtml(conclusionText({state:item.original_state,crossing:item.original_crossing}))}</p><p><span class="small">Without this reading</span><br>${escapeHtml(conclusionText(item))}</p><a href="#measurements-details" data-source-index="${index}">Locate this measurement</a></div>`).join('')||'<p class="small">No tested single-reading deletion changes this conclusion. Technical measurement errors have not been ruled out.</p>';
    const scenarios=drug.scenarios.filter(row=>!el('changes-only').checked||row.changed);
    el('scenarios').innerHTML=scenarios.map(row=>`<tr data-scenario-id="${escapeHtml(row.scenario_id||'')}"><td>${escapeHtml(row.kind.replaceAll('_',' '))}</td><td>${escapeHtml(row.label)}<br><code>${escapeHtml(row.source_cells.join(', '))}</code></td><td>${stateLabel(row.state)}</td><td>${number(row.crossing)}</td><td>${row.changed?'Yes':'No'}</td></tr>`).join('')||'<tr><td colspan="5">No material change among the displayed scenarios.</td></tr>';
    el('records').innerHTML=drug.records.map((row,index)=>`<tr id="record-${index}"><td><strong>${escapeHtml(row.source_sheet+'!'+row.source_cell)}</strong><br><code>${escapeHtml(row.source_record_id)}</code></td><td>${number(row.dose_cmax_multiple)}</td><td>${row.missing?'Missing':number(row.value)}</td><td>${escapeHtml(row.data_origin.replaceAll('_',' '))}</td><td>${escapeHtml(row.chip_id||'Unknown')} / ${escapeHtml(row.run_id||'Unknown')}</td></tr>`).join('');
    document.querySelectorAll('[data-source-index]').forEach(link=>link.onclick=event=>{
        event.preventDefault();
        const item=drug.influential_observations[Number(link.dataset.sourceIndex)];
        locateMeasurements(item.source_record_ids);
    });
    const pair=output.pairs.find(pair=>pair.includes(drug.compound));
    const other=pair && pair.find(name=>name!==drug.compound);
    el('comparator').disabled=!other || !drugs.some(item=>item.compound===other);
    el('comparator').textContent=other?`Published comparator: ${other}`:'No published comparator';
    el('comparator').title='Open the paired compound from the source paper. This is a separate case, not a matched-chip comparison.';
    const isExample=drug.records.every(row=>row.data_origin==='published_real' && row.source_doi==='10.1038/s43856-022-00209-1');
    el('data-origin').textContent=isExample?'Example dataset':'Imported measurements';
    el('data-origin').href=isExample?'data_sources.html':'guide.html#csv';
    if (drug.followthrough_revision) {
        el('data-origin').textContent='Reassessed evidence version';
        el('data-origin').href='guide.html#followthrough';
    }
    el('return-to-action').href='planner.html?compound='+encodeURIComponent(drug.compound)+'#followthrough';
    el('return-to-action').hidden=true;
    try {
        const plans=JSON.parse(sessionStorage.getItem('liver-chip-followthrough-v1'))?.plans || [];
        for (const entry of plans.filter(item=>item.compound===drug.compound)) {
            const versions=[entry.plan.audit.records,entry.reassessment?.updated.records].filter(Boolean);
            for (const records of versions) {
                const sameVersion=records.length===drug.records.length && drug.records.every(row=>{
                    const original=records.find(item=>item.source_record_id===row.source_record_id);
                    if(!original) return false;
                    const keys=new Set([...Object.keys(row),...Object.keys(original)]);
                    for(const key of keys) {
                        if(['day','dose_cmax_multiple','value'].includes(key) && row[key]!=='' && original[key]!=='') {
                            if(Number(row[key])!==Number(original[key])) return false;
                        } else if(String(row[key]??'')!==String(original[key]??'')) return false;
                    }
                    return true;
                });
                if(sameVersion) el('return-to-action').hidden=false;
            }
        }
    } catch(error) { console.warn('Saved action could not be read.',error); }
    renderRecommendations(drug);
    drawChart(drug);
    rememberCase();
}

populate();
render();
if (query.get('source')) locateMeasurements([query.get('source')]);
el('compound').onchange=()=>{current=drugs.find(drug=>drug.compound===el('compound').value);const url=new URL(location.href);url.searchParams.delete('source');url.hash='';history.replaceState(null,'',url);render();};
el('changes-only').onchange=render;
el('compare-models').onchange=()=>drawChart(current);
window.addEventListener('resize',()=>drawChart(current));
el('comparator').onclick=()=>{
    const pair=output.pairs.find(pair=>pair.includes(current.compound));
    const other=pair.find(name=>name!==current.compound);
    current=drugs.find(drug=>drug.compound===other);
    el('compound').value=other;
    render();
};
el('download').onclick=()=>{
    const blob=new Blob([JSON.stringify(current,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob), link=document.createElement('a');
    link.href=url;
    link.download=current.compound.toLowerCase()+'_evidence.json';
    link.click();
    URL.revokeObjectURL(url);
};
el('import-button').disabled=location.protocol==='file:';
el('import-button').title=location.protocol==='file:'?'See Guide to enable local CSV import.':'Import a compatible albumin CSV.';
el('import-button').onclick=()=>el('upload').click();
el('reset-examples').onclick=()=>{
    importedCases=[];
    drugs=[...output.drug_results];
    current=drugs.find(drug=>drug.compound===current.compound)||drugs[0];
    el('upload-status').textContent='Example cases restored.';
    el('upload-status').className='';
    populate();
    render();
};
el('upload').onchange=async event=>{
    const file=event.target.files[0];
    if(!file) return;
    el('upload-status').className='';
    el('upload-status').textContent='Analysing measurements…';
    try {
        const response=await fetch('/audit',{method:'POST',headers:{'Content-Type':'text/csv'},body:await file.text()});
        const result=await response.json();
        if(!response.ok) throw Error(result.error);
        result.forEach(drug=>{
            const importedIndex=importedCases.findIndex(item=>item.compound===drug.compound);
            if(importedIndex>=0) importedCases[importedIndex]=drug;
            else importedCases.push(drug);
            const previous=drugs.findIndex(item=>item.compound===drug.compound);
            if(previous>=0) drugs[previous]=drug;
            else drugs.push(drug);
        });
        current=result[0];
        populate();
        render();
        el('upload-status').textContent=`Analysed ${result.length} compound(s) locally.`;
    } catch(error) {
        el('upload-status').textContent=error.message;
        el('upload-status').className='error';
    }
    event.target.value='';
};
