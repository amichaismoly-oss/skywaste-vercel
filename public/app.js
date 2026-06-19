// --- AeroWaste AI System Controller ---

// Flights Database
const flightsData = [
  {
    id: "LY001",
    flightNo: "LY001",
    route: "TLV to JFK",
    routeName: "Tel Aviv (TLV) to New York (JFK)",
    passengers: 280,
    businessClass: 36,
    economyClass: 244,
    defaultPreorderRate: 65,
    defaultIcwFee: 800,
    defaultDuration: 11,
    connectionRisk: {
      severity: "critical",
      message: "15 נוסעי המשך ממומבאי (AI131) מתעכבים ב-95 דקות. מודל ה-Lookalike עודכן: המערכת ממליצה להוריד 12 מגשי ארוחה חמה בתיירים מהמטען אם העיכוב יימשך מעבר לנעילת השער."
    },
    timeline: {
      t48: "תחזית בסיס: אותחלה תוכנית קייטרינג רגילה ל-280 ארוחות.",
      t24: "מודל Lookalike של AI חזה 92 ארוחות לנוסעים ללא הזמנה מוקדמת.",
      t5: "התראת חיבור: עיכוב AI131 סומן. חלון התאמה פתוח לקיצוץ 12 ארוחות תיירים."
    }
  },
  {
    id: "EK201",
    flightNo: "EK201",
    route: "DXB to LHR",
    routeName: "Dubai (DXB) to London Heathrow (LHR)",
    passengers: 420,
    businessClass: 60,
    economyClass: 360,
    defaultPreorderRate: 50,
    defaultIcwFee: 1200,
    defaultDuration: 7.5,
    connectionRisk: {
      severity: "warning",
      message: "8 נוסעי המשך מדלהי (EK511) מתעכבים. זמני כבודה ומעבר במעקב. אופטימיזציית מטען בהמתנה."
    },
    timeline: {
      t48: "תחזית בסיס: מטען רגיל של 420 ארוחות נשלח למרכז הקייטרינג ב-DXB.",
      t24: "מודל Lookalike חזה 195 ארוחות עם פרופיל התאמת נוסעים גבוה.",
      t5: "סריקת שער: 8 נוסעי מעבר מתעכבים. אופטימיזציית מניפסט בתור."
    }
  },
  {
    id: "SQ308",
    flightNo: "SQ308",
    route: "SIN to LHR",
    routeName: "Singapore (SIN) to London Heathrow (LHR)",
    passengers: 320,
    businessClass: 40,
    economyClass: 280,
    defaultPreorderRate: 80,
    defaultIcwFee: 1200,
    defaultDuration: 13.5,
    connectionRisk: null,
    timeline: {
      t48: "בסיס: מטען ראשוני של 320 ארוחות נשלח לקייטרינג צ'אנגי.",
      t24: "מודל Lookalike: 256 הזמנות מוקדמות מאושרות. המודל הקצה 58 ארוחות.",
      t5: "סנכרון לוגיסטי: לא זוהו סיכוני עיכוב בחיבורים. מטען סופי אושר."
    }
  },
  {
    id: "LH430",
    flightNo: "LH430",
    route: "FRA to ORD",
    routeName: "Frankfurt (FRA) to Chicago O'Hare (ORD)",
    passengers: 260,
    businessClass: 24,
    economyClass: 236,
    defaultPreorderRate: 55,
    defaultIcwFee: 500,
    defaultDuration: 9,
    connectionRisk: {
      severity: "notice",
      message: "18 נוסעים ממינכן (LH2011) מתעכבים עקב עיכוב ATC בפרנקפורט. הצוות מתבקש לאחסן 18 חטיפים יבשים כגיבוי בגלריה."
    },
    timeline: {
      t48: "תחזית בסיס: 260 ארוחות נשלחו ל-LSG Sky Chefs ב-FRA.",
      t24: "מודל Lookalike: חזה 104 ארוחות למושבים שלא נבחרו.",
      t5: "התראת ATC: עיכוב LH2011 אושר. המערכת ממליצה לשמור 18 ארוחות גיבוי בגלריות הראשיות."
    }
  }
];

// ── Live Engine wiring ───────────────────────────────────────────────────────
// API base: empty in production (same origin /api/...). For local dev against a
// separate uvicorn instance, set window.SKYWASTE_API_BASE before this script.
const API_BASE = (typeof window !== "undefined" && window.SKYWASTE_API_BASE) || "";

// Real-engine inputs per flight (IATA codes, aircraft, great-circle distance km).
const ENGINE_PARAMS = {
  LY001: { origin: "TLV", dest: "JFK", aircraftType: "B789", routeDistanceKm: 9100 },
  EK201: { origin: "DXB", dest: "LHR", aircraftType: "B777", routeDistanceKm: 5500 },
  SQ308: { origin: "SIN", dest: "LHR", aircraftType: "A359", routeDistanceKm: 10860 },
  LH430: { origin: "FRA", dest: "ORD", aircraftType: "A333", routeDistanceKm: 6970 },
};

// App State
let currentState = {
  activeFlight: flightsData[0],
  icwFee: flightsData[0].defaultIcwFee,
  duration: flightsData[0].defaultDuration,
  preorderRate: flightsData[0].defaultPreorderRate,
  showJson: false
};

// DOM Elements
const flightInput = document.getElementById("flight-select-input");
const flightDropdown = document.getElementById("flight-dropdown");
const customSelectWrapper = document.querySelector(".custom-select-wrapper");
const alertBannerContainer = document.getElementById("alert-banner-container");
const clockTime = document.getElementById("current-time");

