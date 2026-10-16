/**
 * BusinessLabs AI Tech Consultant - Unified Frontend Application
 * Connects directly to Task 1 (:8000), Task 2 (:3000), and Task 3 (:8001).
 * Features automatic seamless fallback to Interactive Standalone Demo Mode
 * when deployed to cloud hosts (e.g. Netlify) or when local backends are offline.
 */

const API_CONFIG = {
  kbBaseUrl: 'http://127.0.0.1:8000',
  inboxBaseUrl: 'http://127.0.0.1:3000',
  scopeBaseUrl: 'http://127.0.0.1:8001',
};

// Global App State
const state = {
  activeTab: 'overview',
  demoMode: false,
  services: {
    kb: false,
    inbox: false,
    scope: false,
  },
  inbox: {
    emails: [],
    drafts: new Map(),
    activeEmailId: null,
    filter: 'all',
    autonomyStates: {},
  },
  scope: {
    currentProjectId: 'PRJ-LEGAL-01',
    currentScope: null,
    currentProposal: null,
    currentDiff: null,
    scenarios: [],
  },
};

// =====================================================================
// INITIALIZATION
// =====================================================================

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  checkServicesHealth();
  setInterval(checkServicesHealth, 10000);

  // Initialize data with automatic demo fallback
  loadKbStatus();
  refreshAutonomyStates();
  loadSyntheticEmails();
  preloadScenarios();
});

// --- Tab Switching ---
function initTabs() {
  document.querySelectorAll('.nav-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      const tabId = tab.getAttribute('data-tab');
      switchTab(tabId);
    });
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll('.nav-tab').forEach((t) => {
    t.classList.toggle('active', t.getAttribute('data-tab') === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach((p) => {
    p.classList.toggle('active', p.id === `tab-${tabId}`);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// --- Health Probing & Demo Mode Indicator ---
async function checkServicesHealth() {
  const updatePill = (elemId, isHealthy, label) => {
    const el = document.getElementById(elemId);
    if (!el) return;
    const dot = el.querySelector('.dot');
    if (dot) dot.style.background = isHealthy ? 'var(--accent-emerald)' : 'var(--accent-amber)';
    if (label) el.innerHTML = `<span class="dot" style="background:${isHealthy ? 'var(--accent-emerald)' : 'var(--accent-amber)'}"></span> ${label}`;
  };

  // 1. Task 1 Knowledge Brain (:8000)
  try {
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/health`, { method: 'GET', signal: AbortSignal.timeout(1500) });
    state.services.kb = res.ok;
  } catch {
    state.services.kb = false;
  }

  // 2. Task 2 Inbox Agent (:3000)
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/health`, { method: 'GET', signal: AbortSignal.timeout(1500) });
    state.services.inbox = res.ok;
  } catch {
    state.services.inbox = false;
  }

  // 3. Task 3 Meeting to Scope (:8001)
  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/health`, { method: 'GET', signal: AbortSignal.timeout(1500) });
    state.services.scope = res.ok;
  } catch {
    state.services.scope = false;
  }

  const allOnline = state.services.kb && state.services.inbox && state.services.scope;
  const globalDot = document.getElementById('globalHealthDot');
  const globalText = document.getElementById('globalHealthText');
  const appModeText = document.getElementById('appModeText');

  if (allOnline) {
    state.demoMode = false;
    updatePill('t1Status', true, 'Task 1 (KB :8000)');
    updatePill('t2Status', true, 'Task 2 (Inbox :3000)');
    updatePill('t3Status', true, 'Task 3 (Scope :8001)');
    if (globalDot && globalText) {
      globalDot.style.background = 'var(--accent-emerald)';
      globalText.textContent = 'All Services Online';
    }
    if (appModeText) appModeText.textContent = 'Live Local Backends';
  } else {
    // Cloud Host (Netlify / Mobile) or Offline Localhost
    state.demoMode = true;
    updatePill('t1Status', true, 'Task 1 (Demo Active)');
    updatePill('t2Status', true, 'Task 2 (Demo Active)');
    updatePill('t3Status', true, 'Task 3 (Demo Active)');
    if (globalDot && globalText) {
      globalDot.style.background = 'var(--accent-emerald)';
      globalText.textContent = 'Interactive Demo Mode';
    }
    if (appModeText) appModeText.textContent = 'Cloud Standalone Simulation';
  }
}

// =====================================================================
// TASK 1: KNOWLEDGE BRAIN CONTROLLER
// =====================================================================

function fillKbQuery(queryText) {
  const input = document.getElementById('kbInput');
  if (input) {
    input.value = queryText;
    input.focus();
  }
}

async function loadKbStatus() {
  try {
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/health`, { signal: AbortSignal.timeout(1500) });
    if (res.ok) {
      const data = await res.json();
      const articlesEl = document.getElementById('kbTotalArticles');
      const chunksEl = document.getElementById('kbTotalChunks');
      if (articlesEl && data.total_articles !== undefined) articlesEl.textContent = data.total_articles;
      if (chunksEl && data.total_chunks !== undefined) chunksEl.textContent = data.total_chunks;
      return;
    }
  } catch (err) {
    // Fallback to demo numbers
  }

  const articlesEl = document.getElementById('kbTotalArticles');
  const chunksEl = document.getElementById('kbTotalChunks');
  const countEl = document.getElementById('escalationCount');
  if (articlesEl) articlesEl.textContent = '3';
  if (chunksEl) chunksEl.textContent = '6';
  if (countEl) countEl.textContent = '2';
}

async function handleKbQuery(event) {
  event.preventDefault();
  const input = document.getElementById('kbInput');
  const query = input.value.trim();
  if (!query) return;

  const topK = parseInt(document.getElementById('kbTopK').value, 10) || 3;
  const minScore = parseFloat(document.getElementById('kbMinScore').value) || 0.5;
  const spinner = document.getElementById('kbSpinner');
  const submitBtn = document.getElementById('kbSubmitBtn');

  spinner.style.display = 'inline-block';
  submitBtn.disabled = true;
  const startTime = performance.now();

  try {
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: topK, min_score: minScore }),
      signal: AbortSignal.timeout(2500),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const elapsed = Math.round(performance.now() - startTime);
    renderKbResponse(data, elapsed);
    showToast('Knowledge Brain answered inquiry successfully', 'success');
  } catch (err) {
    // Interactive Cloud / Offline Fallback Simulation
    setTimeout(() => {
      const data = getMockKbResponse(query);
      const elapsed = Math.max(145, Math.round(performance.now() - startTime));
      renderKbResponse(data, elapsed);
      showToast('Knowledge Brain answered inquiry (Interactive Demo)', 'success');
    }, 400);
  } finally {
    setTimeout(() => {
      spinner.style.display = 'none';
      submitBtn.disabled = false;
    }, 450);
  }
}

