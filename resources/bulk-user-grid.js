// Minimal editable grid for bulk user creation. Vanilla JS (jQuery only for the AJAX upload).
// Supports typing, Ctrl+V paste (TSV from Excel/Sheets), .xlsx upload, and per-column field mapping.
// ponytail: hand-rolled grid, one-use only — swap for a lib if this UI ever grows.
(function () {
    'use strict';

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

    // Map a raw header string to a field key, matching key/label case-insensitively plus a few aliases.
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
        opt.textContent = I18N.ignore || '— ignore —';
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

    function colCount() {
        return headRow.querySelectorAll('th.col-head').length;
    }

    function addColumn(mappedKey) {
        var th = document.createElement('th');
        th.className = 'col-head';
        var del = document.createElement('span');
        del.className = 'col-del';
        del.textContent = '×';
        del.title = 'Delete column';
        del.addEventListener('click', function () {
            if (colCount() <= 1) return;  // keep at least one column
            var idx = th.cellIndex;
            Array.prototype.forEach.call(tbody.rows, function (tr) { tr.deleteCell(idx); });
            headRow.removeChild(th);
        });
        th.appendChild(del);
        th.appendChild(buildSelect(mappedKey));
        headRow.insertBefore(th, actionsHead);
        // Add a matching cell to every existing body row (before its actions cell).
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            tr.insertBefore(makeCell(), tr.lastElementChild);
        });
    }

    function makeCell() {
        var td = document.createElement('td');
        td.setAttribute('contenteditable', 'true');
        return td;
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
        act.title = 'Delete row';
        act.addEventListener('click', function () {
            tr.parentNode.removeChild(tr);
            if (tbody.rows.length === 0) addRow();
            renumber();
        });
        tr.appendChild(act);
        tbody.appendChild(tr);
        renumber();
        return tr;
    }

    // Trailing (fixed) header cell above the row-actions column.
    var actionsHead = document.createElement('th');
    headRow.appendChild(actionsHead);

    // Leading (fixed) header cell above the row-number column.
    var leadHead = document.createElement('th');
    leadHead.className = 'row-num-head';
    leadHead.textContent = '#';
    headRow.insertBefore(leadHead, headRow.firstChild);

    function renumber() {
        Array.prototype.forEach.call(tbody.rows, function (tr, i) { tr.cells[0].textContent = i + 1; });
    }

    function reset(columnKeys, rowsData, blankRows) {
        headRow.querySelectorAll('th.col-head').forEach(function (th) { headRow.removeChild(th); });
        while (tbody.rows.length) tbody.deleteRow(0);
        (columnKeys && columnKeys.length ? columnKeys : ['username', 'fullname'])
            .forEach(function (k) { addColumn(k); });
        if (rowsData) rowsData.forEach(function (r) { addRow(r); });
        for (var i = 0; i < (blankRows || 0); i++) addRow();
        if (tbody.rows.length === 0) addRow();
    }

    // ---- Paste (Ctrl+V): fill the grid from clipboard TSV, growing rows/columns as needed. ----
    table.addEventListener('paste', function (e) {
        var text = (e.clipboardData || window.clipboardData).getData('text');
        if (text.indexOf('\t') === -1 && text.indexOf('\n') === -1) return; // single cell: let browser handle
        var anchor = e.target.closest && e.target.closest('td[contenteditable]');
        if (!anchor) return;
        e.preventDefault();
        var startCol = anchor.cellIndex;
        var startRow = anchor.parentNode.rowIndex - 1; // minus header row
        var lines = text.replace(/\r/g, '').split('\n');
        if (lines.length && lines[lines.length - 1] === '') lines.pop();
        lines.forEach(function (line, ri) {
            var cells = line.split('\t');
            // startCol is an actual cellIndex; data columns start after the row-number gutter (index 1).
            while ((startCol - 1) + cells.length > colCount()) addColumn('');
            while (startRow + ri >= tbody.rows.length) addRow();
            var tr = tbody.rows[startRow + ri];
            cells.forEach(function (val, ci) {
                tr.cells[startCol + ci].textContent = val;
            });
        });
    });

    // ---- Collect grid -> list of dicts keyed by mapped field. ----
    function collect() {
        var fieldCol = {};
        // Map field -> actual cell index (col-head th.cellIndex accounts for the row-number gutter).
        Array.prototype.forEach.call(headRow.querySelectorAll('th.col-head'), function (th) {
            var key = th.querySelector('select').value;
            if (key && !(key in fieldCol)) fieldCol[key] = th.cellIndex;
        });
        var out = [];
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            var row = {}, hasValue = false;
            Object.keys(fieldCol).forEach(function (key) {
                var val = (tr.cells[fieldCol[key]].textContent || '').trim();
                row[key] = val;
                if (val) hasValue = true;
            });
            if (hasValue) out.push(row);
        });
        return {rows: out, mapped: fieldCol};
    }

    // ---- Wire up toolbar + form ----
    document.getElementById('bulk-add-row').addEventListener('click', function () { addRow(); });
    document.getElementById('bulk-add-col').addEventListener('click', function () { addColumn(''); });
    document.getElementById('bulk-clear').addEventListener('click', function () { reset(null, null, 3); });

    var fileInput = document.getElementById('bulk-file');
    document.getElementById('bulk-upload').addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () {
        if (!fileInput.files.length) return;
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
            } catch (err) {
                alert(I18N.parse_failed);
            }
        };
        reader.readAsArrayBuffer(fileInput.files[0]);
        fileInput.value = '';
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

    reset(null, null, 3);
    }

    // js_media renders in <head>, before the grid exists — run once the DOM is ready.
    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();