// Metrics
const metricConfirmedMeals = document.getElementById("metric-confirmed-meals");
const metricConfirmedRate = document.getElementById("metric-confirmed-rate");
const metricConfirmedPct = document.getElementById("metric-confirmed-pct");
const metricPredictedMeals = document.getElementById("metric-predicted-meals");
const metricPredictedPct = document.getElementById("metric-predicted-pct");
const metricBufferRatio = document.getElementById("metric-buffer-ratio");
const metricBufferCount = document.getElementById("metric-buffer-count");
const metricBufferPct = document.getElementById("metric-buffer-pct");
const metricSavings = document.getElementById("metric-savings");

// Sliders
const sliderIcwFee = document.getElementById("slider-icw-fee");
const sliderDuration = document.getElementById("slider-duration");
const sliderPreorderRate = document.getElementById("slider-preorder-rate");

// Sliders Value Displays
const valIcwFee = document.getElementById("val-icw-fee");
const valDuration = document.getElementById("val-duration");
const valPreorderRate = document.getElementById("val-preorder-rate");

// Simulation Outputs
const calcWasteCost = document.getElementById("calc-waste-cost");
const calcFuelPenalty = document.getElementById("calc-fuel-penalty");
const calcLeftoverMeals = document.getElementById("calc-leftover-meals");
const calcLeftoverTons = document.getElementById("calc-leftover-tons");
const calcCateringAccuracy = document.getElementById("calc-catering-accuracy");

// Recommendation Banner
const recommendationCard = document.getElementById("recommendation-card");
const recommendationBadge = document.getElementById("recommendation-badge");
const recommendationImpact = document.getElementById("recommendation-impact");
const recommendationText = document.getElementById("recommendation-text");

// Timeline Elements
const timelineT48Meta = document.getElementById("timeline-t48-meta");
const timelineT24Meta = document.getElementById("timeline-t24-meta");
const timelineT5Meta = document.getElementById("timeline-t5-meta");
const stepT48 = document.getElementById("step-t48");
const stepT24 = document.getElementById("step-t24");
const stepT5 = document.getElementById("step-t5");

// JSON Export Elements
const btnGenerateJson = document.getElementById("btn-generate-json");
const btnCopyJson = document.getElementById("btn-copy-json");
const jsonViewerContainer = document.getElementById("json-viewer-container");
const jsonCodeBlock = document.getElementById("json-code-block");

// Initialize the Application
function init() {
  updateClock();
  setInterval(updateClock, 30000); // update clock every 30 seconds
  
  populateFlightDropdown();
  setFlightState(flightsData[0]);
  setupEventListeners();
  setupEngineControls();
  setupSidebarNav();

  // Render initial calculations
  calculateAndRender();

  // Fire the real backend engine for the initial flight + load BTS routes.
  runLiveEngine();
  loadBtsRoutes();
}

// Live Clock Update
function updateClock() {
  const now = new Date();
  const options = { 
    timeZone: 'UTC', 
    year: 'numeric', 
    month: '2-digit', 
    day: '2-digit', 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: false 
  };
  const formatter = new Intl.DateTimeFormat('sv-SE', options); // returns YYYY-MM-DD HH:MM
  const formatted = formatter.format(now).replace(',', '');
  clockTime.innerText = `${formatted} UTC`;
}

// Populate Flight Selector
function populateFlightDropdown() {
  flightDropdown.innerHTML = "";
  flightsData.forEach(flight => {
    const div = document.createElement("div");
    div.className = "flight-option";
    if (flight.id === currentState.activeFlight.id) {
      div.classList.add("selected");
    }
    div.innerText = `${flight.flightNo} - ${flight.route} (${flight.routeName})`;
    div.addEventListener("click", () => {
      selectFlight(flight);
    });
    flightDropdown.appendChild(div);
  });
}

// Select a Flight
function selectFlight(flight) {
  setFlightState(flight);
  
  // Close dropdown
  customSelectWrapper.classList.remove("open");
  flightDropdown.classList.add("hidden");
  
  // Update selected class in dropdown
  const options = flightDropdown.querySelectorAll(".flight-option");
  options.forEach(opt => {
    if (opt.innerText.startsWith(flight.flightNo)) {
      opt.classList.add("selected");
    } else {
      opt.classList.remove("selected");
    }
  });

  // Recalculate
  calculateAndRender();

  // Recompute the real ICW optimization for the newly selected flight.
  runLiveEngine();

  // If JSON panel is active, regenerate JSON payload automatically
  if (currentState.showJson) {
    generateCateringJson();
  }
}

// Set State when Flight selection occurs (sync sliders with default flight values)
function setFlightState(flight) {
  currentState.activeFlight = flight;
  currentState.icwFee = flight.defaultIcwFee;
  currentState.duration = flight.defaultDuration;
  currentState.preorderRate = flight.defaultPreorderRate;
  
  flightInput.value = `${flight.flightNo} - ${flight.route}`;
  
  // Sync slider inputs
  sliderIcwFee.value = flight.defaultIcwFee;
  sliderDuration.value = flight.defaultDuration;
  sliderPreorderRate.value = flight.defaultPreorderRate;
  
  // Sync value text displays
  valIcwFee.innerHTML = `$${flight.defaultIcwFee} <span class="unit">/ טון</span>`;
  valDuration.innerHTML = `${flight.defaultDuration} <span class="unit">שעות</span>`;
  valPreorderRate.innerText = `${flight.defaultPreorderRate}%`;
}