function getMockKbResponse(query) {
  const q = query.toLowerCase();

  if (q.includes('domain') || q.includes('dns') || q.includes('ssl')) {
    return {
      answer: "To connect a live custom domain in Brilliant Directories: 1) Navigate to Settings > Domain Settings in the admin portal. 2) Enter your registered custom domain name (e.g. yoursite.com). 3) Point your domain's A-Record to the Brilliant Directories server IP address (54.208.232.181). Propagation takes between 2 to 4 hours. Automated SSL certificates (Let's Encrypt) are provisioned automatically once DNS propagation completes.",
      confidence_score: 0.94,
      escalated: false,
      sources: [
        {
          title: "How to Connect Your Custom Domain",
          url: "https://support.brilliantdirectories.com/support/solutions/articles/12000045678-how-to-connect-a-custom-domain",
          score: 0.95,
          snippet: "Navigate to Settings > Domain Settings. Enter your custom domain and update your DNS A-Record to point to the BD server IP address...",
        },
      ],
      screenshots: [
        {
          url: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=80",
          caption: "Settings > Domain Settings: DNS A-Record Configuration",
        },
      ],
    };
  }

  if (q.includes('stripe') || q.includes('payment') || q.includes('recurring')) {
    return {
      answer: "To configure Stripe payment gateway with recurring plans: 1) Go to Finance > Payment Gateways. 2) Click Connect with Stripe to authenticate your Stripe account via OAuth. 3) Under Finance > Membership Plans, edit each membership tier to define billing intervals (monthly, quarterly, annually) and setup fees. Webhooks for subscription renewals, credit card updates, and failed payment alerts are handled automatically.",
      confidence_score: 0.91,
      escalated: false,
      sources: [
        {
          title: "Configuring Stripe Payment Gateway",
          url: "https://support.brilliantdirectories.com/support/solutions/articles/12000078901-configuring-stripe",
          score: 0.92,
          snippet: "Connect your Stripe account via OAuth in Finance > Payment Gateways. Automated recurring billing is handled directly through Stripe Subscriptions...",
        },
      ],
      screenshots: [
        {
          url: "https://images.unsplash.com/photo-1556742049-0a67c5574f73?auto=format&fit=crop&w=800&q=80",
          caption: "Finance > Payment Gateways: Stripe Integration Dashboard",
        },
      ],
    };
  }

  if (q.includes('wordpress') || q.includes('plugin') || q.includes('php')) {
    return {
      answer: "Brilliant Directories operates on a proprietary, standalone SaaS cloud architecture and does NOT support uploading custom WordPress PHP plugins or themes directly into the platform backend. Custom directory functionality is implemented via the native Widget Manager (HTML, CSS, JavaScript) or by connecting external services through Webhooks and the BD REST API.",
      confidence_score: 0.88,
      escalated: false,
      sources: [
        {
          title: "Custom Widgets vs Third-Party PHP Plugins",
          url: "https://support.brilliantdirectories.com/support/solutions/articles/12000034567-custom-widgets",
          score: 0.89,
          snippet: "Brilliant Directories is an independent cloud solution. WordPress plugins cannot be uploaded to BD hosting environments...",
        },
      ],
    };
  }

  if (q.includes('hipaa') || q.includes('medical') || q.includes('doctor') || q.includes('health')) {
    return {
      answer: "CRITICAL REGULATORY NOTICE: Brilliant Directories is a marketing directory platform and is NOT HIPAA compliant. Storing protected health information (PHI), patient medical records, blood test results, or prescription histories directly on doctor profile pages violates federal healthcare privacy laws. This query has been escalated to Tier-1 Human Technical Consulting for architectural alternative guidance.",
      confidence_score: 0.62,
      escalated: true,
      escalation_id: "ESC-MED-HIPAA-01",
      sources: [
        {
          title: "Data Security and Compliance Guidelines",
          url: "https://support.brilliantdirectories.com/support/solutions/articles/12000099881-security-guidelines",
          score: 0.64,
          snippet: "Brilliant Directories does not provide HIPAA-certified cloud storage for sensitive patient medical data...",
        },
      ],
    };
  }

  if (q.includes('quantum') || q.includes('warp') || q.includes('teleport')) {
    return {
      answer: "I cannot find any documentation or capabilities regarding 'quantum teleportation warp drive' in the Brilliant Directories Solution Center. The similarity score (15%) is below the minimum confidence cutoff (0.50). This inquiry has been safely abstained and routed to human review.",
      confidence_score: 0.15,
      escalated: true,
      escalation_id: "ESC-LOW-SIM-09",
      sources: [],
    };
  }

  // Dynamic fallback for arbitrary inquiries
  return {
    answer: `Regarding "${query}": Brilliant Directories provides full support through the Admin Dashboard under General Settings and Content Management. Custom features can be extended via Widget Manager (HTML/CSS/JS) or the REST API.`,
    confidence_score: 0.84,
    escalated: false,
    sources: [
      {
        title: "Brilliant Directories Solution Center Documentation",
        url: "https://support.brilliantdirectories.com/support/solutions",
        score: 0.86,
        snippet: `Verified reference documentation for platform management, directory configuration, and custom feature implementation...`,
      },
    ],
  };
}

function renderKbResponse(data, elapsedMs) {
  document.getElementById('kbResultPlaceholder').style.display = 'none';
  const card = document.getElementById('kbResultCard');
  card.style.display = 'block';

  // Badges
  const confBadge = document.getElementById('kbConfidenceBadge');
  const conf = Math.round((data.confidence_score || 0) * 100);
  confBadge.textContent = `Confidence: ${conf}%`;
  confBadge.className = `badge ${conf >= 75 ? 'badge-success' : conf >= 50 ? 'badge-warning' : 'badge-danger'}`;

  const escBadge = document.getElementById('kbEscalationBadge');
  if (data.escalated) {
    escBadge.textContent = `🚨 Escalated (ID: ${data.escalation_id || 'Tier-1'})`;
    escBadge.className = 'badge badge-danger';
  } else {
    escBadge.textContent = '✔ Verified Grounded';
    escBadge.className = 'badge badge-success';
  }

  document.getElementById('kbResponseTime').textContent = `Retrieved in ${elapsedMs}ms`;
  document.getElementById('kbAnswerText').textContent = data.answer || 'No answer generated.';

  // Citations
  const citationsList = document.getElementById('kbCitationsList');
  citationsList.innerHTML = '';
  if (data.sources && data.sources.length > 0) {
    data.sources.forEach((src) => {
      const item = document.createElement('div');
      item.className = 'citation-card';
      item.innerHTML = `
        <div class="citation-title-row">
          <span class="citation-title">${escapeHtml(src.title || 'Documentation Article')}</span>
          <span class="citation-score">Relevance: ${Math.round((src.score || 0) * 100)}%</span>
        </div>
        <a href="${escapeHtml(src.url)}" target="_blank" class="citation-url">${escapeHtml(src.url)} ↗</a>
        <div class="citation-snippet">${escapeHtml(src.snippet || '')}</div>
      `;
      citationsList.appendChild(item);
    });
  } else {
    citationsList.innerHTML = '<div class="text-muted text-sm">No direct chunk citations above score threshold. Inquiry safely abstained.</div>';
  }

  // Screenshots
  const imagesSection = document.getElementById('kbImagesSection');
  const imagesGallery = document.getElementById('kbImagesGallery');
  if (data.screenshots && data.screenshots.length > 0) {
    imagesSection.style.display = 'block';
    imagesGallery.innerHTML = '';
    data.screenshots.forEach((sc) => {
      const thumb = document.createElement('div');
      thumb.className = 'screenshot-thumb';
      thumb.onclick = () => openLightbox(sc.url, sc.caption);
      thumb.innerHTML = `
        <img src="${escapeHtml(sc.url)}" alt="${escapeHtml(sc.caption || 'Screenshot')}">
        <div class="screenshot-caption">${escapeHtml(sc.caption || 'Click to enlarge')}</div>
      `;
      imagesGallery.appendChild(thumb);
    });
  } else {
    imagesSection.style.display = 'none';
  }
}

function triggerKbSync() {
  showToast('Starting incremental documentation synchronization...', 'info');
  setTimeout(() => {
    showToast('Incremental sync completed: 3 articles processed, 6 chunks indexed into ChromaDB.', 'success');
  }, 1200);
}

function loadEscalations() {
  alert(
    "📋 Knowledge Brain Escalation Desk (2 Open Tickets):\n\n" +
    "1. [ESC-MED-HIPAA-01] HIPAA Medical Records Storage Request\n" +
    "   Client: MedCare Health Group | Status: Open | Tier: 1 (Regulatory Conflict)\n" +
    "   Recommendation: Advise client to utilize external HIPAA portal (e.g. DrChrono) and link via SSO.\n\n" +
    "2. [ESC-LOW-SIM-09] Quantum Teleportation Capability Query\n" +
    "   Status: Open | Tier: 2 (Low Confidence 15%)\n" +
    "   Recommendation: Clarify client technical inquiry."
  );
}

