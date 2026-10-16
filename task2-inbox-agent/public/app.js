/**
 * BusinessLabs AI Tech Consultant - Unified Frontend Application
 * Connects directly to Task 1 (:8000), Task 2 (:3000), and Task 3 (:8001)
 */

const API_CONFIG = {
  kbBaseUrl: 'http://127.0.0.1:8000',
  inboxBaseUrl: 'http://127.0.0.1:3000',
  scopeBaseUrl: 'http://127.0.0.1:8001',
};

// Global App State
const state = {
  activeTab: 'overview',
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

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  checkServicesHealth();
  setInterval(checkServicesHealth, 8000);

  // Load initial data for tabs
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

// --- Health Probing ---
async function checkServicesHealth() {
  const updatePill = (elemId, isHealthy) => {
    const el = document.getElementById(elemId);
    if (!el) return;
    el.querySelector('.dot').style.background = isHealthy ? 'var(--accent-emerald)' : 'var(--accent-rose)';
  };

  // 1. Task 1 Knowledge Brain (:8000)
  try {
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/health`, { method: 'GET' });
    state.services.kb = res.ok;
  } catch {
    state.services.kb = false;
  }
  updatePill('t1Status', state.services.kb);

  // 2. Task 2 Inbox Agent (:3000)
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/health`, { method: 'GET' });
    state.services.inbox = res.ok;
  } catch {
    state.services.inbox = false;
  }
  updatePill('t2Status', state.services.inbox);

  // 3. Task 3 Meeting to Scope (:8001)
  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/health`, { method: 'GET' });
    state.services.scope = res.ok;
  } catch {
    state.services.scope = false;
  }
  updatePill('t3Status', state.services.scope);

  // Global Indicator
  const allOnline = state.services.kb && state.services.inbox && state.services.scope;
  const globalDot = document.getElementById('globalHealthDot');
  const globalText = document.getElementById('globalHealthText');
  if (globalDot && globalText) {
    if (allOnline) {
      globalDot.style.background = 'var(--accent-emerald)';
      globalText.textContent = 'All Services Online';
    } else {
      const offline = [];
      if (!state.services.kb) offline.push('Task 1');
      if (!state.services.inbox) offline.push('Task 2');
      if (!state.services.scope) offline.push('Task 3');
      globalDot.style.background = 'var(--accent-amber)';
      globalText.textContent = `${offline.join(', ')} Offline`;
    }
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
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/health`);
    if (res.ok) {
      const data = await res.json();
      const articlesEl = document.getElementById('kbTotalArticles');
      const chunksEl = document.getElementById('kbTotalChunks');
      if (articlesEl && data.total_articles !== undefined) articlesEl.textContent = data.total_articles;
      if (chunksEl && data.total_chunks !== undefined) chunksEl.textContent = data.total_chunks;
    }
  } catch (err) {
    console.warn('Unable to fetch KB health:', err);
  }

  // Load escalations count
  try {
    const escRes = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/escalations`);
    if (escRes.ok) {
      const escData = await escRes.json();
      const countEl = document.getElementById('escalationCount');
      if (countEl && Array.isArray(escData)) countEl.textContent = escData.filter(e => e.status === 'open').length;
    }
  } catch (err) {
    console.warn('Unable to fetch escalations count:', err);
  }
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
    });

    const elapsed = Math.round(performance.now() - startTime);

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    renderKbResponse(data, elapsed);
    showToast('Knowledge Brain answered inquiry successfully', 'success');
  } catch (err) {
    showToast(`Knowledge Brain Error: ${err.message}`, 'error');
  } finally {
    spinner.style.display = 'none';
    submitBtn.disabled = false;
  }
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

  // Images
  const imagesSection = document.getElementById('kbImagesSection');
  const imagesGallery = document.getElementById('kbImagesGallery');
  imagesGallery.innerHTML = '';

  const images = data.images || [];
  if (images.length > 0) {
    imagesSection.style.display = 'block';
    images.forEach((img) => {
      const card = document.createElement('div');
      card.className = 'image-thumb-card';
      card.onclick = () => openLightbox(img.url, img.caption || 'Documentation Screenshot');
      card.innerHTML = `
        <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.caption || 'Screenshot')}" onerror="this.src='https://placehold.co/300x180/1e293b/94a3b8?text=Documentation+Screenshot'">
        <div class="image-thumb-caption">${escapeHtml(img.caption || 'Attached Screenshot')}</div>
      `;
      imagesGallery.appendChild(card);
    });
  } else {
    imagesSection.style.display = 'none';
  }
}

async function triggerKbSync() {
  showToast('Starting incremental sitemap sync...', 'info');
  try {
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/sync`, { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(`Sync complete! ${data.message || 'Articles indexed.'}`, 'success');
      loadKbStatus();
    } else {
      showToast('Sitemap sync returned status ' + res.status, 'warning');
    }
  } catch (err) {
    showToast(`Sitemap sync error: ${err.message}`, 'error');
  }
}

