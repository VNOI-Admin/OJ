// Minimal editable grid for bulk user creation. Vanilla JS.
// Supports typing, Ctrl+V paste, .xlsx upload/drop, per-column field mapping, and column-level formulas.
// Formula syntax: ={A}.slice(0,3) + "_" + {B}  - {A}/{B}/... by column letter, or {fieldname} by key.
(function () {
    'use strict';

    var DRAFT_KEY = 'bulk_user_draft';

    function init() {
    var FIELDS = window.BULK_FIELDS || [];
    var I18N = window.BULK_I18N || {};
    var table = document.getElementById('bulk-grid');
    if (!table) return;

    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    var tbody = document.createElement('tbody');
    thead.appendChild(headRow);
    table.appendChild(thead);
    table.appendChild(tbody);

    var ALIASES = {name: 'fullname', 'full name': 'fullname', org: 'organization',
                   'display name': 'username_display', display: 'username_display',
                   'internal id': 'internal_id', internalid: 'internal_id', id: 'internal_id'};

    function matchField(header) {
        var h = (header || '').toString().trim().toLowerCase();
        if (!h) return '';
        for (var i = 0; i < FIELDS.length; i++) {
            if (h === FIELDS[i].key || h === FIELDS[i].label.toLowerCase()) return FIELDS[i].key;
        }
        return ALIASES[h] || '';
    }

    function buildSelect(selectedKey) {
        var sel = document.createElement('select');
        var opt = document.createElement('option');
        opt.value = '';
        opt.textContent = I18N.ignore || '- ignore -';
        sel.appendChild(opt);
        FIELDS.forEach(function (f) {
            var o = document.createElement('option');
            o.value = f.key;
            o.textContent = f.label + (f.required ? ' *' : '');
            sel.appendChild(o);
        });
        sel.value = selectedKey || '';
        sel.className = (selectedKey && fieldRequired(selectedKey)) ? 'required' : '';
        sel.addEventListener('change', function () {
            sel.className = (sel.value && fieldRequired(sel.value)) ? 'required' : '';
        });
        return sel;
    }

    function fieldRequired(key) {
        for (var i = 0; i < FIELDS.length; i++) if (FIELDS[i].key === key) return FIELDS[i].required;
        return false;
    }

    function colCount() { return headRow.querySelectorAll('th.col-head').length; }

    function getColLetter(th) {
        var cols = headRow.querySelectorAll('th.col-head');
        for (var i = 0; i < cols.length; i++) if (cols[i] === th) return String.fromCharCode(65 + i);
        return '?';
    }

    // ---- Formula evaluation ----
    // Resolves {A}/{B}/... (column letter) or {fieldname} to a JSON-escaped cell value.
    function resolveColRef(ref, tr) {
        var cols = Array.prototype.slice.call(headRow.querySelectorAll('th.col-head'));
        var th = null;
        if (/^[A-Z]$/.test(ref)) {
            th = cols[ref.charCodeAt(0) - 65] || null;
        } else {
            cols.forEach(function (c) { if (c.querySelector('select').value === ref) th = c; });
        }
        if (!th) return '""';
        var cell = tr.cells[th.cellIndex];
        return JSON.stringify(cell ? (cell.textContent || '').trim() : '');
    }

    function evaluateFormula(formula, tr) {
        var expr = formula.substring(1); // strip leading '='
        expr = expr.replace(/\{(\w+)\}/g, function (_, ref) { return resolveColRef(ref, tr); });
        // Python-style string method aliases
        expr = expr.replace(/\.lower\(\)/g, '.toLowerCase()');
        expr = expr.replace(/\.upper\(\)/g, '.toUpperCase()');
        expr = expr.replace(/\.strip\(\)/g, '.trim()');
        expr = expr.replace(/\.lstrip\(\)/g, '.trimStart()');
        expr = expr.replace(/\.rstrip\(\)/g, '.trimEnd()');
        try { return new Function('return ' + expr)(); } // admin-only page
        catch (e) { return formula; }
    }

    // Re-evaluate all column-formula cells in a row after a cell is edited.
    function recalcRow(tr, skipCell) {
        Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th) {
            if (!th.dataset.colFormula) return;
            var cell = tr.cells[th.cellIndex];
            if (!cell || cell === skipCell) return;
            var result = evaluateFormula(th.dataset.colFormula, tr);
            cell.textContent = (result !== undefined && result !== null) ? String(result) : '';
        });
    }

    function makeCell() {
        var td = document.createElement('td');
        td.setAttribute('contenteditable', 'true');
        td.addEventListener('focus', function () {
            if (td.dataset.formula) td.textContent = td.dataset.formula;
        });
        td.addEventListener('blur', function () {
            var content = td.textContent;
            if (content.charAt(0) === '=') {
                td.dataset.formula = content;
                var result = evaluateFormula(content, td.parentNode);
                td.textContent = (result !== undefined && result !== null) ? String(result) : content;
                saveDraft();
            } else {
                delete td.dataset.formula;
            }
            recalcRow(td.parentNode, td);
        });
        return td;
    }

    // ---- Column-level formula ----
    function applyColumnFormula(th, formula) {
        if (formula) { th.dataset.colFormula = formula; }
        else { delete th.dataset.colFormula; }
        var btn = th.querySelector('.col-formula-btn');
        if (btn) btn.classList.toggle('active', !!formula);
        if (!formula) return;
        var colIdx = th.cellIndex;
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            var cell = tr.cells[colIdx];
            if (!cell || !cell.getAttribute('contenteditable')) return;
            var result = evaluateFormula(formula, tr);
            cell.textContent = (result !== undefined && result !== null) ? String(result) : '';
        });
        autoSizeColumns();
        saveDraft();
    }

    function addColumn(mappedKey) {
        var th = document.createElement('th');
        th.className = 'col-head';

        var btnRow = document.createElement('div');
        btnRow.className = 'col-head-btns';

        var del = document.createElement('span');
        del.className = 'col-del';
        del.textContent = '×';
        del.title = I18N.delete_column || 'Delete column';
        del.addEventListener('click', function () {
            if (colCount() <= 1) return;
            var idx = th.cellIndex;
            Array.prototype.forEach.call(tbody.rows, function (tr) { tr.deleteCell(idx); });
            headRow.removeChild(th);
        });

        var formulaBtn = document.createElement('span');
        formulaBtn.className = 'col-formula-btn';
        formulaBtn.textContent = 'ƒ';
        formulaBtn.title = I18N.edit_formula || 'Edit column formula';
        formulaBtn.addEventListener('click', function () { openFormulaModal(th); });

        btnRow.appendChild(del);
        btnRow.appendChild(formulaBtn);
        th.appendChild(btnRow);
        th.appendChild(buildSelect(mappedKey));
        headRow.insertBefore(th, actionsHead);
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            tr.insertBefore(makeCell(), tr.lastElementChild);
        });
    }

    function addRow(values) {
        var tr = document.createElement('tr');
        var num = document.createElement('td');
        num.className = 'row-num';
        tr.appendChild(num);
        var n = colCount();
        for (var i = 0; i < n; i++) {
            var td = makeCell();
            if (values && values[i] != null) td.textContent = values[i];
            tr.appendChild(td);
        }
        var act = document.createElement('td');
        act.className = 'row-actions';
        act.textContent = '×';
        act.title = I18N.delete_row || 'Delete row';
        act.addEventListener('click', function () {
            tr.parentNode.removeChild(tr);
            if (tbody.rows.length === 0) addRow();
            renumber();
        });
        tr.appendChild(act);
        tbody.appendChild(tr);
        renumber();
        // Auto-apply any column-level formulas to this new row.
        Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th) {
            if (!th.dataset.colFormula) return;
            var cell = tr.cells[th.cellIndex];
            if (cell) {
                var result = evaluateFormula(th.dataset.colFormula, tr);
                cell.textContent = (result !== undefined && result !== null) ? String(result) : '';
            }
        });
        return tr;
    }

    // Trailing header: + add-column button.
    var actionsHead = document.createElement('th');
    actionsHead.className = 'col-add-head';
    var addColBtn = document.createElement('span');
    addColBtn.className = 'col-add';
    addColBtn.textContent = '+';
    addColBtn.title = I18N.add_column || 'Add column';
    addColBtn.addEventListener('click', function () { addColumn(''); });
    actionsHead.appendChild(addColBtn);
    headRow.appendChild(actionsHead);

    // Leading header: click to add a row.
    var leadHead = document.createElement('th');
    leadHead.className = 'row-num-head';
    leadHead.textContent = '#';
    leadHead.title = I18N.add_row || 'Add row';
    leadHead.addEventListener('click', function () { addRow(); });
    headRow.insertBefore(leadHead, headRow.firstChild);

    function renumber() {
        Array.prototype.forEach.call(tbody.rows, function (tr, i) { tr.cells[0].textContent = i + 1; });
    }

    // ---- Auto-size columns by max content width, capped at MAX_COL_W. ----
    var _mctx = null;
    function textWidth(text) {
        if (!_mctx) {
            _mctx = document.createElement('canvas').getContext('2d');
            _mctx.font = getComputedStyle(table).font || '14px sans-serif';
        }
        return _mctx.measureText(text || '').width;
    }

    function autoSizeColumns() {
        var MIN_W = 90, MAX_W = 280, PAD = 20;
        Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th) {
            var colIdx = th.cellIndex, maxW = MIN_W;
            Array.prototype.forEach.call(tbody.rows, function (tr) {
                var cell = tr.cells[colIdx];
                if (cell) maxW = Math.max(maxW, textWidth(cell.textContent) + PAD);
            });
            th.style.width = Math.min(MAX_W, maxW) + 'px';
        });
    }

    function reset(columnKeys, rowsData, blankRows) {
        headRow.querySelectorAll('th.col-head').forEach(function (th) { headRow.removeChild(th); });
        while (tbody.rows.length) tbody.deleteRow(0);
        (columnKeys && columnKeys.length ? columnKeys : ['username', 'fullname'])
            .forEach(function (k) { addColumn(k); });
        if (rowsData) rowsData.forEach(function (r) { addRow(r); });
        for (var i = 0; i < (blankRows || 0); i++) addRow();
        if (tbody.rows.length === 0) addRow();
        autoSizeColumns();
    }

    // ---- Formula modal ----
    var fModal = document.createElement('div');
    fModal.className = 'bfm-overlay';
    fModal.innerHTML = [
        '<div class="bfm-box">',
        '<div class="bfm-header"><h3 id="bfm-title"></h3></div>',
        '<div class="bfm-section"><label class="bfm-label" id="bfm-chips-label"></label>',
        '<div id="bfm-chips" class="bfm-chips"></div>',
        '<div class="bfm-hint" id="bfm-ignored-hint"></div></div>',
        '<div class="bfm-section"><label class="bfm-label" for="bfm-input" id="bfm-input-label"></label>',
        '<textarea id="bfm-input" rows="3" spellcheck="false"></textarea></div>',
        '<div class="bfm-section bfm-preview-wrap"><table id="bfm-preview"></table></div>',
        '<div class="bfm-footer">',
        '<button type="button" class="button" id="bfm-apply"></button>',
        '<button type="button" class="button" id="bfm-clear-formula"></button>',
        '<button type="button" class="button" id="bfm-cancel"></button>',
        '</div></div>'
    ].join('');
    document.body.appendChild(fModal);

    var fInput = document.getElementById('bfm-input');
    var fPreview = document.getElementById('bfm-preview');
    var fChips = document.getElementById('bfm-chips');
    var fTitle = document.getElementById('bfm-title');
    var currentFormulaCol = null;

    // Set button labels from I18N.
    document.getElementById('bfm-apply').textContent = I18N.apply_formula || 'Apply to all rows';
    document.getElementById('bfm-clear-formula').textContent = I18N.clear_formula || 'Clear formula';
    document.getElementById('bfm-cancel').textContent = I18N.cancel || 'Cancel';
    document.getElementById('bfm-chips-label').textContent = I18N.columns_label || 'Columns (click to insert):';
    document.getElementById('bfm-input-label').textContent = I18N.formula_label || 'Formula:';

    function getColChipLabel(colTh) {
        var letter = getColLetter(colTh);
        var sel = colTh.querySelector('select');
        var label = '';
        if (sel && sel.value) {
            // Find the FIELDS label for this key
            for (var i = 0; i < FIELDS.length; i++) {
                if (FIELDS[i].key === sel.value) { label = FIELDS[i].label; break; }
            }
            if (!label) label = sel.value;
        } else {
            label = I18N.ignore || '(unmapped)';
        }
        return letter + ' - ' + label;
    }

    function buildPreview(formula) {
        fPreview.innerHTML = '';
        if (!formula || formula.charAt(0) !== '=') {
            var empty = document.createElement('tr');
            var etd = document.createElement('td');
            etd.textContent = I18N.preview_hint || 'Type a formula above starting with = to see a preview.';
            etd.style.cssText = 'color:#888;padding:8px;font-style:italic;';
            empty.appendChild(etd);
            fPreview.appendChild(empty);
            return;
        }
        // Find columns referenced in the formula.
        var cols = Array.prototype.slice.call(headRow.querySelectorAll('th.col-head'));
        var refThs = [];
        var re = /\{(\w+)\}/g, m;
        while ((m = re.exec(formula)) !== null) {
            var ref = m[1], th = null;
            if (/^[A-Z]$/.test(ref)) { th = cols[ref.charCodeAt(0) - 65] || null; }
            else { cols.forEach(function (c) { if (c.querySelector('select').value === ref) th = c; }); }
            if (th && refThs.indexOf(th) === -1) refThs.push(th);
        }
        // Header row.
        var htr = document.createElement('tr');
        var rth = document.createElement('th'); rth.textContent = '#'; htr.appendChild(rth);
        refThs.forEach(function (th) {
            var htd = document.createElement('th');
            htd.textContent = getColLetter(th);
            htr.appendChild(htd);
        });
        var resth = document.createElement('th');
        resth.textContent = I18N.preview_result || 'Result';
        resth.className = 'bfm-result-head';
        htr.appendChild(resth);
        fPreview.appendChild(htr);
        // Data rows (up to 5 non-empty rows).
        var shown = 0;
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            if (shown >= 5) return;
            var hasVal = false;
            for (var i = 1; i <= cols.length; i++) {
                if (tr.cells[i] && tr.cells[i].textContent.trim()) { hasVal = true; break; }
            }
            if (!hasVal) return;
            shown++;
            var dtr = document.createElement('tr');
            var ntd = document.createElement('td'); ntd.textContent = tr.cells[0].textContent; dtr.appendChild(ntd);
            refThs.forEach(function (th) {
                var dtd = document.createElement('td');
                dtd.textContent = tr.cells[th.cellIndex] ? tr.cells[th.cellIndex].textContent : '';
                dtr.appendChild(dtd);
            });
            var rtd = document.createElement('td');
            rtd.className = 'bfm-result';
            var result = evaluateFormula(formula, tr);
            rtd.textContent = (result !== undefined && result !== null) ? String(result) : '(error)';
            dtr.appendChild(rtd);
            fPreview.appendChild(dtr);
        });
        if (shown === 0) {
            var etr = document.createElement('tr');
            var etd2 = document.createElement('td');
            etd2.colSpan = refThs.length + 2;
            etd2.textContent = I18N.no_data_rows || '(no data rows to preview yet)';
            etd2.style.cssText = 'text-align:center;color:#888;padding:8px;font-style:italic;';
            etr.appendChild(etd2);
            fPreview.appendChild(etr);
        }
    }

    var previewTimer = null;
    fInput.addEventListener('input', function () {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(function () { buildPreview(fInput.value.trim()); }, 200);
    });

    function openFormulaModal(th) {
        currentFormulaCol = th;
        var letter = getColLetter(th);
        fTitle.textContent = (I18N.formula_for || 'Formula for column') + ' ' + letter;

        fChips.innerHTML = '';
        var hasIgnored = false;
        Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (colTh) {
            var isSelf = colTh === th;
            var isIgnored = !colTh.querySelector('select').value;
            if (isIgnored) hasIgnored = true;
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'bfm-chip'
                + (isSelf ? ' bfm-chip-self' : '')
                + (isIgnored ? ' bfm-chip-ignored' : '');
            chip.textContent = getColChipLabel(colTh);
            chip.addEventListener('click', function () {
                if (isSelf) return;
                var ins = '{' + getColLetter(colTh) + '}';
                var pos = fInput.selectionStart;
                fInput.value = fInput.value.slice(0, pos) + ins + fInput.value.slice(fInput.selectionEnd);
                fInput.selectionStart = fInput.selectionEnd = pos + ins.length;
                fInput.focus();
                buildPreview(fInput.value.trim());
            });
            fChips.appendChild(chip);
        });
        var hintEl = document.getElementById('bfm-ignored-hint');
        hintEl.textContent = hasIgnored
            ? (I18N.ignored_col_hint || 'Ignored columns (-) can be used as formula sources - reference them by letter.')
            : '';

        fInput.value = th.dataset.colFormula || '';
        fInput.placeholder = I18N.formula_placeholder || 'e.g. ={A}.slice(0,3) + "_" + {B}';
        buildPreview(fInput.value.trim());
        fModal.style.display = 'flex';
        setTimeout(function () { fInput.focus(); fInput.selectionStart = fInput.selectionEnd = fInput.value.length; }, 50);
    }

    document.getElementById('bfm-apply').addEventListener('click', function () {
        if (!currentFormulaCol) return;
        var formula = fInput.value.trim();
        if (formula && formula.charAt(0) !== '=') formula = '=' + formula;
        applyColumnFormula(currentFormulaCol, formula);
        fModal.style.display = 'none';
    });

    document.getElementById('bfm-clear-formula').addEventListener('click', function () {
        if (!currentFormulaCol) return;
        applyColumnFormula(currentFormulaCol, '');
        fModal.style.display = 'none';
    });

    document.getElementById('bfm-cancel').addEventListener('click', function () { fModal.style.display = 'none'; });
    fModal.addEventListener('click', function (e) { if (e.target === fModal) fModal.style.display = 'none'; });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') fModal.style.display = 'none'; });

    // ---- Draft persistence (localStorage) ----
    var saveTimer = null;
    function saveDraft() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
            try {
                var cols = [];
                Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th) {
                    cols.push({key: th.querySelector('select').value, formula: th.dataset.colFormula || ''});
                });
                var n = colCount();
                var rowArrays = [];
                Array.prototype.forEach.call(tbody.rows, function (tr) {
                    var cells = [];
                    for (var i = 0; i < n; i++) {
                        var cell = tr.cells[i + 1]; // skip row-num cell at index 0
                        cells.push(cell ? (cell.dataset.formula || cell.textContent || '') : '');
                    }
                    rowArrays.push(cells);
                });
                localStorage.setItem(DRAFT_KEY, JSON.stringify({cols: cols, rows: rowArrays}));
            } catch (e) {}
        }, 400);
    }

    function loadDraft() {
        try {
            var raw = localStorage.getItem(DRAFT_KEY);
            if (!raw) return false;
            var draft = JSON.parse(raw);
            if (!draft || !draft.cols || !draft.rows || !draft.rows.length) return false;
            // Support both old format (cols as string[]) and new format (cols as {key,formula}[]).
            var keys = draft.cols.map(function (c) { return typeof c === 'string' ? c : c.key; });
            var formulas = draft.cols.map(function (c) { return typeof c === 'string' ? '' : (c.formula || ''); });
            reset(keys, draft.rows, 0);
            // Restore column-level formulas (don't re-apply - row values already computed).
            Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th, i) {
                if (formulas[i]) {
                    th.dataset.colFormula = formulas[i];
                    var btn = th.querySelector('.col-formula-btn');
                    if (btn) btn.classList.add('active');
                }
            });
            // Re-evaluate any per-cell formulas saved as '=...' text.
            Array.prototype.forEach.call(tbody.rows, function (tr) {
                Array.prototype.forEach.call(tr.querySelectorAll('td[contenteditable]'), function (td) {
                    if (td.textContent.charAt(0) === '=') {
                        td.dataset.formula = td.textContent;
                        var result = evaluateFormula(td.textContent, tr);
                        if (result !== undefined && result !== null) td.textContent = String(result);
                    }
                });
            });
            return true;
        } catch (e) { return false; }
    }

    table.addEventListener('input', saveDraft);

    // ---- Paste ----
    table.addEventListener('paste', function (e) {
        var text = (e.clipboardData || window.clipboardData).getData('text');
        if (text.indexOf('\t') === -1 && text.indexOf('\n') === -1) return;
        var anchor = e.target.closest && e.target.closest('td[contenteditable]');
        if (!anchor) return;
        e.preventDefault();
        var startCol = anchor.cellIndex;
        var startRow = anchor.parentNode.rowIndex - 1;
        var lines = text.replace(/\r/g, '').split('\n');
        if (lines.length && lines[lines.length - 1] === '') lines.pop();
        lines.forEach(function (line, ri) {
            var cells = line.split('\t');
            while ((startCol - 1) + cells.length > colCount()) addColumn('');
            while (startRow + ri >= tbody.rows.length) addRow();
            var tr = tbody.rows[startRow + ri];
            cells.forEach(function (val, ci) { tr.cells[startCol + ci].textContent = val; });
        });
        autoSizeColumns();
        saveDraft();
    });

    // ---- Collect grid -> list of dicts keyed by mapped field. ----
    function collect() {
        var fieldCol = {};
        Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th) {
            var key = th.querySelector('select').value;
            if (key && !(key in fieldCol)) fieldCol[key] = th.cellIndex;
        });
        var dnCheckbox = document.getElementById('bulk-dn-fullname');
        var copyDN = dnCheckbox && dnCheckbox.checked
            && ('fullname' in fieldCol) && !('username_display' in fieldCol);
        var out = [];
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            var row = {}, hasValue = false;
            Object.keys(fieldCol).forEach(function (key) {
                var val = (tr.cells[fieldCol[key]].textContent || '').trim();
                row[key] = val;
                if (val) hasValue = true;
            });
            if (copyDN) row.username_display = row.fullname || '';
            if (hasValue) out.push(row);
        });
        return {rows: out, mapped: fieldCol};
    }

    // ---- File loading (shared by upload button and drag-and-drop). ----
    function loadFile(file) {
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function (e) {
            try {
                var wb = XLSX.read(e.target.result, {type: 'array'});
                var ws = wb.Sheets[wb.SheetNames[0]];
                var aoa = XLSX.utils.sheet_to_json(ws, {header: 1, raw: false, defval: ''});
                var headers = (aoa[0] || []).map(function (h) { return h == null ? '' : String(h); });
                var rows = aoa.slice(1).filter(function (r) {
                    return r.some(function (c) { return String(c).trim() !== ''; });
                });
                reset(headers.map(matchField), rows, 0);
                saveDraft();
            } catch (err) { alert(I18N.parse_failed); }
        };
        reader.readAsArrayBuffer(file);
    }

    var fileInput = document.getElementById('bulk-file');
    document.getElementById('bulk-upload').addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () {
        if (!fileInput.files.length) return;
        loadFile(fileInput.files[0]);
        fileInput.value = '';
    });

    // ---- Drag-and-drop ----
    var gridWrap = document.getElementById('bulk-grid-wrap');
    gridWrap.addEventListener('dragover', function (e) { e.preventDefault(); gridWrap.classList.add('drag-over'); });
    gridWrap.addEventListener('dragleave', function () { gridWrap.classList.remove('drag-over'); });
    gridWrap.addEventListener('drop', function (e) {
        e.preventDefault();
        gridWrap.classList.remove('drag-over');
        var file = e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) loadFile(file);
    });

    // ---- Toolbar ----
    document.getElementById('bulk-clear').addEventListener('click', function () {
        if (!confirm(I18N.confirm_clear || 'Clear all data?')) return;
        reset(null, null, 3);
        localStorage.removeItem(DRAFT_KEY);
    });

    document.getElementById('bulk-export').addEventListener('click', function () {
        // Export ALL columns including ignored ones (header = field key or "col_A" for ignored).
        // "col_A" headers round-trip back as ignored columns on re-import since matchField won't map them.
        var colDefs = [];
        Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th) {
            var key = th.querySelector('select').value;
            colDefs.push({key: key, cellIdx: th.cellIndex, header: key || ('col_' + getColLetter(th))});
        });
        var rowArrays = [];
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            var hasVal = false, cells = [];
            colDefs.forEach(function (col) {
                var cell = tr.cells[col.cellIdx];
                var val = cell ? (cell.textContent || '').trim() : '';
                cells.push(val);
                if (val) hasVal = true;
            });
            if (hasVal) rowArrays.push(cells);
        });
        if (!rowArrays.length) { alert(I18N.nothing_to_export || 'Nothing to export.'); return; }
        var aoa = [colDefs.map(function (c) { return c.header; })].concat(rowArrays);
        var wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), 'Users');
        XLSX.writeFile(wb, 'bulk_users_draft.xlsx');
    });

    document.getElementById('bulk-create-form').addEventListener('submit', function (e) {
        var result = collect();
        if (!('username' in result.mapped) || result.rows.length === 0) {
            e.preventDefault();
            alert(I18N.need_required);
            return;
        }
        document.getElementById('id_rows_json').value = JSON.stringify(result.rows);
    });

    if (!loadDraft()) reset(null, null, 3);
    }

    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();