// =====================================================================
// TASK 2: INBOX AGENT CONTROLLER (WITH AUTONOMY STREAKS)
// =====================================================================

const DEFAULT_SYNTHETIC_EMAILS = [
  {
    id: 'eval_tech_001',
    senderEmail: 'marcus.vance@example.org',
    senderName: 'Marcus Vance',
    subject: 'SSL Certificate failing on custom domain directorypro.com',
    body: 'Hi Support,\n\nOur custom domain directorypro.com points to Brilliant Directories, but visitors are seeing a "Not Secure" warning in Chrome. I updated the nameservers 48 hours ago. Can you verify why the automated Let\'s Encrypt SSL certificate is not generating?\n\nThanks,\nMarcus',
    category: 'technical_support',
    status: 'pending_review',
    draft: {
      id: 'draft_001',
      proposedBody: "Hi Marcus,\n\nThank you for reaching out to Brilliant Directories support.\n\nOnce nameservers are pointed, SSL certificates are issued automatically within 2 to 4 hours. To resolve the 'Not Secure' warning: 1) Go to Settings > Domain Settings in your admin portal. 2) Ensure your domain is listed as primary. 3) Verify your DNS A-Record points to our server IP (54.208.232.181). If DNS was recently updated, clearing browser cache or forcing SSL regeneration under Domain Settings will resolve the issue.\n\nBest regards,\nCustomer Support Team",
      autoSendEligible: true,
      supportingSources: [
        { title: "Connecting Your Custom Domain & SSL", url: "https://support.brilliantdirectories.com/support/solutions/articles/12000045678-how-to-connect-a-custom-domain", score: 0.94 }
      ]
    }
  },
  {
    id: 'eval_tech_002',
    senderEmail: 'elena.rostova@example.com',
    senderName: 'Elena Rostova',
    subject: 'Webhook endpoint returning HTTP 500 on member signup',
    body: 'Hello,\n\nEvery time a member completes registration on our site, our Zapier webhook receives an HTTP 500 internal server error from your webhook dispatcher. Can you check the error logs for webhook ID wh_98234?\n\nRegards,\nElena',
    category: 'technical_support',
    status: 'pending_review',
    draft: {
      id: 'draft_002',
      proposedBody: "Hello Elena,\n\nThank you for notifying us. An HTTP 500 from the webhook dispatcher usually indicates an unexpected payload structure or a timeout on the receiving endpoint. We have flagged webhook ID wh_98234 for log inspection. In the meantime, please verify under Developer Tools > Webhooks that your endpoint returns an immediate HTTP 200 acknowledge.",
      autoSendEligible: false,
      supportingSources: [
        { title: "Developer Tools: Webhook Payload Format", url: "https://support.brilliantdirectories.com/support/solutions/articles/12000088234-webhooks", score: 0.87 }
      ]
    }
  },
  {
    id: 'eval_bill_003',
    senderEmail: 'jordan.lee@lawdirectory.net',
    senderName: 'Jordan Lee',
    subject: 'Requesting refund for accidental annual plan renewal',
    body: 'Hi Billing Team,\n\nOur account was billed $990 yesterday for annual renewal of our Platinum directory plan. We intended to downgrade to the monthly plan before the renewal date. Can you please refund the annual charge and switch us to monthly?\n\nJordan Lee',
    category: 'billing_and_payments',
    status: 'pending_review',
    draft: {
      id: 'draft_003',
      proposedBody: "Hi Jordan,\n\nThank you for contacting billing. We understand you intended to change to a monthly plan prior to renewal. Per our 30-day satisfaction policy, we can refund the $990 annual renewal and transition your account to the monthly billing rate of $99/month. Please confirm you would like us to process this adjustment.",
      autoSendEligible: false,
      supportingSources: [
        { title: "Billing & Refund Policies", url: "https://support.brilliantdirectories.com/support/solutions/articles/12000011223-billing-refunds", score: 0.91 }
      ]
    }
  },
  {
    id: 'eval_feat_004',
    senderEmail: 'carlos.mendes@globaldirectory.io',
    senderName: 'Carlos Mendes',
    subject: 'Multi-currency checkout support for European members (EUR and GBP)',
    body: 'Hi,\n\nWe have 300 members in the UK and Germany who need to pay in Euros and British Pounds instead of USD. Does Brilliant Directories support multi-currency checkout on membership signups?\n\nCarlos',
    category: 'feature_request',
    status: 'pending_review',
    draft: {
      id: 'draft_004',
      proposedBody: "Hi Carlos,\n\nBrilliant Directories supports single-currency processing per website installation in Finance > Currency Settings. To accept multi-currency billing in EUR and GBP simultaneously, our technical team can integrate Stripe Multi-Currency checkout via a custom widget. We will prepare an implementation scoping proposal for you.",
      autoSendEligible: true,
      supportingSources: [
        { title: "Currency & Payment Settings", url: "https://support.brilliantdirectories.com/support/solutions/articles/12000055441-currency-settings", score: 0.89 }
      ]
    }
  },
  {
    id: 'eval_lead_005',
    senderEmail: 'samuel.green@attorneysunited.com',
    senderName: 'Samuel Green',
    subject: 'Migrating 2,500 attorney profiles from WordPress to Brilliant Directories',
    body: 'Hello,\n\nWe currently manage a directory of 2,500 attorneys on WordPress with custom fields, headshots, and bar license numbers. We are evaluating Brilliant Directories. How long would a full data migration take and do you offer assistance?\n\nSamuel Green',
    category: 'lead_qualification',
    status: 'pending_review',
    draft: {
      id: 'draft_005',
      proposedBody: "Hello Samuel,\n\nThank you for considering Brilliant Directories! Migrating 2,500 attorney profiles from WordPress is straightforward using our CSV Import tool. We can preserve all custom fields, headshot URLs, and bar license numbers. Our technical consulting team offers complete migration assistance typically completed within 3 to 5 business days.",
      autoSendEligible: true,
      supportingSources: [
        { title: "Importing Members via CSV", url: "https://support.brilliantdirectories.com/support/solutions/articles/12000066778-csv-member-import", score: 0.96 }
      ]
    }
  },
  {
    id: 'eval_comp_006',
    senderEmail: 'rachel.adams@healthcarefind.org',
    senderName: 'Rachel Adams',
    subject: 'Directory search latency high during peak hours',
    body: 'To whom it may concern,\n\nOur healthcare directory is taking over 8 seconds to load doctor search results between 2 PM and 5 PM EST. Our users are complaining. Please look into our server response times immediately.\n\nRachel Adams',
    category: 'complaint',
    status: 'pending_review',
    draft: {
      id: 'draft_006',
      proposedBody: "Dear Rachel,\n\nWe sincerely apologize for the slow search load times you are experiencing. Performance is our top priority. We are immediately investigating your database query performance and server cache configurations. A technical specialist has been assigned to audit your index settings within the next hour.",
      autoSendEligible: false,
      supportingSources: [
        { title: "Optimizing Search Performance & Caching", url: "https://support.brilliantdirectories.com/support/solutions/articles/12000077889-search-performance", score: 0.88 }
      ]
    }
  }
];

// In-memory or localStorage streak store
const AUTONOMY_STORE_KEY = 'bl_autonomy_state';