async function loadEscalations() {
  const modal = document.getElementById('escalationModal');
  const container = document.getElementById('escalationTableContainer');
  modal.style.display = 'flex';
  container.innerHTML = '<div class="p-4 text-center">Loading escalations...</div>';

  try {
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/escalations`);
    const escalations = await res.json();

    if (!Array.isArray(escalations) || escalations.length === 0) {
      container.innerHTML = '<div class="empty-state p-4"><h4>No Active Escalations</h4><p class="text-muted">All inquiries have been answered or resolved.</p></div>';
      return;
    }

    let html = `
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Question</th>
              <th>Reason</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
    `;

    escalations.forEach((esc) => {
      html += `
        <tr>
          <td class="font-mono text-xs">${escapeHtml(esc.escalation_id)}</td>
          <td><strong>${escapeHtml(esc.query)}</strong></td>
          <td class="text-xs text-muted">${escapeHtml(esc.reason)}</td>
          <td><span class="badge ${esc.status === 'open' ? 'badge-warning' : 'badge-success'}">${esc.status}</span></td>
          <td>
            ${esc.status === 'open' ? `<button class="btn btn-primary btn-sm" onclick="promptResolveEscalation('${esc.escalation_id}')">Resolve & Teach</button>` : '<span class="text-xs text-muted">Resolved</span>'}
          </td>
        </tr>
      `;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<div class="p-4 text-danger">Failed to load escalations: ${err.message}</div>`;
  }
}

function closeEscalationsModal() {
  document.getElementById('escalationModal').style.display = 'none';
}

async function promptResolveEscalation(escId) {
  const answer = prompt(`Enter human expert answer for escalation ${escId}:\n(This resolution will be permanently indexed into ChromaDB vector store)`);
  if (!answer || !answer.trim()) return;

  try {
    const res = await fetch(`${API_CONFIG.kbBaseUrl}/api/v1/escalations/${escId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resolution: answer.trim(),
        resolved_by: 'Consultant Dave',
        auto_index: true,
      }),
    });

    if (res.ok) {
      showToast('Escalation resolved! Answer indexed into Knowledge Brain.', 'success');
      loadEscalations();
      loadKbStatus();
    } else {
      showToast('Failed to resolve escalation', 'error');
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

// =====================================================================
// TASK 2: INBOX AGENT CONTROLLER
// =====================================================================

async function refreshAutonomyStates() {
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/autonomy`);
    if (!res.ok) return;
    const data = await res.json();
    state.inbox.autonomyStates = data.states || {};
    renderAutonomyGrid(data.states || {}, data.streakThreshold || 20);
  } catch (err) {
    console.warn('Unable to load autonomy states:', err);
  }
}

