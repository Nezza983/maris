// ==========================================
// MARIS - FRONTEND
// ==========================================


// ==========================================
// START ANALYSIS BUTTON
// ==========================================

document
    .getElementById("startAnalysis")
    .addEventListener("click", function () {

        document
            .getElementById("analysis")
            .scrollIntoView({
                behavior: "smooth"
            });

    });


// ==========================================
// LEAFLET MAP
// ==========================================

// DEMO coordinates
// These will later come from the backend.

const spillLocation = [15.35, 73.95];

const probableSource = [15.72, 73.48];

const driftPath = [
    probableSource,
    [15.62, 73.58],
    [15.53, 73.68],
    [15.45, 73.78],
    spillLocation
];


// Create map

const map = L.map("marisMap", {
    zoomControl: true
}).setView(spillLocation, 7);


// OpenStreetMap base layer

const baseMap = L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        attribution:
            '&copy; OpenStreetMap contributors'
    }
);

baseMap.addTo(map);


// ==========================================
// SPILL MARKER
// ==========================================

const spillIcon = L.divIcon({

    className: "maris-spill-marker",

    html: `
        <div style="
            width:18px;
            height:18px;
            background:#4fc3c8;
            border:3px solid #071014;
            border-radius:50%;
            box-shadow:0 0 18px #4fc3c8;
        "></div>
    `,

    iconSize: [18, 18],

    iconAnchor: [9, 9]

});


L.marker(
    spillLocation,
    {
        icon: spillIcon
    }
)
.addTo(map)
.bindPopup(`
    <strong>DETECTED SPILL</strong><br>
    Demo incident location
`);


// ==========================================
// PROBABLE SOURCE MARKER
// ==========================================

const sourceIcon = L.divIcon({

    className: "maris-source-marker",

    html: `
        <div style="
            width:15px;
            height:15px;
            background:#ffffff;
            border:3px solid #071014;
            border-radius:50%;
            box-shadow:0 0 15px #ffffff;
        "></div>
    `,

    iconSize: [15, 15],

    iconAnchor: [7, 7]

});


L.marker(
    probableSource,
    {
        icon: sourceIcon
    }
)
.addTo(map)
.bindPopup(`
    <strong>PROBABLE SOURCE</strong><br>
    Demo source location
`);


// ==========================================
// DRIFT TRAJECTORY
// ==========================================

const trajectory = L.polyline(
    driftPath,
    {
        color: "#4fc3c8",

        weight: 3,

        opacity: 0.85,

        dashArray: "8 8"
    }
)
.addTo(map);


// ==========================================
// FIT MAP TO TRAJECTORY
// ==========================================

map.fitBounds(
    trajectory.getBounds(),
    {
        padding: [50, 50]
    }
);


// ==========================================
// DEMO DATA
// ==========================================
//
// IMPORTANT:
// This is temporary.
//
// Later:
// Member 2 → detection
// Member 3 → environment / currents
// Member 4 → drift / age
// Member 5 → vessel correlation
//
// will replace these values.
// ==========================================

const demoData = {

    status: "DEMO",

    confidence: "—",

    oilAge: "—",

    movementDirection: "—",

    oceanCurrent: "—",

    wind: "—"

};


// ==========================================
// IMAGE UPLOAD
// ==========================================

document
    .getElementById("imageUpload")
    .addEventListener("change", function (event) {

        const file = event.target.files[0];

        if (!file) {
            return;
        }

        document
            .getElementById("fileName")
            .textContent = file.name;

        document
            .getElementById("dashboardStatus")
            .textContent = "READY";

        document
            .getElementById("dashboardConfidence")
            .textContent = "—";

    });
    // ==========================================
// MARIS LIVE MAP
// ==========================================

const marisMap = L.map("marisMap").setView(
    [15.35, 73.95],
    7
);


// OpenStreetMap base layer

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        attribution:
            '&copy; OpenStreetMap contributors'
    }
).addTo(marisMap);