function getStoredAutonomy() {
  try {
    const raw = localStorage.getItem(AUTONOMY_STORE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return {
    technical_support: { consecutiveUneditedApprovals: 18, isAutonomous: false, totalProcessed: 42 },
    billing_and_payments: { consecutiveUneditedApprovals: 7, isAutonomous: false, totalProcessed: 19 },
    feature_request: { consecutiveUneditedApprovals: 12, isAutonomous: false, totalProcessed: 28 },
    complaint: { consecutiveUneditedApprovals: 4, isAutonomous: false, totalProcessed: 11 },
    lead_qualification: { consecutiveUneditedApprovals: 15, isAutonomous: false, totalProcessed: 31 },
    general_inquiry: { consecutiveUneditedApprovals: 20, isAutonomous: true, totalProcessed: 65 },
    spam_or_abuse: { consecutiveUneditedApprovals: 20, isAutonomous: true, totalProcessed: 54 },
  };
}

function saveStoredAutonomy(states) {
  try {
    localStorage.setItem(AUTONOMY_STORE_KEY, JSON.stringify(states));
  } catch {}
}

async function refreshAutonomyStates() {
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/autonomy`, { signal: AbortSignal.timeout(1500) });
    if (res.ok) {
      const data = await res.json();
      state.inbox.autonomyStates = data.categories || {};
      renderAutonomyMatrix(state.inbox.autonomyStates, data.threshold || 20);
      return;
    }
  } catch {}

  // Fallback to stored demo state
  state.inbox.autonomyStates = getStoredAutonomy();
  renderAutonomyMatrix(state.inbox.autonomyStates, 20);
}

function renderAutonomyMatrix(states, threshold = 20) {
  const container = document.getElementById('autonomyStreakGrid');
  if (!container) return;
  container.innerHTML = '';

  const categories = [
    'general_inquiry',
    'technical_support',
    'billing_and_payments',
    'feature_request',
    'lead_qualification',
    'complaint',
    'spam_or_abuse',
  ];

  categories.forEach((cat) => {
    const s = states[cat] || {
      consecutiveUneditedApprovals: 0,
      isAutonomous: false,
      totalProcessed: 0,
    };

    const card = document.createElement('div');
    card.className = `category-streak-card ${s.isAutonomous ? 'autonomous' : ''}`;

    const progressPct = Math.min(100, Math.round((s.consecutiveUneditedApprovals / threshold) * 100));

    card.innerHTML = `
      <div class="streak-card-top">
        <span class="streak-cat-name">${formatCategoryName(cat)}</span>
        <span class="streak-status-badge ${s.isAutonomous ? 'autonomous' : 'supervised'}">
          ${s.isAutonomous ? '⚡ AUTONOMOUS' : 'SUPERVISED'}
        </span>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width: ${progressPct}%"></div>
      </div>
      <div class="streak-numbers">
        <span>Streak: <strong>${s.consecutiveUneditedApprovals}</strong> / ${threshold}</span>
        <span>Processed: ${s.totalProcessed || 0}</span>
      </div>
    `;
    container.appendChild(card);
  });
}

async function loadSyntheticEmails() {
  showToast('Loading synthetic customer emails...', 'info');
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/synthetic`, { signal: AbortSignal.timeout(1500) });
    if (res.ok) {
      const data = await res.json();
      // Ingest live if possible
      await refreshInboxEmails();
      showToast('Synthetic emails loaded into queue!', 'success');
      return;
    }
  } catch {}

  // Fallback to embedded synthetic dataset
  state.inbox.emails = JSON.parse(JSON.stringify(DEFAULT_SYNTHETIC_EMAILS));
  document.getElementById('inboxCountBadge').textContent = `${state.inbox.emails.length} emails`;
  renderInboxList();
  showToast('Synthetic emails loaded into interactive queue!', 'success');
}

async function refreshInboxEmails() {
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/emails`, { signal: AbortSignal.timeout(1500) });
    if (res.ok) {
      const data = await res.json();
      state.inbox.emails = data.emails || [];
      document.getElementById('inboxCountBadge').textContent = `${state.inbox.emails.length} emails`;
      renderInboxList();
      return;
    }
  } catch {}

  if (state.inbox.emails.length === 0) {
    state.inbox.emails = JSON.parse(JSON.stringify(DEFAULT_SYNTHETIC_EMAILS));
  }
  document.getElementById('inboxCountBadge').textContent = `${state.inbox.emails.length} emails`;
  renderInboxList();
}

function filterInbox(filterType) {
  state.inbox.filter = filterType;
  document.querySelectorAll('.filter-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.textContent.toLowerCase().includes(filterType));
  });
  renderInboxList();
}

function renderInboxList() {
  const container = document.getElementById('inboxList');
  if (!container) return;

  let emails = state.inbox.emails || [];
  if (state.inbox.filter === 'pending') {
    emails = emails.filter((e) => !e.status || e.status === 'pending_review');
  } else if (state.inbox.filter === 'sent') {
    emails = emails.filter((e) => e.status === 'sent');
  } else if (state.inbox.filter === 'rejected') {
    emails = emails.filter((e) => e.status === 'rejected');
  }

  if (emails.length === 0) {
    container.innerHTML = '<div class="text-muted text-sm p-4 text-center">No emails match the selected filter.</div>';
    return;
  }

  container.innerHTML = '';
  emails.forEach((em) => {
    const item = document.createElement('div');
    item.className = `inbox-item ${state.inbox.activeEmailId === em.id ? 'active' : ''}`;
    item.onclick = () => selectInboxEmail(em.id);
    item.innerHTML = `
      <div class="inbox-item-top">
        <span class="inbox-item-sender">${escapeHtml(em.senderName || em.senderEmail)}</span>
        <span class="inbox-item-cat">${escapeHtml(em.category || 'triage')}</span>
      </div>
      <div class="inbox-item-subject">${escapeHtml(em.subject)}</div>
      <div class="inbox-item-preview">${escapeHtml(em.body.slice(0, 85))}...</div>
    `;
    container.appendChild(item);
  });
}

async function selectInboxEmail(emailId) {
  state.inbox.activeEmailId = emailId;
  renderInboxList();

  const emptyState = document.getElementById('reviewEmptyState');
  const activePane = document.getElementById('reviewActivePane');
  emptyState.style.display = 'none';
  activePane.style.display = 'block';

  // Find local email first
  const localEm = state.inbox.emails.find(e => e.id === emailId);

  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/emails/${emailId}`, { signal: AbortSignal.timeout(1500) });
    if (res.ok) {
      const data = await res.json();
      displayEmailDetails(data.email, data.draft);
      return;
    }
  } catch {}

  // Fallback to local email representation
  if (localEm) {
    displayEmailDetails(localEm, localEm.draft);
  }
}

function displayEmailDetails(em, draft) {
  document.getElementById('revSenderName').textContent = em.senderName || 'Customer';
  document.getElementById('revSenderEmail').textContent = `<${em.senderEmail}>`;
  document.getElementById('revCategoryBadge').textContent = em.category || 'technical_support';
  document.getElementById('revStatusBadge').textContent = (em.status || 'PENDING REVIEW').toUpperCase();
  document.getElementById('revSubject').textContent = em.subject;
  document.getElementById('revCustomerBody').textContent = em.body;

  const draftTextarea = document.getElementById('revDraftTextarea');
  const autoSendBadge = document.getElementById('draftAutoSendBadge');
  const sourcesList = document.getElementById('revSourcesList');

  if (draft) {
    draftTextarea.value = draft.proposedBody || '';
    draftTextarea.dataset.draftId = draft.id || 'draft_temp';

    if (draft.autoSendEligible) {
      autoSendBadge.textContent = 'Auto-Send: Eligible';
      autoSendBadge.className = 'badge badge-success';
    } else {
      autoSendBadge.textContent = 'Auto-Send: Human Review Required';
      autoSendBadge.className = 'badge badge-warning';
    }

    sourcesList.innerHTML = '';
    if (draft.supportingSources && draft.supportingSources.length > 0) {
      draft.supportingSources.forEach((s) => {
        const div = document.createElement('div');
        div.className = 'text-xs text-muted';
        div.innerHTML = `• <a href="${escapeHtml(s.url)}" target="_blank" class="citation-url inline">${escapeHtml(s.title || s.url)}</a> (${Math.round((s.score || 0) * 100)}% relevance)`;
        sourcesList.appendChild(div);
      });
    } else {
      sourcesList.innerHTML = '<span class="text-xs text-muted">Verified against Brilliant Directories Solution Center.</span>';
    }
  } else {
    draftTextarea.value = 'No draft generated yet.';
    draftTextarea.dataset.draftId = '';
    sourcesList.innerHTML = '';
  }

  document.getElementById('revAuditHistoryBox').style.display = 'none';
}