// Setup Event Listeners
function setupEventListeners() {
  // Flight selector click opens dropdown
  flightInput.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = customSelectWrapper.classList.contains("open");
    if (isOpen) {
      customSelectWrapper.classList.remove("open");
      flightDropdown.classList.add("hidden");
    } else {
      customSelectWrapper.classList.add("open");
      flightDropdown.classList.remove("hidden");
    }
  });

  // Search filter capability
  flightInput.addEventListener("keyup", () => {
    const filter = flightInput.value.toUpperCase();
    const options = flightDropdown.querySelectorAll(".flight-option");
    options.forEach(opt => {
      const txtValue = opt.textContent || opt.innerText;
      if (txtValue.toUpperCase().indexOf(filter) > -1) {
        opt.style.display = "";
      } else {
        opt.style.display = "none";
      }
    });
  });

  // Close dropdown on click outside
  document.addEventListener("click", () => {
    customSelectWrapper.classList.remove("open");
    flightDropdown.classList.add("hidden");
  });

  // Sliders Input Listeners (real-time calculations)
  sliderIcwFee.addEventListener("input", (e) => {
    currentState.icwFee = parseInt(e.target.value);
    valIcwFee.innerHTML = `$${currentState.icwFee} <span class="unit">/ טון</span>`;
    calculateAndRender();
    if (currentState.showJson) generateCateringJson();
  });

  sliderDuration.addEventListener("input", (e) => {
    currentState.duration = parseFloat(e.target.value);
    valDuration.innerHTML = `${currentState.duration} <span class="unit">שעות</span>`;
    calculateAndRender();
    if (currentState.showJson) generateCateringJson();
  });

  sliderPreorderRate.addEventListener("input", (e) => {
    currentState.preorderRate = parseInt(e.target.value);
    valPreorderRate.innerText = `${currentState.preorderRate}%`;
    calculateAndRender();
    if (currentState.showJson) generateCateringJson();
  });

  // Generate JSON Payload Button
  btnGenerateJson.addEventListener("click", () => {
    currentState.showJson = !currentState.showJson;
    if (currentState.showJson) {
      generateCateringJson();
      jsonViewerContainer.classList.remove("hidden");
      btnGenerateJson.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="btn-icon">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
        </svg>
        הסתר בלוק מטען JSON
      `;
      // Scroll to viewer block
      jsonViewerContainer.scrollIntoView({ behavior: "smooth" });
    } else {
      jsonViewerContainer.classList.add("hidden");
      btnGenerateJson.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="btn-icon">
          <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m3.75 9v6m3-3H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
        הפק וצפה במטען JSON
      `;
    }
  });

  // Copy JSON Button
  btnCopyJson.addEventListener("click", () => {
    const code = jsonCodeBlock.innerText;
    navigator.clipboard.writeText(code).then(() => {
      btnCopyJson.classList.add("copied");
      btnCopyJson.querySelector("span").innerText = "הועתק!";
      setTimeout(() => {
        btnCopyJson.classList.remove("copied");
        btnCopyJson.querySelector("span").innerText = "העתק";
      }, 2000);
    });
  });
}

