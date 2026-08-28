// ==========================================
// MARIS - FRONTEND (integrated with real backend)
// ==========================================

const API_BASE = window.MARIS_API_BASE || "http://127.0.0.1:5000";

// ==========================================
// START ANALYSIS BUTTON (hero CTA -> scroll)
// ==========================================

document.getElementById("startAnalysis").addEventListener("click", function () {
    document.getElementById("analysis").scrollIntoView({ behavior: "smooth" });
});

// ==========================================
// LEAFLET MAP (single instance)
// ==========================================

const DEFAULT_CENTER = [15.35, 73.95];

const map = L.map("marisMap", { zoomControl: true }).setView(DEFAULT_CENTER, 7);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// Layer group so we can clear + redraw on each new analysis
let resultLayer = L.layerGroup().addTo(map);

function spillIcon() {
    return L.divIcon({
        className: "maris-spill-marker",
        html: `<div style="width:18px;height:18px;background:#4fc3c8;border:3px solid #071014;border-radius:50%;box-shadow:0 0 18px #4fc3c8;"></div>`,
        iconSize: [18, 18],
        iconAnchor: [9, 9]
    });
}

function sourceIcon() {
    return L.divIcon({
        className: "maris-source-marker",
        html: `<div style="width:15px;height:15px;background:#ffffff;border:3px solid #071014;border-radius:50%;box-shadow:0 0 15px #ffffff;"></div>`,
        iconSize: [15, 15],
        iconAnchor: [7, 7]
    });
}

function vesselIcon() {
    return L.divIcon({
        className: "maris-vessel-marker",
        html: `<div style="width:12px;height:12px;background:#ffb74d;border:2px solid #071014;border-radius:3px;box-shadow:0 0 10px #ffb74d;"></div>`,
        iconSize: [12, 12],
        iconAnchor: [6, 6]
    });
}

function renderResultOnMap(result) {
    resultLayer.clearLayers();

    const spillLatLng = [result.spill.latitude, result.spill.longitude];
    const sourceLatLng = [result.source.latitude, result.source.longitude];

    L.marker(spillLatLng, { icon: spillIcon() })
        .addTo(resultLayer)
        .bindPopup(`<strong>DETECTED SPILL</strong><br>Confidence: ${(result.detection.confidence * 100).toFixed(1)}%`);

    L.marker(sourceLatLng, { icon: sourceIcon() })
        .addTo(resultLayer)
        .bindPopup(`<strong>PROBABLE SOURCE</strong><br>Confidence: ${(result.source.confidence * 100).toFixed(0)}%<br>Radius: ${result.source.radius_km} km`);

    L.circle(sourceLatLng, {
        radius: result.source.radius_km * 1000,
        color: "#ffffff",
        weight: 1,
        fillOpacity: 0.08
    }).addTo(resultLayer);

    // Forward drift trajectory (predicted future positions)
    const driftPath = [spillLatLng, ...result.drift.predicted_positions.map(p => [p.latitude, p.longitude])];
    L.polyline(driftPath, { color: "#4fc3c8", weight: 3, opacity: 0.85, dashArray: "8 8" }).addTo(resultLayer);

    // Backward trace line (spill -> probable source)
    L.polyline([spillLatLng, sourceLatLng], { color: "#ffffff", weight: 2, opacity: 0.5, dashArray: "2 6" }).addTo(resultLayer);

    // Vessel tracks (GeoJSON from Module 5)
    if (result.vessel_tracks && result.vessel_tracks.features) {
        L.geoJSON(result.vessel_tracks, {
            style: { color: "#ffb74d", weight: 2, opacity: 0.7 }
        }).addTo(resultLayer);

        result.vessel_tracks.features.forEach(function (feature) {
            const coords = feature.geometry.coordinates;
            if (coords && coords.length) {
                const last = coords[coords.length - 1];
                L.marker([last[1], last[0]], { icon: vesselIcon() })
                    .addTo(resultLayer)
                    .bindPopup(`<strong>${feature.properties?.vessel_name || "Vessel"}</strong>`);
            }
        });
    }

    const bounds = L.latLngBounds([spillLatLng, sourceLatLng]);
    map.fitBounds(bounds, { padding: [60, 60] });
}

// ==========================================
// IMAGE UPLOAD
// ==========================================

let selectedFile = null;

document.getElementById("imageUpload").addEventListener("change", function (event) {
    const file = event.target.files[0];
    if (!file) return;

    selectedFile = file;
    document.getElementById("fileName").textContent = file.name;
    document.getElementById("dashboardStatus").textContent = "READY";
    document.getElementById("dashboardConfidence").textContent = "—";
});

// ==========================================
// PIPELINE LOADING STEP ANIMATION
// ==========================================

const ANALYSIS_STEPS = ["upload", "detect", "env", "drift", "ais", "report"];

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function resetSteps() {
    ANALYSIS_STEPS.forEach(function (step) {
        const row = document.querySelector(`.step-row[data-step="${step}"]`);
        row.classList.remove("step-active", "step-done");
    });
}

