/**
 * regional_report.js: Client-side logic for the Anonymous Regional Disease Report.
 */

document.addEventListener('DOMContentLoaded', () => {
    checkAuthAndRedirect(true); 
    
    loadFarmLocations();
    loadAllTreatments();
    setupEventListeners();
});

let regionalChartInstance = null;
let savedFarms = []; // New global variable to store farm data

// --- CRITICAL: Client-Side Severity Index (Kept for table/tooltip reference) ---
const DISEASE_SEVERITY_INDEX = {
    'Healthy': 0,
    'Sooty Mould': 1,
    'Powdery Mildew': 2,
    'Gall Midge': 2,
    'Anthracnose': 3,
    'Bacterial Canker': 3,
    'Cutting Weevil': 3,
    'die back': 3,
};

// Reuse the color map from user_statistic.js
const DISEASE_COLOR_MAP = {
    'Anthracnose': '#f0ad4e',
    'Bacterial Canker': '#337ab7',
    'Cutting Weevil': '#9966FF',
    'die back': '#dc3545',
    'Gall Midge': '#ffc107',
    'Powdery Mildew': '#20c997',
    'Sooty Mould': '#6c757d',
};

// --- NEW FUNCTIONS ---

/**
 * Loads the user's geo-tagged farm locations and populates the dropdown.
 */
async function loadFarmLocations() {
    const farmSelect = document.getElementById('farmSelect');
    
    try {
        // Assuming UserAPI.getFarms is defined in api.js
        const farms = await UserAPI.getFarms(); 
        
        // Filter to only include farms that have GPS coordinates
        savedFarms = farms.filter(f => f.latitude && f.longitude);
        
        if (savedFarms.length === 0) {
            farmSelect.innerHTML = '<option value="">-- No Geo-tagged Farms Found --</option>';
            farmSelect.disabled = true;
            return;
        }

        savedFarms.forEach(farm => {
            const option = document.createElement('option');
            // We use a combined value to make lookup easy
            option.value = `${farm.latitude},${farm.longitude}`; 
            option.textContent = `${farm.farm_name} (${farm.latitude}, ${farm.longitude})`;
            farmSelect.appendChild(option);
        });

        // Add change listener to the new dropdown
        farmSelect.addEventListener('change', handleFarmSelection);

    } catch (error) {
        farmSelect.innerHTML = '<option value="">-- Error Loading Farms --</option>';
        farmSelect.disabled = true;
        console.error("Failed to load user farms:", error);
    }
}

/**
 * Handles the selection of a farm from the dropdown, populating Latitude/Longitude fields.
 */
function handleFarmSelection(e) {
    const value = e.target.value;
    const latInput = document.getElementById('reportLatitude');
    const lonInput = document.getElementById('reportLongitude');
    
    // Clear manual inputs first
    latInput.value = '';
    lonInput.value = '';
    
    if (value) {
        // Split the combined lat,lon value
        const [lat, lon] = value.split(',');
        latInput.value = lat;
        lonInput.value = lon;
    }
}

/**
 * Loads all disease information for the static reference table.
 */
async function loadAllTreatments() {
    const container = document.getElementById('allDiseasesTreatment');
    if (!container) return;
    
    container.innerHTML = '<p>Loading static disease guide...</p>';

    try {
        const diseases = await apiCall('/api/user/diseases', 'GET');

        let tableHTML = `
            <h3 style="color: var(--primary-color); margin-top: 15px; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 5px;">
                Reference: Complete Disease Treatment Guide
            </h3>
            <table class="data-table" style="width: 100%; font-size: 0.9em;">
                <thead>
                    <tr>
                        <th>Disease</th>
                        <th>Organic Treatment</th>
                        <th>Chemical Treatment</th>
                    </tr>
                </thead>
                <tbody>
        `;

        diseases.forEach(disease => {
            if (disease.name === 'Healthy') return;
            
            tableHTML += `
                <tr>
                    <td style="font-weight: bold;">${disease.name}</td>
                    <td>${disease.organic_treatment || 'No specific organic treatment recorded.'}</td>
                    <td>${disease.chemical_treatment || 'No specific chemical treatment recorded.'}</td>
                </tr>
            `;
        });

        tableHTML += `
                </tbody>
            </table>
        `;
        
        container.innerHTML = tableHTML;
        
    } catch (error) {
        container.innerHTML = '<p style="color:red;">Failed to load static treatment guide.</p>';
    }
}
// --- END OF NEW FUNCTIONS ---