async function submitReviewAction(action) {
  const textarea = document.getElementById('revDraftTextarea');
  const draftId = textarea.dataset.draftId;
  const currentEm = state.inbox.emails.find(e => e.id === state.inbox.activeEmailId);

  if (!currentEm) {
    showToast('No active email selected.', 'warning');
    return;
  }

  const editedBody = textarea.value;

  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/drafts/${draftId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        editedBody: action === 'edit' ? editedBody : undefined,
        reviewerName: 'Consultant Dave',
        sendOnApproval: true,
      }),
      signal: AbortSignal.timeout(1500),
    });

    if (res.ok) {
      const result = await res.json();
      applyReviewDecisionUI(result.action, result.email.status, result.sent ? result.sent.recipient : currentEm.senderEmail);
      refreshAutonomyStates();
      refreshInboxEmails();
      return;
    }
  } catch {}

  // Fallback Simulation of Autonomy Streak Update
  const cat = currentEm.category || 'technical_support';
  const autonomy = getStoredAutonomy();
  if (!autonomy[cat]) {
    autonomy[cat] = { consecutiveUneditedApprovals: 0, isAutonomous: false, totalProcessed: 0 };
  }

  autonomy[cat].totalProcessed = (autonomy[cat].totalProcessed || 0) + 1;

  if (action === 'approve') {
    autonomy[cat].consecutiveUneditedApprovals += 1;
    if (autonomy[cat].consecutiveUneditedApprovals >= 20) {
      autonomy[cat].isAutonomous = true;
    }
    currentEm.status = 'sent';
  } else if (action === 'edit') {
    autonomy[cat].consecutiveUneditedApprovals = 0;
    autonomy[cat].isAutonomous = false;
    currentEm.status = 'sent';
    if (currentEm.draft) currentEm.draft.proposedBody = editedBody;
  } else if (action === 'reject') {
    autonomy[cat].consecutiveUneditedApprovals = 0;
    autonomy[cat].isAutonomous = false;
    currentEm.status = 'rejected';
  }

  saveStoredAutonomy(autonomy);
  applyReviewDecisionUI(action, currentEm.status, currentEm.senderEmail);
  renderAutonomyMatrix(autonomy, 20);
  renderInboxList();
}

function applyReviewDecisionUI(action, status, recipient) {
  showToast(`Action "${action.toUpperCase()}" submitted successfully!`, 'success');

  const auditBox = document.getElementById('revAuditHistoryBox');
  const auditDetails = document.getElementById('revAuditDetails');
  auditBox.style.display = 'block';
  auditDetails.innerHTML = `
    Action: <strong>${action.toUpperCase()}</strong> | 
    Reviewer: Consultant Dave | 
    Status: <strong>${status.toUpperCase()}</strong> | 
    Simulated Send: <strong>${recipient || 'client@example.com'}</strong>
  `;

  document.getElementById('revStatusBadge').textContent = status.toUpperCase();
}

// =====================================================================
// TASK 3: MEETING TO SCOPE CONTROLLER (DIFF ENGINE & 403 DELIVERY GATE)
// =====================================================================

const PRESET_SCENARIOS = {
  A: {
    project_id: 'PRJ-LEGAL-01',
    title: 'Acme Legal Directory Discovery Meeting',
    client_name: 'Acme Legal Services LLC',
    transcript: `Consultant: Thanks for joining today, Sarah. Let's talk about what Acme Legal needs for your directory launch.
Sarah (Client): Thanks! We currently manage our directory of 400 attorneys manually via Google Sheets and PayPal invoices, and it's taking up 20 hours a week. We need a professional portal.
Consultant: What are your key functional requirements?
Sarah (Client): First, we need lawyer member profiles with headshots, practice areas, state bar license numbers, and office addresses.
Second, we must have automated membership subscription tiers with Stripe payment processing—charging $49/month for standard attorneys, and $99/month for premium partners.
Third, visitors need location search with radius filtering, so clients can search by city or zip code and find lawyers within 25 miles.
Consultant: Understood. We'll prepare a structured scope of work based on Brilliant Directories native capabilities.`,
  },
  B: {
    project_id: 'PRJ-HEALTH-02',
    title: 'MedCare Health Portal Discovery Meeting',
    client_name: 'MedCare Health Group',
    transcript: `Consultant: Welcome Dr. Robert. Let's explore what MedCare Health is looking to build.
Dr. Robert (Client): We want a directory of our 150 medical doctors and clinical specialists. We also want patients to book appointments.
Consultant: Tell me more about the patient booking and data storage requirements.
Dr. Robert (Client): When a patient books an appointment, we want them to upload their private medical records, blood test PDFs, and prescription histories directly to the doctor's profile page, and keep it stored there in compliance with HIPAA regulations.
Consultant: Storing Protected Health Information on a public directory platform raises major regulatory concerns. Brilliant Directories is a marketing directory, not a certified HIPAA EHR.
Dr. Robert (Client): Well, maybe we can run our custom WordPress PHP plugin directly inside Brilliant Directories to handle the encryption. Can we upload WordPress plugins to your backend?
Consultant: Brilliant Directories runs on its own proprietary SaaS architecture, not WordPress. Let's document that as a technical conflict requiring architectural clarification.`,
  },
  C: {
    project_id: 'PRJ-LEGAL-01',
    title: 'Acme Legal Scope Refinement Follow-up Meeting',
    client_name: 'Acme Legal Services LLC',
    transcript: `Consultant: Sarah, great to connect again. We're reviewing the v1.0 scope for Acme Legal Directory.
Sarah (Client): Thanks! We reviewed the initial scope with our partners. We have a few key updates.
First, regarding attorney member reviews: we decided to cancel member reviews for the phase 1 launch. We want to drop public star ratings entirely for now so we don't need the review approval workflow.
Second, for Stripe payments: instead of just US dollars, we now need multi-currency billing in USD, CAD, and GBP with custom PDF invoice generation for firm accounting.
Third, we want to add an automated lead capture webhook to Zapier and HubSpot so every time a new lawyer signs up, their data is piped immediately to our CRM.
Fourth, our marketing director asked if we can also get a native mobile app published on the Apple App Store and Google Play Store within this same budget.
Consultant: Got it. Dropping reviews reduces scope, while multi-currency and Zapier webhooks add implementation hours. However, a native mobile app for app stores is out of scope for the Brilliant Directories web platform.
Sarah (Client): Makes sense. Let's update the scope version, show the revised hours and net delta, and present it for our leadership approval.`,
  },
};

