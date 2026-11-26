"use strict";

const API_BASE = "/turfradar/api";
const state = { pages: 0, rows: new Map() };
const el = {};
const DATE_RE = /^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$/;
const INT_RE = /^[−-]?\d[\d\s]*$/;

function cacheElements() {
    for (const id of ["current-status","turfa-data","add-page","clear-import","parse-message","page-count","row-count","taken-count","take-total","preview-note","preview-body","import-data","import-message","unresolved-details","unresolved-list"]) {
        el[id] = document.getElementById(id);
    }
}

function parseInteger(value) {
    const normalized = value.replace(/\s/g, "").replace("−", "-");
    return Number.parseInt(normalized, 10);
}

function normalizeLines(text) {
    return text
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(
            /<a\b[^>]*>(.*?)<\/a>/gi,
            "$1"
        )
        .replace(/<[^>]+>/g, "")
        .replace(/&nbsp;/gi, " ")
        .replace(/&amp;/gi, "&")
        .replace(/&lt;/gi, "<")
        .replace(/&gt;/gi, ">")
        .replace(/&quot;/gi, "\"")
        .replace(/&#39;/gi, "'")
        .replace(/\r/g, "")
        .split("\n")
        .map(line =>
            line
                .replace(/\u00a0/g, " ")
                .trim()
        )
        .filter(Boolean);
}

function looksLikeName(value) {
    return value && !DATE_RE.test(value) && !INT_RE.test(value) && value.length <= 80;
}

function parseTurfaPage(text) {
    const rows = [];

    const lines = text
        .replace(/\r/g, "")
        .split("\n")
        .map(line => line.trim())
        .filter(Boolean);

    for (const line of lines) {
        const columns = line.split("\t");

        // A real Turfa TvT row starts with:
        // # | Name | Takes | First Contact | First Take | ...
        if (columns.length < 4) {
            continue;
        }

        const rowNumber = columns[0].trim();
        const name = columns[1].trim();
        const takesText = columns[2].trim();
        const firstContact = columns[3].trim();

        if (!/^\d+$/.test(rowNumber)) {
            continue;
        }

        if (!name) {
            continue;
        }

        const takes = parseInteger(takesText);

        if (!Number.isFinite(takes) || takes < 0) {
            continue;
        }

        let firstTake = null;

        /*
         * Turfa columns:
         *
         * 0  #
         * 1  Name
         * 2  Takes
         * 3  First Contact
         * 4  First Take
         *
         * When Takes > 0, column 4 is the historical
         * first time we took from this player.
         */
        if (
            takes > 0 &&
            columns[4] &&
            DATE_RE.test(columns[4].trim())
        ) {
            firstTake =
                columns[4].trim().replace(" ", "T")
                + ":00+00:00";
        }

        rows.push({
            name,
            takes,
            firstTake
        });
    }

    return rows;
}
function addRows(rows) {
    for (const row of rows) {
        const key = row.name.normalize("NFKC").trim().toLocaleLowerCase("sv-SE");
        const existing = state.rows.get(key);
        if (!existing || row.takes > existing.takes) state.rows.set(key, row);
    }
}

function render() {
    const rows = [...state.rows.values()].sort((a, b) => b.takes - a.takes || a.name.localeCompare(b.name, "sv"));
    const taken = rows.filter(row => row.takes > 0);
    const total = taken.reduce((sum, row) => sum + row.takes, 0);

    el["page-count"].textContent = state.pages.toLocaleString("sv-SE");
    el["row-count"].textContent = rows.length.toLocaleString("sv-SE");
    el["taken-count"].textContent = taken.length.toLocaleString("sv-SE");
    el["take-total"].textContent = total.toLocaleString("sv-SE");
    el["import-data"].disabled = taken.length === 0;
    el["preview-note"].textContent = taken.length ? `Visar ${Math.min(taken.length, 200)} av ${taken.length}` : "Inga sidor tillagda";
    el["preview-body"].replaceChildren();

    for (const row of taken.slice(0, 200)) {
        const tr = document.createElement("tr");
        for (const value of [row.name, row.takes.toLocaleString("sv-SE"), row.firstTake ? row.firstTake.slice(0, 10) : "-"]) {
            const td = document.createElement("td");
            td.textContent = value;
            tr.appendChild(td);
        }
        el["preview-body"].appendChild(tr);
    }
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
    return data;
}

async function loadStatus() {
    try {
        const status = await requestJson(`${API_BASE}/import/turfa/status`);
        if (status.importedPlayers > 0) {
            const when = status.lastImportedAt ? new Date(status.lastImportedAt).toLocaleString("sv-SE") : "okänd tid";
            el["current-status"].classList.add("success");
            el["current-status"].textContent = `Tidigare import: ${status.importedPlayers.toLocaleString("sv-SE")} turfare, ${status.importedTakes.toLocaleString("sv-SE")} takes. Senast ${when}.`;
        } else {
            el["current-status"].textContent = "Ingen Turfa-historik har importerats ännu.";
        }
    } catch (error) {
        if (/401|authenticated|session/i.test(error.message)) {
            location.href = "/turfradar/";
            return;
        }
        el["current-status"].textContent = "Kunde inte läsa importstatus.";
    }
}

function addPage() {
    const text = el["turfa-data"].value;
    if (!text.trim()) {
        el["parse-message"].className = "message error";
        el["parse-message"].textContent = "Klistra in en Turfa-sida först.";
        return;
    }

    const parsed = parseTurfaPage(text);
    if (!parsed.length) {
        el["parse-message"].className = "message error";
        el["parse-message"].textContent = "Ingen tabell kunde tolkas. Kopiera hela Turfer vs Turfer-sidan inklusive raderna.";
        return;
    }

    const positives = parsed.filter(row => row.takes > 0).length;
    addRows(parsed);
    state.pages += 1;
    el["turfa-data"].value = "";
    el["parse-message"].className = "message success";
    el["parse-message"].textContent = `Sida ${state.pages} tillagd: ${parsed.length} turfare, ${positives} med Takes > 0.`;
    render();
}

function clearImport() {
    state.pages = 0;
    state.rows.clear();
    el["turfa-data"].value = "";
    el["parse-message"].textContent = "";
    el["import-message"].textContent = "";
    el["unresolved-details"].hidden = true;
    render();
}

async function importData() {
    const rows = [...state.rows.values()].filter(row => row.takes > 0);
    if (!rows.length) return;

    el["import-data"].disabled = true;
    el["import-message"].className = "message";
    el["import-message"].textContent = `Slår upp och importerar ${rows.length.toLocaleString("sv-SE")} turfare. Det kan ta en stund...`;

    try {
        const result = await requestJson(`${API_BASE}/import/turfa`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows }),
        });

        el["import-message"].className = "message success";
        el["import-message"].textContent = `Klart: ${result.imported.toLocaleString("sv-SE")} av ${result.submitted.toLocaleString("sv-SE")} turfare importerades.`;

        el["unresolved-list"].replaceChildren();
        if (result.unresolvedCount > 0) {
            el["unresolved-details"].hidden = false;
            for (const name of result.unresolved) {
                const li = document.createElement("li");
                li.textContent = name;
                el["unresolved-list"].appendChild(li);
            }
        } else {
            el["unresolved-details"].hidden = true;
        }
        await loadStatus();
    } catch (error) {
        el["import-message"].className = "message error";
        el["import-message"].textContent = `Importen misslyckades: ${error.message}`;
        el["import-data"].disabled = false;
    }
}

function initialize() {
    cacheElements();
    el["add-page"].addEventListener("click", addPage);
    el["clear-import"].addEventListener("click", clearImport);
    el["import-data"].addEventListener("click", importData);
    render();
    loadStatus();
}

document.addEventListener("DOMContentLoaded", initialize);