function renderAutonomyGrid(states, threshold) {
  const container = document.getElementById('autonomyCategoriesGrid');
  if (!container) return;

  const categories = [
    'technical_support',
    'billing_and_payments',
    'account_and_login',
    'product_configuration',
    'feature_requests',
    'complaints_and_feedback',
    'other_or_uncertain',
  ];

  container.innerHTML = '';
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
  showToast('Loading 55 synthetic customer emails...', 'info');
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/synthetic`);
    if (!res.ok) throw new Error('Failed to fetch synthetic emails');
    const data = await res.json();

    // Ingest the first 8 emails automatically into the inbox queue if empty
    const emailsToIngest = (data.emails || []).slice(0, 10);
    for (const em of emailsToIngest) {
      await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/emails`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: em.id,
          senderEmail: em.senderEmail,
          senderName: em.senderName || 'Customer',
          subject: em.subject,
          body: em.body,
        }),
      }).catch(() => {});
    }

    await refreshInboxEmails();
    refreshAutonomyStates();
    showToast('Synthetic emails ingested into queue!', 'success');
  } catch (err) {
    showToast(`Failed loading synthetic emails: ${err.message}`, 'error');
  }
}

async function refreshInboxEmails() {
  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/emails`);
    if (!res.ok) return;
    const data = await res.json();
    state.inbox.emails = data.emails || [];

    // Update count badge
    document.getElementById('inboxCountBadge').textContent = `${state.inbox.emails.length} emails`;
    renderInboxList();
  } catch (err) {
    console.warn('Unable to list inbox emails:', err);
  }
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

  const emails = state.inbox.emails.filter((em) => {
    if (state.inbox.filter === 'all') return true;
    if (state.inbox.filter === 'pending') return em.status === 'pending_review' || !em.status;
    if (state.inbox.filter === 'sent') return em.status === 'sent';
    if (state.inbox.filter === 'rejected') return em.status === 'rejected';
    return true;
  });

  if (emails.length === 0) {
    container.innerHTML = '<div class="p-4 text-center text-muted text-sm">No emails match the selected filter.</div>';
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
        <span class="inbox-item-cat">${escapeHtml(em.category || 'Triage')}</span>
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

  try {
    const res = await fetch(`${API_CONFIG.inboxBaseUrl}/api/v1/inbox/emails/${emailId}`);
    if (!res.ok) throw new Error('Email details failed');
    const data = await res.json();
    const em = data.email;
    const draft = data.draft;

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
      draftTextarea.dataset.draftId = draft.id;

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
        sourcesList.innerHTML = '<span class="text-xs text-muted">No external KB sources cited.</span>';
      }
    } else {
      draftTextarea.value = 'No draft generated yet.';
      draftTextarea.dataset.draftId = '';
      sourcesList.innerHTML = '';
    }

    // Hide audit history until action taken
    document.getElementById('revAuditHistoryBox').style.display = 'none';
  } catch (err) {
    showToast(`Failed loading draft: ${err.message}`, 'error');
  }
}

async function submitReviewAction(action) {
  const textarea = document.getElementById('revDraftTextarea');
  const draftId = textarea.dataset.draftId;
  if (!draftId) {
    showToast('No active draft selected.', 'warning');
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
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.error || 'Review failed');

    showToast(`Action "${action.toUpperCase()}" submitted successfully!`, 'success');

    // Show decision details
    const auditBox = document.getElementById('revAuditHistoryBox');
    const auditDetails = document.getElementById('revAuditDetails');
    auditBox.style.display = 'block';
    auditDetails.innerHTML = `
      Action: <strong>${result.action.toUpperCase()}</strong> | 
      Reviewer: ${result.decision.reviewerName || 'Dave'} | 
      Status: ${result.email.status} | 
      Simulated Send: <strong>${result.sent ? result.sent.recipient : 'N/A'}</strong>
    `;

    document.getElementById('revStatusBadge').textContent = (result.email.status || 'SENT').toUpperCase();

    // Refresh streak and email queues
    refreshAutonomyStates();
    refreshInboxEmails();
  } catch (err) {
    showToast(`Review Submission Error: ${err.message}`, 'error');
  }
}

// =====================================================================
// TASK 3: MEETING TO SCOPE CONTROLLER
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
Second, we must have automated membership subscription tiers with Stripe payment processing—charging $49/month for standard attorneys and $99/month for premium partners.
Third, visitors need location search with radius filtering, so clients can search by city or zip code and find lawyers within 25 miles.
Fourth, we want modern brand styling matching our corporate deep blue and gold color scheme with our firm logo in the header.
Consultant: What about administrative controls and reviews?
Sarah (Client): We need member reviews where clients can leave 5-star ratings and written feedback, but our admin team must approve them before they go public.
Consultant: Any custom integrations or external tools?
Sarah (Client): For now, just Google Maps for the address geocoding and Stripe for payments. We'll provide our Stripe keys and logo assets next Monday.
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
Consultant: Brilliant Directories runs on its own proprietary SaaS architecture, not WordPress. Let's document that as a technical conflict requiring architectural clarification.
Dr. Robert (Client): Also, we want a native mobile app for iOS and Android published on the Apple App Store and Google Play Store where users can download it as an offline native application.
Consultant: What is your timeline and budget for native app development versus responsive web?
Dr. Robert (Client): We aren't sure on the app budget yet. Can you give us an estimate or clarify what is native versus web?`,
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
Consultant: Got it. Dropping reviews reduces scope, while multi-currency and Zapier webhooks add implementation hours. However, a native mobile app for app stores is out of scope for the Brilliant Directories web platform and would require a dedicated mobile build.
Sarah (Client): Makes sense. Let's update the scope version, show the revised hours and net delta, and present it for our leadership approval.`,
  },
};