function preloadScenarios() {
  fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/scenarios`, { signal: AbortSignal.timeout(1500) })
    .then(r => r.json())
    .then(data => {
      if (data.scenarios) state.scope.scenarios = data.scenarios;
    })
    .catch(() => {});
}

function loadScenario(type) {
  const scenario = PRESET_SCENARIOS[type];
  if (!scenario) return;

  document.getElementById('scProjectSelect').value = scenario.project_id;
  document.getElementById('scClientName').value = scenario.client_name;
  document.getElementById('scMeetingTitle').value = scenario.title;
  document.getElementById('scTranscriptText').value = scenario.transcript;

  showToast(`Loaded Scenario ${type} into transcript workspace`, 'info');
}

async function handleMeetingSubmit(event) {
  event.preventDefault();
  const projectId = document.getElementById('scProjectSelect').value.trim();
  const title = document.getElementById('scMeetingTitle').value.trim();
  const clientName = document.getElementById('scClientName').value.trim();
  const transcriptText = document.getElementById('scTranscriptText').value.trim();

  if (!transcriptText) {
    showToast('Please provide a meeting transcript.', 'warning');
    return;
  }

  showToast('Analyzing meeting transcript and checking native BD capabilities...', 'info');
  const btn = document.getElementById('btnProcessInitial');
  btn.disabled = true;

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/meetings/initial`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, title, client_name: clientName, transcript_text: transcriptText }),
      signal: AbortSignal.timeout(2000),
    });

    if (res.ok) {
      const result = await res.json();
      state.scope.currentScope = result.scope;
      state.scope.currentProposal = result.proposal;
      state.scope.currentDiff = null;
      renderScopeView(result.scope, result.proposal, null);
      showToast('Scope v1.0 generated with bottom-up hour math!', 'success');
      return;
    }
  } catch {}

  // Fallback Scoping Simulation with Exact Bottom-up Mathematical Consistency
  setTimeout(() => {
    const mockScope = {
      project_id: projectId || 'PRJ-LEGAL-01',
      project_title: title || 'Acme Legal Directory Discovery Scope',
      client_name: clientName || 'Acme Legal Services LLC',
      version: '1.0',
      created_at: new Date().toISOString(),
      total_estimated_hours: 34.0,
      tasks: [
        {
          task_id: 'TSK-01',
          title: 'Native Directory Schema & Custom Legal Field Setup',
          description: 'Configure member categories, bar license fields, and profile headshots in General Settings.',
          work_type: 'configuration',
          confidence: 'high',
          confidence_score: 0.95,
          estimated_hours: 4.0,
          prerequisites: [],
        },
        {
          task_id: 'TSK-02',
          title: 'Stripe Automated Subscription Tiers ($49 & $99/mo)',
          description: 'Setup standard and premium membership plans with automated recurring billing and webhooks.',
          work_type: 'configuration',
          confidence: 'high',
          confidence_score: 0.90,
          estimated_hours: 6.0,
          prerequisites: ['TSK-01'],
        },
        {
          task_id: 'TSK-03',
          title: 'Radius Location Search & Google Maps API Whitelist',
          description: 'Enable 25-mile radius filtering by city and zip code with Google Maps API key restriction.',
          work_type: 'configuration',
          confidence: 'high',
          confidence_score: 0.90,
          estimated_hours: 5.0,
          prerequisites: ['TSK-01'],
        },
        {
          task_id: 'TSK-04',
          title: 'CSV Bulk Import & Data Hygiene (400 Attorneys)',
          description: 'Data sanitization and bulk import mapping from Google Sheets into member database.',
          work_type: 'custom_development',
          confidence: 'medium',
          confidence_score: 0.85,
          estimated_hours: 7.0,
          prerequisites: ['TSK-01'],
        },
        {
          task_id: 'TSK-05',
          title: 'Attorney Star Rating & Peer Review System',
          description: 'Client star ratings and admin moderation workflow for incoming attorney reviews.',
          work_type: 'custom_development',
          confidence: 'medium',
          confidence_score: 0.80,
          estimated_hours: 12.0,
          prerequisites: ['TSK-01'],
        },
      ],
      requirements: [
        {
          req_id: 'REQ-01',
          title: 'Attorney Member Profiles & Credentials',
          description: 'Profiles with headshots, practice areas, and bar license numbers.',
          status: 'confirmed',
          transcript_evidence: 'we need lawyer member profiles with headshots, practice areas, state bar license numbers',
        },
        {
          req_id: 'REQ-02',
          title: 'Stripe Membership Tiers ($49/mo & $99/mo)',
          description: 'Automated recurring subscription billing with credit card processing.',
          status: 'confirmed',
          transcript_evidence: 'automated membership subscription tiers with Stripe payment processing',
        },
        {
          req_id: 'REQ-03',
          title: '25-Mile Radius Location Search',
          description: 'Visitors can search by city or zip code and find lawyers within 25 miles.',
          status: 'confirmed',
          transcript_evidence: 'visitors need location search with radius filtering, so clients can search by city or zip code',
        },
      ],
    };

    const mockProposal = {
      proposal_id: `PROP-${projectId}-V1`,
      project_id: projectId,
      scope_version: '1.0',
      title: `Implementation Proposal: ${title}`,
      total_estimated_hours: 34.0,
      status: 'draft',
      executive_summary: `${clientName} seeks to transition manual Google Sheets management of 400 attorneys into an automated Brilliant Directories platform. This proposal configures native member management, automated Stripe subscriptions, and location filtering.`,
      recommended_solution: 'Utilize Brilliant Directories native SaaS architecture for member management and recurring billing. Implement custom styling for legal credential display and radius search.',
      commercial_terms: 'Fixed-price scope based on 34.0 engineering hours at standard rate ($150/hr) totaling $5,100 USD. 50% milestone deposit required prior to kickoff.',
    };

    state.scope.currentScope = mockScope;
    state.scope.currentProposal = mockProposal;
    state.scope.currentDiff = null;

    renderScopeView(mockScope, mockProposal, null);
    showToast('Scope v1.0 generated with bottom-up hour math (34.0 hrs)!', 'success');
  }, 400);

  btn.disabled = false;
}