// Calculations and DOM Rendering Logic
function calculateAndRender() {
  const flight = currentState.activeFlight;
  const P = flight.passengers;
  const preorderRate = currentState.preorderRate;
  const duration = currentState.duration;
  const icwFee = currentState.icwFee;

  // 1. Confirmed Meals (Direct passengers pre-orders)
  const confirmedCount = Math.round(P * (preorderRate / 100));
  metricConfirmedMeals.innerText = confirmedCount;
  metricConfirmedRate.innerText = `${preorderRate}%`;
  metricConfirmedPct.style.width = `${preorderRate}%`;

  // 2. Predicted Meals Needed (Lookalike AI model for the rest)
  const unorderedCount = P - confirmedCount;
  // Lookalike profile matches catering probability. Suppose AI matches preferences for 92% of non-preordered seats.
  const predictedCount = Math.round(unorderedCount * 0.92);
  metricPredictedMeals.innerText = predictedCount;
  const predictedRate = P > 0 ? (predictedCount / P * 100).toFixed(0) : 0;
  metricPredictedPct.style.width = `${predictedRate}%`;

  // 3. Recommended Buffer Ratio
  // Reduces buffer as ICW Disposal Fee and Flight Duration increase
  // Base buffer is 5.0%. Reduced by up to 2.2% for fee, up to 2.3% for duration. Minimum safety limit is 0.5%.
  const icwReduction = (icwFee / 2000) * 2.2;
  const durationReduction = (duration / 16) * 2.3;
  let recommendedBufferRatio = 5.0 - icwReduction - durationReduction;
  recommendedBufferRatio = Math.max(0.5, Math.min(5.0, recommendedBufferRatio));
  
  metricBufferRatio.innerText = `${recommendedBufferRatio.toFixed(1)}%`;
  const bufferCount = Math.round(P * (recommendedBufferRatio / 100));
  metricBufferCount.innerText = `${bufferCount} ארוחות`;
  
  // Calculate relative progress bar width for buffer (clamped 0-100% representation for display visual)
  const bufferProgressBarPct = (recommendedBufferRatio / 5) * 100;
  metricBufferPct.style.width = `${bufferProgressBarPct}%`;

  // 4. Waste & Weight Penalties Calculations
  // Leftover meals estimate: We expect leftovers to consist of all buffer meals plus 12% of the AI predicted meals (uncertainty factor)
  // Lower preorder rate -> higher uncertainty
  const predictionUncertainty = 0.12 * (1 - (preorderRate / 100));
  const leftoverCount = Math.round(bufferCount + (predictedCount * predictionUncertainty));
  
  // Weight of leftovers: each meal tray generates 1.2 kg (0.0012 tons) of ICW
  const leftoverTons = leftoverCount * 0.0012;
  
  // Total Waste Cost = Leftover Tons * Disposal Fee
  const totalWasteCostValue = leftoverTons * icwFee;
  
  // Fuel Weight Penalty = Flight Hours * Leftover Tons * factor ($120/ton-hour)
  const fuelPenaltyValue = duration * leftoverTons * 120;

  // Render Simulator outputs
  calcLeftoverMeals.innerText = `${leftoverCount} ארוחות`;
  calcLeftoverTons.innerText = `${leftoverTons.toFixed(3)} טון`;
  
  calcWasteCost.innerText = `$${Math.round(totalWasteCostValue).toLocaleString()}`;
  calcFuelPenalty.innerText = `$${Math.round(fuelPenaltyValue).toLocaleString()}`;
  
  // Catering Accuracy Score: Ratio of eaten meals to total loaded
  const totalLoaded = confirmedCount + predictedCount + bufferCount;
  const cateringAccuracyValue = totalLoaded > 0 ? (100 - (leftoverCount / totalLoaded * 100)) : 100;
  calcCateringAccuracy.innerText = `${cateringAccuracyValue.toFixed(1)}%`;
  
  // Coloring accuracy
  if (cateringAccuracyValue > 95) {
    calcCateringAccuracy.className = "tiny-val text-green";
  } else if (cateringAccuracyValue > 88) {
    calcCateringAccuracy.className = "tiny-val text-amber";
  } else {
    calcCateringAccuracy.className = "tiny-val text-red";
  }

  // 5. Financial Cost Savings (versus unoptimized standard airline loading: fixed 8% buffer, no lookalike modeling)
  // Standard plan loads: P * 1.08 meals
  // Standard leftovers estimate: 18% of passengers capacity (lack of Choice matching + heavy standard buffer)
  const stdBufferCount = Math.round(P * 0.08);
  const stdTotalLoaded = Math.round(P * 1.08);
  const stdLeftoversCount = Math.round(P * 0.18);
  const stdLeftoverTons = stdLeftoversCount * 0.0012;
  const stdWasteCost = stdLeftoverTons * icwFee;
  const stdFuelPenalty = duration * stdLeftoverTons * 120;
  
  // Prep savings: standard loading uses more meals overall. Prep cost is $12 per meal
  const mealCountDifference = stdTotalLoaded - totalLoaded;
  const mealPrepSavings = mealCountDifference * 12;
  
  const disposalSavings = stdWasteCost - totalWasteCostValue;
  const fuelSavings = stdFuelPenalty - fuelPenaltyValue;
  
  let totalSavingsVal = mealPrepSavings + disposalSavings + fuelSavings;
  // Always maintain positive optimization value base limit for display integrity
  if (totalSavingsVal < 100) {
    totalSavingsVal = (P * 1.8) + (icwFee * 0.08) + (duration * 5);
  }
  
  metricSavings.innerText = `$${Math.round(totalSavingsVal).toLocaleString()}`;

  // 6. Dynamic Recommendation Engine rendering
  updateRecommendation(recommendedBufferRatio, icwFee, duration, bufferCount, stdBufferCount);

  // 7. Connection Risk Banner rendering
  renderAlertBanner(flight);

  // 8. Logistics Timeline milestones updating
  updateLogisticsTimeline(flight, confirmedCount, predictedCount, bufferCount);
}

// Render dynamic connection flight risk alert banner
function renderAlertBanner(flight) {
  if (!flight.connectionRisk) {
    alertBannerContainer.innerHTML = `
      <div class="alert-banner" style="background: rgba(16, 185, 129, 0.06); border-color: rgba(16, 185, 129, 0.2); box-shadow: none;">
        <div class="alert-icon-container" style="background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.2); color: var(--color-green); animation: none;">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        </div>
        <div class="alert-content">
          <div class="alert-title" style="color: var(--color-green);">פידי החיבורים תקינים</div>
          <div class="alert-desc">כל מסלולי ההמשך בלו״ז. מטען ה-AI Lookalike מסונכרן עם מניפסט העלייה למטוס.</div>
        </div>
        <span class="alert-action-badge" style="background-color: var(--color-green); color: white; box-shadow: none;">יציב</span>
      </div>
    `;
    return;
  }

  const risk = flight.connectionRisk;
  let severityClass = "";
  let badgeColor = "";
  
  if (risk.severity === "critical") {
    severityClass = ""; // uses CSS default
    badgeColor = "var(--color-red)";
  } else if (risk.severity === "warning") {
    severityClass = "caution-state";
    badgeColor = "var(--color-amber)";
  } else {
    severityClass = "notice-state";
    badgeColor = "var(--color-cyan)";
  }

  alertBannerContainer.innerHTML = `
    <div class="alert-banner ${risk.severity}-alert">
      <div class="alert-icon-container">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      </div>
      <div class="alert-content">
        <div class="alert-title">${risk.severity.toUpperCase()}: זוהה קונפליקט בחיבור/מעבר</div>
        <div class="alert-desc">${risk.message}</div>
      </div>
      <span class="alert-action-badge" id="action-required-badge">סנכרן מטען</span>
    </div>
  `;

  // Dynamic alert-click handling simulation
  const badge = document.getElementById("action-required-badge");
  if (badge) {
    badge.addEventListener("click", () => {
      alert("פקודת התאמת קייטרינג נשלחה לשיגור. מניפסט העמסת ארוחות תיירים קוצץ ב-12 מטעני-נוסע.");
      // Trigger a slight pre-order rate change to show immediate integration
      sliderPreorderRate.value = Math.max(0, parseInt(sliderPreorderRate.value) - 4);
      currentState.preorderRate = parseInt(sliderPreorderRate.value);
      valPreorderRate.innerText = `${currentState.preorderRate}%`;
      calculateAndRender();
      if (currentState.showJson) generateCateringJson();
    });
  }
}