// Runs the cosmetic step-by-step readout, but the FINAL step genuinely
// waits on the real backend response before marking itself done.
async function playStepAnimation(fetchPromise) {
    const stepsEl = document.getElementById("analysisSteps");
    stepsEl.classList.add("active");
    resetSteps();

    for (let i = 0; i < ANALYSIS_STEPS.length - 1; i++) {
        const row = document.querySelector(`.step-row[data-step="${ANALYSIS_STEPS[i]}"]`);
        row.classList.add("step-active");
        await sleep(650);
        row.classList.remove("step-active");
        row.classList.add("step-done");
    }

    const lastStep = ANALYSIS_STEPS[ANALYSIS_STEPS.length - 1];
    const lastRow = document.querySelector(`.step-row[data-step="${lastStep}"]`);
    lastRow.classList.add("step-active");

    const result = await fetchPromise;

    lastRow.classList.remove("step-active");
    lastRow.classList.add("step-done");

    await sleep(300);
    stepsEl.classList.remove("active");

    return result;
}

// ==========================================
// RUN ANALYSIS -> call real backend
// ==========================================

document.getElementById("runAnalysis").addEventListener("click", async function () {
    const errorEl = document.getElementById("analysisError");
    const runBtn = document.getElementById("runAnalysis");
    errorEl.textContent = "";

    if (!selectedFile) {
        errorEl.textContent = "Select a SAR image first.";
        return;
    }

    runBtn.disabled = true;
    document.getElementById("dashboardStatus").textContent = "ANALYZING...";

    const formData = new FormData();
    formData.append("image", selectedFile);
    formData.append("latitude", document.getElementById("inputLat").value || "15.35");
    formData.append("longitude", document.getElementById("inputLon").value || "73.55");
    formData.append("timestamp", document.getElementById("inputTime").value || new Date().toISOString());

    const fetchPromise = fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        body: formData
    }).then(res => res.json());

    try {
        const result = await playStepAnimation(fetchPromise);

        if (!result.success) {
            errorEl.textContent = result.error || "Analysis failed.";
            document.getElementById("dashboardStatus").textContent = "ERROR";
            return;
        }

        renderResult(result);
    } catch (err) {
        errorEl.textContent = "Could not reach MARIS backend: " + err.message;
        document.getElementById("dashboardStatus").textContent = "ERROR";
    } finally {
        runBtn.disabled = false;
    }
});

function renderResult(result) {
    document.getElementById("dashboardStatus").textContent = result.status ? result.status.toUpperCase() : "COMPLETE";
    document.getElementById("incidentId").textContent = result.investigation_id;
    document.getElementById("dashboardConfidence").textContent = (result.detection.confidence * 100).toFixed(1) + "%";

    if (!result.detection.oil_detected) {
        document.getElementById("dashboardStatus").textContent = "NO SPILL DETECTED";
        return;
    }

    // Source / vessel card
    document.getElementById("sourceLat").textContent = result.source.latitude.toFixed(4);
    document.getElementById("sourceLon").textContent = result.source.longitude.toFixed(4);
    document.getElementById("sourceConfidence").textContent = (result.source.confidence * 100).toFixed(0) + "%";

    if (result.vessels && result.vessels.length > 0) {
        const top = result.vessels[0];
        document.getElementById("sourceVessel").textContent =
            `Top Candidate: ${top.vessel_name} (${(top.score * 100).toFixed(0)}%)`;
    } else {
        document.getElementById("sourceVessel").textContent = "No AIS candidates in range";
    }

    // Drift analysis card
    document.getElementById("oceanCurrent").textContent = result.environment.current_speed_ms + " m/s";
    document.getElementById("windSpeed").textContent = result.environment.wind_speed_ms + " m/s";
    const bearing = Math.atan2(result.environment.wind_u, result.environment.wind_v) * (180 / Math.PI);
    document.getElementById("movementDirection").textContent = ((bearing + 360) % 360).toFixed(0) + "°";
    const ageHrs = result.drift.oil_age_hours;
    document.getElementById("oilAge").textContent = ageHrs != null ? `~${ageHrs} hr (est.)` : "—";
    document.getElementById("oilAge").title = result.drift.oil_age_note || "";

    // Vessel list panel
    const vesselList = document.getElementById("vesselList");
    vesselList.innerHTML = "";
    (result.vessels || []).forEach(function (v) {
        const row = document.createElement("div");
        row.style.cssText = "display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.08); font-size:0.85rem;";
        row.innerHTML = `<span>#${v.rank} ${v.vessel_name} (${v.vessel_id})</span><span>${(v.score * 100).toFixed(0)}%</span>`;
        vesselList.appendChild(row);
    });

    renderResultOnMap(result);
}

// ==========================================
// SCROLL REVEAL
// ==========================================

document.addEventListener("DOMContentLoaded", function () {
    const revealEls = document.querySelectorAll(".reveal");

    const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add("in-view");
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15 });

    revealEls.forEach(function (el, index) {
        el.style.transitionDelay = (index % 4) * 0.08 + "s";
        observer.observe(el);
    });
});