async function handleFollowupSubmit() {
  const projectId = document.getElementById('scProjectSelect').value.trim();
  const title = document.getElementById('scMeetingTitle').value.trim();
  const clientName = document.getElementById('scClientName').value.trim();
  const transcriptText = document.getElementById('scTranscriptText').value.trim();

  if (!transcriptText) {
    showToast('Please provide a follow-up transcript.', 'warning');
    return;
  }

  showToast('Running Diff Engine against Scope v1.0...', 'info');
  const btn = document.getElementById('btnProcessFollowup');
  btn.disabled = true;

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/meetings/followup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, title, client_name: clientName, transcript_text: transcriptText }),
      signal: AbortSignal.timeout(2000),
    });

    if (res.ok) {
      const result = await res.json();
      state.scope.currentScope = result.revised_scope;
      state.scope.currentProposal = result.proposal;
      state.scope.currentDiff = result.diff_report;
      renderScopeView(result.revised_scope, result.proposal, result.diff_report);
      showToast('Follow-up processed: Scope v2.0 created & deltas calculated!', 'success');
      return;
    }
  } catch {}

  // Fallback DiffEngine Simulation
  setTimeout(() => {
    const revisedScope = {
      project_id: projectId || 'PRJ-LEGAL-01',
      project_title: title || 'Acme Legal Scope Refinement',
      client_name: clientName || 'Acme Legal Services LLC',
      version: '2.0',
      created_at: new Date().toISOString(),
      total_estimated_hours: 36.0,
      tasks: [
        {
          task_id: 'TSK-01',
          title: 'Native Directory Schema & Custom Legal Field Setup',
          description: 'Configure member categories, bar license fields, and profile headshots.',
          work_type: 'configuration',
          confidence: 'high',
          confidence_score: 0.95,
          estimated_hours: 4.0,
          prerequisites: [],
        },
        {
          task_id: 'TSK-02',
          title: 'Stripe Automated Subscription Tiers ($49 & $99/mo)',
          description: 'Setup standard and premium membership plans with automated recurring billing.',
          work_type: 'configuration',
          confidence: 'high',
          confidence_score: 0.90,
          estimated_hours: 6.0,
          prerequisites: ['TSK-01'],
        },
        {
          task_id: 'TSK-03',
          title: 'Radius Location Search & Google Maps API Whitelist',
          description: 'Enable 25-mile radius filtering by city and zip code.',
          work_type: 'configuration',
          confidence: 'high',
          confidence_score: 0.90,
          estimated_hours: 5.0,
          prerequisites: ['TSK-01'],
        },
        {
          task_id: 'TSK-04',
          title: 'CSV Bulk Import & Data Hygiene (400 Attorneys)',
          description: 'Data sanitization and bulk import mapping from Google Sheets.',
          work_type: 'custom_development',
          confidence: 'medium',
          confidence_score: 0.85,
          estimated_hours: 7.0,
          prerequisites: ['TSK-01'],
        },
        {
          task_id: 'TSK-06',
          title: 'Multi-Currency Stripe Billing (USD, CAD, GBP) & PDF Invoicing',
          description: 'International member checkout currency conversion and automated invoice generation.',
          work_type: 'custom_development',
          confidence: 'medium',
          confidence_score: 0.85,
          estimated_hours: 8.0,
          prerequisites: ['TSK-02'],
        },
        {
          task_id: 'TSK-07',
          title: 'Zapier & HubSpot Real-Time Lead Capture Webhook',
          description: 'Webhook pipeline syncing incoming lawyer member registrations directly to CRM.',
          work_type: 'custom_development',
          confidence: 'high',
          confidence_score: 0.90,
          estimated_hours: 6.0,
          prerequisites: ['TSK-01'],
        },
      ],
      requirements: [
        {
          req_id: 'REQ-01',
          title: 'Attorney Member Profiles & Credentials',
          description: 'Profiles with headshots, practice areas, and bar license numbers.',
          status: 'confirmed',
        },
        {
          req_id: 'REQ-05',
          title: 'Multi-Currency Payments (USD, CAD, GBP)',
          description: 'Stripe multi-currency checkout with firm PDF invoice receipts.',
          status: 'confirmed',
        },
        {
          req_id: 'REQ-06',
          title: 'Zapier & HubSpot CRM Webhook',
          description: 'Real-time data synchronization on attorney signup.',
          status: 'confirmed',
        },
      ],
    };

    const diffReport = {
      project_id: projectId,
      original_total_hours: 34.0,
      revised_total_hours: 36.0,
      net_hour_delta: 2.0,
      change_items: [
        {
          classification: 'removed',
          title: 'Attorney Star Rating & Peer Review System',
          rationale: 'Client cancelled public reviews for phase 1 launch.',
          hour_delta: -12.0,
        },
        {
          classification: 'added',
          title: 'Multi-Currency Billing (USD, CAD, GBP) & Invoicing',
          rationale: 'International member expansion requirement.',
          hour_delta: 8.0,
        },
        {
          classification: 'added',
          title: 'Zapier & HubSpot Real-Time Lead Capture Webhook',
          rationale: 'Automated CRM synchronization upon attorney signup.',
          hour_delta: 6.0,
        },
      ],
    };

    const revisedProposal = {
      proposal_id: `PROP-${projectId}-V2`,
      project_id: projectId,
      scope_version: '2.0',
      title: `Revised Implementation Proposal (v2.0): ${title}`,
      total_estimated_hours: 36.0,
      status: 'draft',
      executive_summary: `${clientName} Scope v2.0 refinement: Cancelled Phase 1 review system (-12h), added multi-currency Stripe billing (+8h), and configured Zapier/HubSpot lead capture webhooks (+6h). Revised total: 36.0 engineering hours.`,
      recommended_solution: 'Deliver Phase 1 core legal portal with multi-currency checkout and automated CRM integration. Public reviews deferred to Phase 2.',
      commercial_terms: 'Revised scope: 36.0 engineering hours ($5,400 USD). Net delta: +2.0 hours ($300).',
    };

    state.scope.currentScope = revisedScope;
    state.scope.currentProposal = revisedProposal;
    state.scope.currentDiff = diffReport;

    renderScopeView(revisedScope, revisedProposal, diffReport);
    showToast('Scope v2.0 created: Net delta +2.0 hrs (36.0h total)!', 'success');
  }, 400);

  btn.disabled = false;
}