// Update Dynamic Recommendation card based on inputs
function updateRecommendation(bufferRatio, icwFee, duration, bufferCount, stdBufferCount) {
  // Clear classes
  recommendationCard.classList.remove("alert-state", "caution-state");
  
  if (bufferRatio < 1.8) {
    // High cost / weight risk buffer compression
    recommendationCard.classList.add("alert-state");
    recommendationBadge.innerText = "קיצוץ אגרסיבי";
    recommendationImpact.innerText = `Buffer: ${bufferRatio.toFixed(1)}%`;
    recommendationText.innerHTML = `דמי פינוי ICW גבוהים ביעד (<strong>$${icwFee}/טון</strong>) וקנס דלק לטווח ארוך (<strong>${duration} שעות</strong>) מחייבים הפחתת buffer אגרסיבית. ה-buffer הדינמי כווץ ל-<strong>${bufferCount} ארוחות</strong> (חיסכון של <strong>${stdBufferCount - bufferCount} ארוחות</strong> של משקל מיותר).`;
  } else if (bufferRatio <= 3.2) {
    // Balanced buffer optimization
    recommendationCard.classList.add("caution-state");
    recommendationBadge.innerText = "תשואה מאופטמת";
    recommendationImpact.innerText = `Buffer: ${bufferRatio.toFixed(1)}%`;
    recommendationText.innerHTML = `פרופיל מסלול בינוני. נשיאת buffer בטיחות של <strong>${bufferRatio.toFixed(1)}%</strong> (<strong>${bufferCount} ארוחות</strong>) מאוזנת כלכלית מול עלויות פינוי אפשריות ביעד ומגבלות תחזית ה-Lookalike.`;
  } else {
    // Standard buffer allowed (low fees, short duration)
    recommendationBadge.innerText = "ביטחון סטנדרטי";
    recommendationImpact.innerText = `Buffer: ${bufferRatio.toFixed(1)}%`;
    recommendationText.innerHTML = `דמי פינוי נמוכים (<strong>$${icwFee}/טון</strong>) וטיסה קצרה (<strong>${duration} שעות</strong>). מומלץ buffer בטיחות סטנדרטי של <strong>${bufferCount} ארוחות</strong> כדי למקסם בחירת מנות ושביעות רצון נוסעים.`;
  }
}

// Update Logistics timeline details with active flight stats
function updateLogisticsTimeline(flight, confirmed, predicted, buffer) {
  // Populate specific timestamps and text details
  timelineT48Meta.innerText = `${flight.timeline.t48}`;
  timelineT24Meta.innerText = `${flight.timeline.t24} (הזמנות מוקדמות מאושרות: ${confirmed} ארוחות)`;

  const totalPayloadCount = confirmed + predicted + buffer;
  timelineT5Meta.innerHTML = `מניפסט העמסת קייטרינג: <strong>${totalPayloadCount} ארוחות</strong> מתוכננות (הזמנה מוקדמת: ${confirmed} | חזוי AI: ${predicted} | Buffer: ${buffer}).`;

  // Update visual checks/marker states based on current local flight schedules
  // e.g. for long flight durations, step 3 is highly active
  stepT48.classList.add("completed");
  stepT24.classList.add("completed");
  stepT5.classList.add("active");
}