function setupEventListeners() {
    const detectButton = document.getElementById('autoDetectLocation');
    const generateButton = document.getElementById('generateReport');
    const latInput = document.getElementById('reportLatitude');
    const lonInput = document.getElementById('reportLongitude');

    // 1. Geolocation Logic
    detectButton.addEventListener('click', () => {
        if (!navigator.geolocation) {
            return displayMessage("Geolocation is not supported by your browser.", true);
        }
        
        detectButton.disabled = true;
        detectButton.textContent = 'Detecting...';
        displayMessage("Please allow browser location access.", false);
        
        // Clear farm selection if detecting a new location
        document.getElementById('farmSelect').value = ''; 

        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude.toFixed(8);
                const lon = position.coords.longitude.toFixed(8);
                latInput.value = lat;
                lonInput.value = lon;
                displayMessage("Location detected successfully!", false);
            },
            (error) => {
                displayMessage(`Error detecting location: ${error.message}. Enter manually.`, true);
            },
            { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
        );
        
        setTimeout(() => {
            detectButton.disabled = false;
            detectButton.textContent = 'Detect Current GPS';
        }, 1500);
    });
    
    // 2. Report Generation Logic
    generateButton.addEventListener('click', async () => {
        const latitude = latInput.value;
        const longitude = lonInput.value;
        
        if (!latitude || !longitude) {
            return displayMessage("Please enter or detect both Latitude and Longitude.", true);
        }
        
        generateButton.disabled = true;
        generateButton.textContent = 'Analyzing...';
        
        await loadRegionalStatistics(latitude, longitude);
        
        generateButton.disabled = false;
        generateButton.textContent = 'Generate Report';
    });
}

/**
 * Fetches regional disease counts (now unique affected trees) and renders the report.
 */
async function loadRegionalStatistics(latitude, longitude) {
    const chartMessage = document.getElementById('chartMessage');
    const summaryContainer = document.getElementById('regionalDataSummary');
    const treatmentContainer = document.getElementById('treatmentSummary'); 

    chartMessage.textContent = 'Fetching data from surrounding 5km...';
    
    // Clear previous results
    if (summaryContainer) summaryContainer.innerHTML = '';
    if (treatmentContainer) treatmentContainer.innerHTML = '';
    
    try {
        const endpoint = `/api/user/regional-stats?latitude=${latitude}&longitude=${longitude}`;
        const response = await apiCall(endpoint, 'GET'); 
        
        const regionalData = response.regional_data || {}; // Now holds unique tree counts
        const topTreatments = response.top_treatments || [];
        
        if (Object.keys(regionalData).length === 0) {
            chartMessage.textContent = response.message || 'No active diseased trees found within 5km.'; // Text update
            if (regionalChartInstance) regionalChartInstance.destroy();
            return;
        }
        
        renderRegionalChart(regionalData);
        renderSummaryTable(regionalData);
        renderTopTreatments(topTreatments); 
        
        displayMessage("Regional disease risk assessment loaded successfully.", false);

    } catch (error) {
        chartMessage.textContent = `Failed to load regional data: ${error.message}`;
        displayMessage(error.message || "Failed to load regional data.", true);
        if (regionalChartInstance) regionalChartInstance.destroy();
    }
}

/**
 * Renders the regional disease distribution Doughnut Chart.
 */