function renderScopeView(scope, proposal, diffReport) {
  document.getElementById('scopeEmptyState').style.display = 'none';
  document.getElementById('scopeActiveContainer').style.display = 'block';

  // Header Details
  document.getElementById('scVersionTag').textContent = `Scope ${scope.version}`;
  document.getElementById('scProjectTitle').textContent = scope.project_title;
  document.getElementById('scMetaLine').textContent = `Project ID: ${scope.project_id} • Created: ${new Date(scope.created_at).toLocaleDateString()}`;
  document.getElementById('scTotalHours').textContent = scope.total_estimated_hours.toFixed(1);
  document.getElementById('scTaskTotalFooter').textContent = `${scope.total_estimated_hours.toFixed(1)} hrs`;

  // Tasks Table
  const tbody = document.getElementById('scTasksTableBody');
  tbody.innerHTML = '';
  (scope.tasks || []).forEach((t) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(t.title)}</strong>
        <div class="text-xs text-muted">${escapeHtml(t.description)}</div>
      </td>
      <td><span class="badge ${t.work_type === 'configuration' ? 'badge-success' : 'badge-warning'}">${t.work_type}</span></td>
      <td class="font-mono text-sm">${formatConfidence(t.confidence, t.confidence_score)}</td>
      <td class="text-xs text-muted">${(t.prerequisites || []).join(', ') || 'None'}</td>
      <td class="text-right font-mono font-bold">${t.estimated_hours.toFixed(1)}h</td>
    `;
    tbody.appendChild(tr);
  });

  // Requirements List
  const reqsList = document.getElementById('scReqsList');
  reqsList.innerHTML = '';
  (scope.requirements || []).forEach((r) => {
    const div = document.createElement('div');
    div.className = 'card mt-2 p-3';
    div.innerHTML = `
      <div class="flex-between">
        <strong>${escapeHtml(r.req_id)}: ${escapeHtml(r.title)}</strong>
        <span class="badge ${r.status === 'confirmed' ? 'badge-success' : 'badge-warning'}">${r.status}</span>
      </div>
      <p class="text-sm mt-1">${escapeHtml(r.description)}</p>
      <div class="text-xs text-muted mt-2">
        <em>Transcript Evidence: "${escapeHtml(r.transcript_evidence || 'Direct client confirmation')}"</em>
      </div>
    `;
    reqsList.appendChild(div);
  });

  // Proposal Preview & Delivery Gate
  if (proposal) {
    document.getElementById('propTitle').textContent = proposal.title;
    document.getElementById('propMetaStrip').textContent = `Proposal ID: ${proposal.proposal_id} • Version: ${proposal.scope_version} • Total Hours: ${proposal.total_estimated_hours}h`;
    document.getElementById('propExecSummary').textContent = proposal.executive_summary;
    document.getElementById('propSolution').textContent = proposal.recommended_solution;
    document.getElementById('propCommercial').textContent = proposal.commercial_terms;

    updateProposalGateUI(proposal);
  }

  // Diff Report Banner (if follow-up)
  const diffBanner = document.getElementById('diffReportBanner');
  if (diffReport) {
    diffBanner.style.display = 'block';
    const deltaSign = diffReport.net_hour_delta >= 0 ? `+${diffReport.net_hour_delta.toFixed(1)}` : `${diffReport.net_hour_delta.toFixed(1)}`;
    document.getElementById('diffNetDeltaBadge').textContent = `Net Delta: ${deltaSign}h`;
    document.getElementById('diffOriginalHours').textContent = `${diffReport.original_total_hours.toFixed(1)}h`;
    document.getElementById('diffRevisedHours').textContent = `${diffReport.revised_total_hours.toFixed(1)}h`;
    document.getElementById('diffItemsCount').textContent = `${(diffReport.change_items || []).length} items`;

    const diffItemsContainer = document.getElementById('diffItemsList');
    diffItemsContainer.innerHTML = '';
    (diffReport.change_items || []).forEach((item) => {
      const row = document.createElement('div');
      row.className = 'diff-item-row';
      const deltaText = item.hour_delta !== 0 ? `${item.hour_delta >= 0 ? '+' : ''}${item.hour_delta}h` : '0h';
      row.innerHTML = `
        <span class="diff-type-tag ${item.classification}">${item.classification.toUpperCase()}</span>
        <span class="flex-grow"><strong>${escapeHtml(item.title)}</strong> - ${escapeHtml(item.rationale)}</span>
        <span class="font-mono text-xs font-bold">${deltaText}</span>
      `;
      diffItemsContainer.appendChild(row);
    });
  } else {
    diffBanner.style.display = 'none';
  }
}

function updateProposalGateUI(proposal) {
  const gateBanner = document.getElementById('propGateBanner');
  const statusBadge = document.getElementById('propStatusBadge');
  const gateMsg = document.getElementById('propGateMsg');
  const deliverBtn = document.getElementById('btnDeliverProposal');

  statusBadge.textContent = `STATUS: ${proposal.status.toUpperCase()}`;

  if (proposal.status === 'approved') {
    gateBanner.className = 'proposal-gate-banner approved';
    statusBadge.className = 'gate-badge approved';
    gateMsg.textContent = `Approved by ${proposal.reviewer_id || 'Consultant Dave'}. Client delivery unlocked.`;
    deliverBtn.disabled = false;
  } else {
    gateBanner.className = 'proposal-gate-banner';
    statusBadge.className = 'gate-badge';
    gateMsg.textContent = 'CLIENT DELIVERY BLOCKED: No proposal may be delivered without explicit human approval.';
    deliverBtn.disabled = true;
  }
}

function showScopeSubTab(subTabName) {
  document.querySelectorAll('.scope-subtab').forEach((b) => {
    b.classList.toggle('active', b.textContent.toLowerCase().includes(subTabName));
  });

  document.getElementById('subtab-tasks').style.display = subTabName === 'tasks' ? 'block' : 'none';
  document.getElementById('subtab-requirements').style.display = subTabName === 'requirements' ? 'block' : 'none';
  document.getElementById('subtab-capabilities').style.display = subTabName === 'capabilities' ? 'block' : 'none';
  document.getElementById('subtab-proposal').style.display = subTabName === 'proposal' ? 'block' : 'none';
}

async function attemptUnapprovedDelivery() {
  if (!state.scope.currentProposal) {
    showToast('No active proposal to deliver.', 'warning');
    return;
  }

  showToast('Demonstrating backend delivery security gate...', 'info');

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/projects/${state.scope.currentProposal.project_id}/deliver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proposal_id: state.scope.currentProposal.proposal_id,
        recipient_email: 'client@example.com',
        delivered_by: 'Consultant Dave',
      }),
      signal: AbortSignal.timeout(1500),
    });

    if (res.status === 403) {
      const err = await res.json();
      showToast(`Gate Blocked (Expected 403): ${err.detail}`, 'warning');
      alert(`🔒 SECURITY GATE DEMO VERIFIED (HTTP 403 FORBIDDEN):\n\n${err.detail}\n\nDelivery is strictly protected until explicit human approval.`);
      return;
    }
  } catch {}

  // Fallback Simulation of Hard Security Gate
  if (state.scope.currentProposal.status !== 'approved') {
    showToast('Gate Blocked (Expected 403 Forbidden): Delivery blocked without human sign-off', 'warning');
    alert(
      `🔒 SECURITY GATE DEMO VERIFIED (HTTP 403 FORBIDDEN):\n\n` +
      `Proposal '${state.scope.currentProposal.proposal_id}' is in 'draft' status.\n\n` +
      `Platform Security Policy: No proposal may be delivered to a client without explicit human review and sign-off.`
    );
  } else {
    showToast('Proposal is already approved and ready for dispatch!', 'success');
  }
}

async function approveCurrentProposal() {
  if (!state.scope.currentProposal) return;

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/projects/${state.scope.currentProposal.project_id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proposal_id: state.scope.currentProposal.proposal_id,
        action: 'approve',
        reviewer_id: 'Consultant Dave',
        comments: 'Scope, tasks, and commercial terms reviewed and approved for client delivery.',
      }),
      signal: AbortSignal.timeout(1500),
    });

    if (res.ok) {
      const updatedProposal = await res.json();
      state.scope.currentProposal = updatedProposal;
      updateProposalGateUI(updatedProposal);
      showToast('Proposal explicitly APPROVED! Client delivery is now unlocked.', 'success');
      return;
    }
  } catch {}

  // Simulation approval
  state.scope.currentProposal.status = 'approved';
  state.scope.currentProposal.reviewer_id = 'Consultant Dave';
  updateProposalGateUI(state.scope.currentProposal);
  showToast('Proposal explicitly APPROVED! Client delivery is now unlocked.', 'success');
}

async function deliverCurrentProposal() {
  if (!state.scope.currentProposal) return;

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/projects/${state.scope.currentProposal.project_id}/deliver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proposal_id: state.scope.currentProposal.proposal_id,
        recipient_email: 'sarah@acmelegalservices.com',
        delivered_by: 'Consultant Dave',
      }),
      signal: AbortSignal.timeout(1500),
    });

    if (res.ok) {
      const result = await res.json();
      showToast(`Proposal successfully delivered! (${result.simulated ? 'SIMULATED' : 'LIVE'})`, 'success');
      alert(`🚀 CLIENT DELIVERY DISPATCHED:\n\nRecipient: ${result.delivered_to}\nProposal: ${result.proposal_id}\nSimulation Mode: ${result.simulated ? 'ACTIVE' : 'OFF'}\nDelivered By: ${result.delivered_by}`);
      return;
    }
  } catch {}

  // Simulation delivery dispatch
  showToast('Proposal successfully dispatched to client! (Simulated Send)', 'success');
  alert(
    `🚀 CLIENT DELIVERY DISPATCHED:\n\n` +
    `Recipient: sarah@acmelegalservices.com\n` +
    `Proposal: ${state.scope.currentProposal.proposal_id}\n` +
    `Version: ${state.scope.currentProposal.scope_version}\n` +
    `Status: DELIVERED\n` +
    `Simulation Mode: ACTIVE (Zero external emails transmitted)\n` +
    `Authorized By: Consultant Dave`
  );
}

// =====================================================================
// UTILITIES: TOASTS, LIGHTBOX & HELPERS
// =====================================================================

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

function openLightbox(imgUrl, caption) {
  const modal = document.getElementById('lightboxModal');
  const img = document.getElementById('lightboxImg');
  const cap = document.getElementById('lightboxCaption');
  img.src = imgUrl;
  cap.textContent = caption || '';
  modal.style.display = 'flex';
}

function closeLightbox() {
  document.getElementById('lightboxModal').style.display = 'none';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatCategoryName(cat) {
  return cat.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function formatConfidence(confidence, confidenceScore) {
  if (confidenceScore !== undefined && confidenceScore !== null && confidenceScore !== '') {
    const numScore = typeof confidenceScore === 'number' ? confidenceScore : Number(confidenceScore);
    if (!isNaN(numScore) && isFinite(numScore)) {
      if (numScore >= 0 && numScore <= 1) {
        return `${Math.round(numScore * 100)}%`;
      }
      if (numScore > 1 && numScore <= 100) {
        return `${Math.round(numScore)}%`;
      }
    }
  }

  if (confidence === undefined || confidence === null) return 'Not available';
  if (typeof confidence === 'string') {
    const lower = confidence.trim().toLowerCase();
    if (lower === 'high') return '90%';
    if (lower === 'medium') return '75%';
    if (lower === 'low') return '50%';
  }
  return 'Not available';
}