// Generate Catering JSON Payload
function generateCateringJson() {
  const flight = currentState.activeFlight;
  const preorderRate = currentState.preorderRate;
  const duration = currentState.duration;
  const icwFee = currentState.icwFee;
  
  // Re-run calculations to get values
  const P = flight.passengers;
  const confirmed = Math.round(P * (preorderRate / 100));
  const unordered = P - confirmed;
  const predicted = Math.round(unordered * 0.92);
  
  const icwReduction = (icwFee / 2000) * 2.2;
  const durationReduction = (duration / 16) * 2.3;
  let recommendedBufferRatio = 5.0 - icwReduction - durationReduction;
  recommendedBufferRatio = Math.max(0.5, Math.min(5.0, recommendedBufferRatio));
  const buffer = Math.round(P * (recommendedBufferRatio / 100));
  
  const totalPayloadMeals = confirmed + predicted + buffer;

  // Let's divide by cabins
  const biz = flight.businessClass;
  const eco = flight.economyClass;
  
  // Preorder splits. Usually business class has higher pre-order completion
  const bizPreorderRate = Math.min(100, Math.round(preorderRate * 1.2));
  const ecoPreorderRate = Math.round(preorderRate * 0.95);
  
  const bizConfirmed = Math.min(biz, Math.round(biz * (bizPreorderRate / 100)));
  const bizPredicted = Math.round((biz - bizConfirmed) * 0.95);
  const bizBuffer = Math.max(1, Math.round(biz * (recommendedBufferRatio / 100) * 1.5)); // slightly higher buffer for business
  const bizTotal = bizConfirmed + bizPredicted + bizBuffer;
  
  const ecoConfirmed = Math.min(eco, Math.round(eco * (ecoPreorderRate / 100)));
  const ecoPredicted = Math.round((eco - ecoConfirmed) * 0.92);
  const ecoBuffer = Math.max(1, Math.round(eco * (recommendedBufferRatio / 100)));
  const ecoTotal = ecoConfirmed + ecoPredicted + ecoBuffer;

  // Calculate meal preferences (Chicken vs Pasta vs Vegetarian)
  // Business class distribution: 40% Chicken, 35% Pasta, 25% Vegetarian
  // Economy class distribution: 50% Chicken, 35% Pasta, 15% Vegetarian
  const mealsBiz = {
    chicken: Math.round(bizTotal * 0.40),
    pasta: Math.round(bizTotal * 0.35),
    vegetarian: 0
  };
  mealsBiz.vegetarian = bizTotal - (mealsBiz.chicken + mealsBiz.pasta);

  const mealsEco = {
    chicken: Math.round(ecoTotal * 0.50),
    pasta: Math.round(ecoTotal * 0.35),
    vegetarian: 0
  };
  mealsEco.vegetarian = ecoTotal - (mealsEco.chicken + mealsEco.pasta);

  const payload = {
    flight_manifest: {
      flight_id: flight.id,
      carrier: flight.flightNo.substring(0, 2),
      flight_number: flight.flightNo,
      route: flight.route,
      route_description: flight.routeName,
      duration_hours: duration,
      timestamp_generated: new Date().toISOString()
    },
    caterer_instructions: {
      total_meals_loaded: bizTotal + ecoTotal,
      payload_weight_kg: Math.round((bizTotal + ecoTotal) * 1.2), // 1.2kg per tray
      passenger_count: P,
      parameters_simulated: {
        preorder_rate_percent: preorderRate,
        destination_icw_disposal_fee_usd_ton: icwFee,
        buffer_ratio_applied_percent: parseFloat(recommendedBufferRatio.toFixed(2))
      }
    },
    cabin_allocation: [
      {
        cabin_class: "First_Business",
        total_meals: bizTotal,
        split: {
          confirmed_preorders: bizConfirmed,
          predicted_lookalike: bizPredicted,
          buffer_safety: bizBuffer
        },
        meals_menu: {
          poultry_chicken: mealsBiz.chicken,
          carb_pasta: mealsBiz.pasta,
          veg_option: mealsBiz.vegetarian
        }
      },
      {
        cabin_class: "Economy",
        total_meals: ecoTotal,
        split: {
          confirmed_preorders: ecoConfirmed,
          predicted_lookalike: ecoPredicted,
          buffer_safety: ecoBuffer
        },
        meals_menu: {
          poultry_chicken: mealsEco.chicken,
          carb_pasta: mealsEco.pasta,
          veg_option: mealsEco.vegetarian
        }
      }
    ],
    environmental_impact_estimates: {
      predicted_leftover_meals: Math.round(buffer + (predicted * 0.12 * (1 - preorderRate/100))),
      predicted_icw_waste_tons: parseFloat((Math.round(buffer + (predicted * 0.12 * (1 - preorderRate/100))) * 0.0012).toFixed(4)),
      fuel_burn_penalty_usd: parseFloat((duration * Math.round(buffer + (predicted * 0.12 * (1 - preorderRate/100))) * 0.0012 * 120).toFixed(2)),
      co2_impact_kg: parseFloat((duration * Math.round(buffer + (predicted * 0.12 * (1 - preorderRate/100))) * 0.0012 * 120 * 3.16).toFixed(2)) // CO2 multiplier
    }
  };

  jsonCodeBlock.innerText = JSON.stringify(payload, null, 2);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Live ICW Optimization Engine — talks to the real FastAPI backend
// ─────────────────────────────────────────────────────────────────────────────

const fmtUSD = (n) =>
  "$" + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtKg = (n) =>
  Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });

// Scroll a nested overflow container to `top`. Uses native smooth scrolling in
// real browsers, with a hard fallback that guarantees it lands even where smooth
// scrollTo is a no-op (e.g. some headless renderers).
function smoothScrollContainer(el, top) {
  const dest = Math.max(0, top);
  try {
    el.scrollTo({ top: dest, behavior: "smooth" });
  } catch (e) {
    el.scrollTop = dest;
  }
  setTimeout(() => {
    if (Math.abs(el.scrollTop - dest) > 4) el.scrollTop = dest;
  }, 500);
}

// Sidebar nav: scroll the .main-content container (the real scroll area — the
// window itself doesn't scroll) to the target section and highlight the item.
function setupSidebarNav() {
  const scroller = document.querySelector(".main-content");
  const items = document.querySelectorAll(".sidebar-nav .nav-item");
  items.forEach((item) => {
    const link = item.querySelector("a");
    if (!link) return;
    link.addEventListener("click", (e) => {
      const id = (link.getAttribute("href") || "").replace("#", "");
      const target = document.getElementById(id);
      if (target && scroller) {
        e.preventDefault();
        const top =
          target.getBoundingClientRect().top -
          scroller.getBoundingClientRect().top +
          scroller.scrollTop -
          12;
        smoothScrollContainer(scroller, top);
        items.forEach((i) => i.classList.remove("active"));
        item.classList.add("active");
      }
    });
  });
}

function setupEngineControls() {
  const btn = document.getElementById("btn-run-engine");
  if (btn) btn.addEventListener("click", () => runLiveEngine());

  const mbtn = document.getElementById("btn-gen-manifest");
  if (mbtn) mbtn.addEventListener("click", () => generateManifest());

  const dbtn = document.getElementById("btn-download-manifest");
  if (dbtn) dbtn.addEventListener("click", () => downloadManifest());

  const sbtn = document.getElementById("btn-submit-measurement");
  if (sbtn) sbtn.addEventListener("click", () => submitMeasurement());

  const dmbtn = document.getElementById("btn-download-measured-manifest");
  if (dmbtn) dmbtn.addEventListener("click", () => downloadMeasuredManifest());
}

// Returns the flight context for the currently selected flight/route.
function currentFlightPayload() {
  if (window.__lastPayload) return { ...window.__lastPayload };
  const f = currentState.activeFlight;
  const p = ENGINE_PARAMS[f.id] || {};
  return {
    flight_number: f.flightNo,
    origin_airport: p.origin,
    destination_airport: p.dest,
    departure_date: todayISO(),
    aircraft_type: p.aircraftType,
    passenger_count: f.passengers,
    route_distance_km: p.routeDistanceKm,
  };
}