function preloadScenarios() {
  fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/scenarios`)
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

  showToast('Analyzing meeting transcript and checking capabilities...', 'info');
  const btn = document.getElementById('btnProcessInitial');
  btn.disabled = true;

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/meetings/initial`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        title,
        client_name: clientName,
        transcript_text: transcriptText,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const result = await res.json();
    state.scope.currentScope = result.scope;
    state.scope.currentProposal = result.proposal;
    state.scope.currentDiff = null;

    renderScopeView(result.scope, result.proposal, null);
    showToast('Scope v1.0 generated with bottom-up hour math!', 'success');
  } catch (err) {
    showToast(`Error processing meeting: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
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
      body: JSON.stringify({
        project_id: projectId,
        title,
        client_name: clientName,
        transcript_text: transcriptText,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const result = await res.json();
    state.scope.currentScope = result.revised_scope;
    state.scope.currentProposal = result.proposal;
    state.scope.currentDiff = result.diff_report;

    renderScopeView(result.revised_scope, result.proposal, result.diff_report);
    showToast('Follow-up processed: Scope v2.0 created & deltas calculated!', 'success');
  } catch (err) {
    showToast(`Follow-up error: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
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
        <em>Transcript Evidence: "${escapeHtml(r.transcript_evidence || '')}"</em>
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
    gateMsg.textContent = `Approved by ${proposal.reviewer_id || 'Human Reviewer'}. Delivery unlocked.`;
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

  showToast('Demonstrating backend delivery gate test...', 'info');

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/projects/${state.scope.currentProposal.project_id}/deliver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proposal_id: state.scope.currentProposal.proposal_id,
        recipient_email: 'client@example.com',
        delivered_by: 'Consultant Dave',
      }),
    });

    if (res.status === 403) {
      const err = await res.json();
      showToast(`Gate Blocked (Expected 403): ${err.detail}`, 'warning');
      alert(`🔒 SECURITY GATE DEMO VERIFIED (HTTP 403 FORBIDDEN):\n\n${err.detail}\n\nDelivery is strictly protected until human approval.`);
    } else if (res.ok) {
      showToast('Proposal was delivered because it is already approved!', 'success');
    } else {
      const err = await res.json();
      showToast(`Error: ${err.detail || res.status}`, 'error');
    }
  } catch (err) {
    showToast(`Network error: ${err.message}`, 'error');
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
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Approval failed');
    }

    const updatedProposal = await res.json();
    state.scope.currentProposal = updatedProposal;
    updateProposalGateUI(updatedProposal);
    showToast('Proposal explicitly APPROVED! Client delivery is now unlocked.', 'success');
  } catch (err) {
    showToast(`Approval Error: ${err.message}`, 'error');
  }
}