function renderRegionalChart(distributionData) {
    const canvas = document.getElementById('regionalDiseaseChartCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    const labels = Object.keys(distributionData);
    const rawCounts = Object.values(distributionData);
    const totalTrees = rawCounts.reduce((sum, count) => sum + count, 0); // Calculation uses tree count
    const colors = labels.map(label => DISEASE_COLOR_MAP[label] || '#cccccc');

    if (regionalChartInstance) {
        regionalChartInstance.destroy();
    }
    
    regionalChartInstance = new Chart(ctx, {
        type: 'doughnut', 
        data: {
            labels: labels,
            datasets: [{
                label: 'Affected Trees Count', // Label Update
                data: rawCounts,
                backgroundColor: colors,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false, 
            plugins: {
                legend: {
                    position: 'right',
                },
                title: {
                    display: true,
                    text: `Regional Disease Distribution (Total Affected Trees: ${totalTrees})` // Title Update
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const rawCount = context.raw;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = total > 0 ? ((rawCount / total) * 100).toFixed(1) + '%' : '0%';
                            
                            return `${label}: ${percentage} (${rawCount} affected tree${rawCount !== 1 ? 's' : ''})`; // Tooltip Update
                        }
                    }
                }
            }
        }
    });
}

/**
 * Renders the data table summary.
 */
function renderSummaryTable(distributionData) {
    const summaryContainer = document.getElementById('regionalDataSummary');
    if (!summaryContainer) return;
    
    const rawCounts = Object.values(distributionData);
    const totalTrees = rawCounts.reduce((sum, count) => sum + count, 0); // Calculation uses tree count

    let tableHTML = `
        <h4 style="margin-top: 30px; color: var(--primary-color);">Detailed Disease Breakdown (Affected Trees)</h4>
        <table class="data-table" style="width: 100%; margin-top: 15px;">
            <thead>
                <tr>
                    <th>Disease</th>
                    <th>Affected Trees</th> <th>Percentage</th>
                    <th>Severity Index</th>
                </tr>
            </thead>
            <tbody>
    `;

    const sortedEntries = Object.entries(distributionData)
        .sort(([, countA], [, countB]) => countB - countA);

    sortedEntries.forEach(([disease, count]) => {
        const percentage = totalTrees > 0 ? ((count / totalTrees) * 100).toFixed(1) + '%' : '0%';
        const severity = DISEASE_SEVERITY_INDEX[disease] || 'N/A';
        const severityColor = severity >= 3 ? 'red' : severity >= 2 ? 'orange' : 'green';
        
        tableHTML += `
            <tr>
                <td>${disease}</td>
                <td>${count}</td>
                <td>${percentage}</td>
                <td style="font-weight: bold; color: ${severityColor};">${severity}</td>
            </tr>
        `;
    });

    tableHTML += `
            <tr style="font-weight: bold; background-color: #f0f0f0;">
                <td>TOTAL</td>
                <td>${totalTrees}</td>
                <td>100.0%</td>
                <td>-</td>
            </tr>
            </tbody>
        </table>
    `;
    
    summaryContainer.innerHTML = tableHTML;
}

/**
 * Renders the treatment solutions for the top 2 diseases.
 */
function renderTopTreatments(topTreatments) {
    const treatmentContainer = document.getElementById('treatmentSummary');
    if (!treatmentContainer) return;

    if (topTreatments.length === 0) {
        treatmentContainer.innerHTML = '';
        return;
    }
    
    let treatmentsHTML = `
        <h2 style="color: #d9534f; margin-top: 40px; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 5px;">
            Action Plan: Top ${topTreatments.length} Regional Threats
        </h2>
        <p style="margin-bottom: 20px;">Based on regional data, here are the most effective treatments for the top prevalent diseases:</p>
    `;

    topTreatments.forEach((threat, index) => {
        const count = threat.count;
        const total = topTreatments.reduce((sum, t) => sum + t.count, 0);
        
        treatmentsHTML += `
            <div style="background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; border-left: 5px solid ${DISEASE_COLOR_MAP[threat.name] || '#333'};">
                <h3 style="color: var(--primary-color); margin-top: 0;">
                    ${index + 1}. ${threat.name} <span style="font-size: 0.9em; color: #777;">(${count} affected tree${count !== 1 ? 's' : ''} reported)</span>
                </h3>
                
                <h4 style="font-size: 1.1em; color: green; margin-top: 15px;">Organic Treatment:</h4>
                <p style="margin-left: 10px;">${threat.organic || 'No specific organic treatment recorded.'}</p>
                
                <h4 style="font-size: 1.1em; color: #d9534f; margin-top: 15px;">Chemical Treatment:</h4>
                <p style="margin-left: 10px;">${threat.chemical || 'No specific chemical treatment recorded.'}</p>
            </div>
        `;
    });
    
    treatmentContainer.innerHTML = treatmentsHTML;
}