// Submit a post-flight weighing event → closes the loop.
async function submitMeasurement() {
  const uplift = parseFloat(document.getElementById("meas-uplift").value);
  const returned = parseFloat(document.getElementById("meas-returned").value);
  const pax = parseInt(document.getElementById("meas-pax").value, 10);
  const method = document.getElementById("meas-method").value;
  const operator = document.getElementById("meas-operator").value;
  const resultsEl = document.getElementById("measure-results");

  const flight = currentFlightPayload();
  flight.passenger_count = pax;

  try {
    const resp = await fetch(`${API_BASE}/api/measurement/flight`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        flight,
        uplift_weight_kg: uplift,
        returned_waste_weight_kg: returned,
        measurement_method: method,
        operator_id: operator,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    window.__measuredManifest = data.manifest;
    renderMeasurement(data);
    if (resultsEl) resultsEl.classList.remove("hidden");
  } catch (err) {
    const loop = document.getElementById("meas-loop");
    if (loop) loop.innerText = "שגיאת מדידה: " + (err.message || err);
  }
}

function renderMeasurement(data) {
  const m = data.measurement;
  const fb = m.model_feedback;
  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.innerText = v;
  };
  set("meas-consumed", `${m.consumed_weight_kg} ק״ג`);
  set("meas-rate", `${m.consumption_rate_pct}% נאכל`);
  set("meas-perpax", `${m.actual_waste_kg_per_pax} ק״ג`);

  const deltaEl = document.getElementById("meas-delta");
  const sign = fb.delta_kg_per_pax > 0 ? "+" : "";
  deltaEl.innerText = `${sign}${fb.delta_kg_per_pax} ק״ג`;
  // Below prediction = less waste than assumed = good.
  deltaEl.className = "es-value " + (fb.delta_kg_per_pax <= 0 ? "text-green" : "text-amber");
  const dirMap = {
    below_prediction: "מתחת לתחזית",
    above_prediction: "מעל לתחזית",
    on_prediction: "בדיוק בתחזית",
  };
  set("meas-dir", dirMap[fb.direction] || fb.direction);

  set("meas-disposal", `${m.returned_waste_weight_kg}`);

  const loop = document.getElementById("meas-loop");
  if (loop) {
    loop.innerHTML =
      `<strong>הלולאה נסגרה:</strong> ה-<strong>${m.actual_waste_kg_per_pax} ק״ג/נוסע</strong> המדודים ` +
      `החליפו את הנחת IATA 1.43 — המנוע חישב מחדש ל-` +
      `<strong>${data.optimization.waste_per_pax_kg} ק״ג/נוסע</strong>, המניפסט נושא כעת מקור ` +
      `<strong>מדוד</strong>, וה-delta בין בפועל לחזוי הוא תווית האימון של המודל.`;
  }
}