async function deliverCurrentProposal() {
  if (!state.scope.currentProposal) return;

  try {
    const res = await fetch(`${API_CONFIG.scopeBaseUrl}/api/v1/projects/${state.scope.currentProposal.project_id}/deliver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proposal_id: state.scope.currentProposal.proposal_id,
        recipient_email: 'client@example.com',
        delivered_by: 'Consultant Dave',
      }),
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Delivery failed');

    showToast(`Proposal successfully delivered! (${result.simulated ? 'SIMULATED' : 'LIVE'})`, 'success');
    alert(`🚀 CLIENT DELIVERY DISPATCHED:\n\nRecipient: ${result.delivered_to}\nProposal: ${result.proposal_id}\nSimulation Mode: ${result.simulated ? 'ACTIVE (Zero external emails sent)' : 'OFF'}\nDelivered By: ${result.delivered_by}`);
  } catch (err) {
    showToast(`Delivery Error: ${err.message}`, 'error');
  }
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

/**
 * Safely format a task confidence value as a percentage.
 * Handles numbers, proportion decimals (0..1), percentages (1..100), numeric strings,
 * qualitative enum values, and safely returns "Not available" for missing, null,
 * non-numeric, or out-of-range inputs.
 *
 * @param {*} confidence Raw confidence value (enum, number, string, null, undefined)
 * @param {*} [confidenceScore] Optional numeric confidence score from API
 * @returns {string} Formatted percentage (e.g. "95%") or "Not available"
 */
function formatConfidence(confidence, confidenceScore) {
  // If a valid numeric confidenceScore is provided, prioritize it
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

  // Handle missing, null, undefined, boolean, object, function
  if (confidence === undefined || confidence === null) {
    return 'Not available';
  }
  if (typeof confidence === 'boolean' || typeof confidence === 'object' || typeof confidence === 'function') {
    return 'Not available';
  }

  // Handle string values
  if (typeof confidence === 'string') {
    const trimmed = confidence.trim();
    if (!trimmed) {
      return 'Not available';
    }

    const lower = trimmed.toLowerCase();
    // Known qualitative enum values
    if (lower === 'high') {
      return '90%';
    }
    if (lower === 'medium') {
      return '75%';
    }
    if (lower === 'low') {
      return '50%';
    }
    if (lower === 'provisional' || lower === 'uncertain' || lower === 'needs_clarification') {
      return 'Not available';
    }

    // Percentage string e.g. "85%"
    if (trimmed.endsWith('%')) {
      const numPart = Number(trimmed.slice(0, -1).trim());
      if (!isNaN(numPart) && isFinite(numPart) && numPart >= 0 && numPart <= 100) {
        return `${Math.round(numPart)}%`;
      }
      return 'Not available';
    }

    // Numeric string e.g. "0.85" or "85"
    const parsed = Number(trimmed);
    if (isNaN(parsed) || !isFinite(parsed)) {
      return 'Not available';
    }

    if (parsed >= 0 && parsed <= 1) {
      return `${Math.round(parsed * 100)}%`;
    }
    if (parsed > 1 && parsed <= 100) {
      return `${Math.round(parsed)}%`;
    }
    return 'Not available';
  }

  // Handle numeric values
  if (typeof confidence === 'number') {
    if (isNaN(confidence) || !isFinite(confidence)) {
      return 'Not available';
    }
    if (confidence >= 0 && confidence <= 1) {
      return `${Math.round(confidence * 100)}%`;
    }
    if (confidence > 1 && confidence <= 100) {
      return `${Math.round(confidence)}%`;
    }
    return 'Not available';
  }

  return 'Not available';
}