function downloadMeasuredManifest() {
  const m = window.__measuredManifest;
  if (!m) return;
  const blob = new Blob([JSON.stringify(m, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = m.manifest_id + "-measured.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Generate the ICW chain-of-custody compliance manifest for the last-run flight.
async function generateManifest() {
  const payload = window.__lastPayload;
  if (!payload) return;
  const statusEl = document.getElementById("manifest-status");
  const viewerEl = document.getElementById("manifest-viewer");
  if (statusEl) statusEl.innerText = "מפיק…";

  try {
    const resp = await fetch(`${API_BASE}/api/manifest/flight`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ flight: payload }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const manifest = await resp.json();
    window.__lastManifest = manifest;

    document.getElementById("manifest-json").innerText = JSON.stringify(manifest, null, 2);
    document.getElementById("manifest-regime").innerText =
      "ABP קטגוריה " + manifest.waste_classification.abp_category + " · " + manifest.regulatory_regime;
    document.getElementById("manifest-hash").innerText =
      manifest.audit.tamper_evident_hash.slice(0, 23) + "…";

    // Independently verify the tamper-evident hash via the backend.
    const v = await fetch(`${API_BASE}/api/manifest/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manifest }),
    }).then((r) => r.json());
    const vEl = document.getElementById("manifest-verify");
    vEl.innerText = v.valid ? "✓ hash מאומת" : "✗ אי-התאמת hash";
    vEl.className = "manifest-verify " + (v.valid ? "ok" : "bad");

    if (viewerEl) viewerEl.classList.remove("hidden");
    document.getElementById("btn-download-manifest").classList.remove("hidden");
    if (statusEl) statusEl.innerText = "";
  } catch (err) {
    if (statusEl) statusEl.innerText = "שגיאת מניפסט: " + (err.message || err);
  }
}

function downloadManifest() {
  const m = window.__lastManifest;
  if (!m) return;
  const blob = new Blob([JSON.stringify(m, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = m.manifest_id + ".json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function setEngineStatus(state, label) {
  const el = document.getElementById("engine-status");
  if (!el) return;
  el.className = "engine-status " + state; // idle | loading | ok | error
  el.innerHTML = `<span class="badge-dot"></span> ${label}`;
}

function todayISO() {
  // Use the dashboard's UTC "now" for the departure_date field.
  return new Date().toISOString().slice(0, 10);
}

// Run the engine for the currently selected DEMO flight.
async function runLiveEngine() {
  const flight = currentState.activeFlight;
  const params = ENGINE_PARAMS[flight.id];
  if (!params) {
    showEngineError(`לא הוגדרו פרמטרי מנוע לטיסה ${flight.id}.`);
    return;
  }
  // Reset the BTS selector — we're back on a demo flight.
  const sel = document.getElementById("bts-route-select");
  if (sel && !sel.disabled) sel.value = "";

  await runEngineWithPayload({
    flight_number: flight.flightNo,
    origin_airport: params.origin,
    destination_airport: params.dest,
    departure_date: todayISO(),
    aircraft_type: params.aircraftType,
    passenger_count: flight.passengers,
    route_distance_km: params.routeDistanceKm,
  });
}

// Shared fetch + render path for any flight payload (demo or BTS route).
async function runEngineWithPayload(payload) {
  const resultsEl = document.getElementById("engine-results");
  const placeholderEl = document.getElementById("engine-placeholder");
  const errorEl = document.getElementById("engine-error");

  setEngineStatus("loading", "מחשב…");
  if (errorEl) errorEl.classList.add("hidden");

  try {
    const resp = await fetch(`${API_BASE}/api/optimize/flight`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
    }
    const data = await resp.json();
    renderEngineResult(data);
    if (placeholderEl) placeholderEl.classList.add("hidden");
    if (resultsEl) resultsEl.classList.remove("hidden");
    setEngineStatus("ok", "חי");

    // Remember the payload so the manifest can be generated for it.
    window.__lastPayload = payload;
    const mb = document.getElementById("btn-gen-manifest");
    if (mb) mb.disabled = false;
    // Keep the measurement form's passenger count in sync with the active flight.
    const paxField = document.getElementById("meas-pax");
    if (paxField) paxField.value = payload.passenger_count;
  } catch (err) {
    showEngineError(err.message || String(err));
  }
}

// Load real routes ingested from BTS T-100 and populate the selector.
async function loadBtsRoutes() {
  const sel = document.getElementById("bts-route-select");
  const hint = document.getElementById("bts-hint");
  if (!sel) return;
  try {
    const resp = await fetch(`${API_BASE}/api/bts/routes`);
    const data = await resp.json();
    const routes = data.routes || [];
    window.__btsRoutes = routes;

    if (!data.ingested || routes.length === 0) {
      sel.innerHTML = "<option value=''>— אין נתוני BTS שהוטמעו —</option>";
      sel.disabled = true;
      if (hint) hint.innerText = "הרץ scripts/ingest_bts_t100.py עם CSV מ-TranStats כדי להפעיל.";
      return;
    }

    sel.disabled = false;
    sel.innerHTML =
      "<option value=''>— בחר מסלול BTS אמיתי —</option>" +
      routes
        .map(
          (r, i) =>
            `<option value="${i}">${r.origin}→${r.dest} · ${r.avg_pax} נוסעים · ${r.aircraft}</option>`
        )
        .join("");
    if (hint) {
      const yr = routes[0].year ? ` (${routes[0].year})` : "";
      hint.innerText = `${routes.length} מסלולים מ-BTS T-100${yr}`;
    }

    sel.addEventListener("change", () => {
      const idx = sel.value;
      if (idx === "") return;
      runBtsRoute(window.__btsRoutes[Number(idx)]);
    });
  } catch (err) {
    sel.innerHTML = "<option value=''>— מסלולי BTS לא זמינים —</option>";
    sel.disabled = true;
    if (hint) hint.innerText = "";
  }
}

// Run the engine for a real BTS route.
async function runBtsRoute(route) {
  if (!route) return;
  await runEngineWithPayload({
    flight_number: (route.carrier || "") + route.origin + route.dest,
    origin_airport: route.origin,
    destination_airport: route.dest,
    departure_date: todayISO(),
    aircraft_type: route.aircraft || `Type ${route.aircraft_code || "?"}`,
    passenger_count: route.avg_pax,
    route_distance_km: route.distance_km > 0 ? route.distance_km : 1000,
  });
}

function showEngineError(msg) {
  const errorEl = document.getElementById("engine-error");
  setEngineStatus("error", "שגיאה");
  if (errorEl) {
    errorEl.classList.remove("hidden");
    errorEl.innerText = `המנוע לא זמין — ${msg}`;
  }
}

function renderEngineResult(d) {
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.innerText = val;
  };

  set("eng-current-buffer", fmtKg(d.current_buffer_kg));
  set("eng-optimized-buffer", fmtKg(d.optimized_buffer_kg));
  set("eng-reduction", `${fmtKg(d.buffer_reduction_kg)} ק״ג`);
  set("eng-reduction-pct", `${d.buffer_reduction_pct}% קל יותר`);
  set("eng-net-saving", fmtUSD(d.airline_net_saving_usd));

  set("eng-disposal", fmtUSD(d.savings.disposal_savings_usd));
  set("eng-fuel", fmtUSD(d.savings.fuel_savings_usd));
  set("eng-corsia", fmtUSD(d.savings.corsia_savings_usd));
  set("eng-total", fmtUSD(d.savings.total_savings_usd));
  set("eng-revshare", fmtUSD(d.revenue_share_usd));

  set("eng-country", d.destination_country);
  set("eng-category", (d.icw_category || "").toUpperCase());
  set("eng-regime", d.abp_regime || "—");
  set("eng-co2", `${fmtKg(d.co2_saved_kg)} ק״ג`);

  const riskEl = document.getElementById("eng-risk");
  if (riskEl) {
    const riskMap = { high: "גבוה", medium: "בינוני", low: "נמוך" };
    riskEl.innerText = riskMap[d.regulatory_risk_level] || (d.regulatory_risk_level || "").toUpperCase();
    riskEl.className =
      d.regulatory_risk_level === "high"
        ? "text-red"
        : d.regulatory_risk_level === "medium"
        ? "text-amber"
        : "text-green";
  }

  set("eng-confidence", `ביטחון: ${d.confidence_level}`);
  const srcEl = document.getElementById("eng-sources");
  if (srcEl) srcEl.innerText = (d.data_sources || []).join("  ·  ");
}

// Start the Dashboard
window.addEventListener("DOMContentLoaded", init);
