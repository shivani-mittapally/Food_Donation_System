/* =====================================================
   Food Donation System — script.js
   ===================================================== */

document.addEventListener('DOMContentLoaded', () => {

  /* ── Sidebar mobile toggle ─────────────────────────── */
  const sidebar = document.getElementById('sidebar');
  const toggleBtn = document.getElementById('sidebarToggle');
  const overlay = document.getElementById('sidebarOverlay');

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      if (overlay) overlay.classList.toggle('active');
    });
  }
  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar?.classList.remove('open');
      overlay.classList.remove('active');
    });
  }

  /* ── Auto-dismiss flash messages ──────────────────── */
  document.querySelectorAll('.alert').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity .5s, transform .5s';
      el.style.opacity = '0';
      el.style.transform = 'translateY(-8px)';
      setTimeout(() => el.remove(), 500);
    }, 4500);
  });

  /* ── Active nav link ───────────────────────────────── */
  document.querySelectorAll('.nav-link').forEach(link => {
    if (link.href === window.location.href) link.classList.add('active');
  });

  /* ── Charts (if canvas elements exist) ─────────────── */
  initCharts();

  /* ── Expiry countdown ──────────────────────────────── */
  updateExpiryCountdowns();

  /* ── Search form enter key ─────────────────────────── */
  document.querySelectorAll('.search-bar input').forEach(inp => {
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') inp.closest('form')?.submit();
    });
  });
});


/* ── Chart initialisation ──────────────────────────────── */
function initCharts() {
  const donutCtx = document.getElementById('statusChart');
  const barCtx   = document.getElementById('monthlyChart');
  if (!donutCtx && !barCtx) return;

  // Fetch status data
  fetch('/api/chart-data')
    .then(r => r.json())
    .then(data => {
      if (!donutCtx) return;
      const labels = Object.keys(data);
      const values = Object.values(data);
      const colorMap = {
        pending:   '#f59e0b',
        accepted:  '#3b82f6',
        collected: '#14b8a6',
        delivered: '#22c55e',
        expired:   '#ef4444',
      };
      new Chart(donutCtx, {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{
            data: values,
            backgroundColor: labels.map(l => colorMap[l] || '#6b9e7a'),
            borderWidth: 0,
            hoverOffset: 8,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: { color: '#e2f5ea', font: { family: 'DM Sans', size: 12 }, padding: 16 }
            }
          },
          cutout: '65%',
        }
      });
    })
    .catch(() => {});

  // Fetch monthly data
  fetch('/api/monthly-data')
    .then(r => r.json())
    .then(data => {
      if (!barCtx) return;
      const sorted = [...data].reverse();
      new Chart(barCtx, {
        type: 'bar',
        data: {
          labels: sorted.map(d => d.month),
          datasets: [{
            label: 'Donations',
            data: sorted.map(d => d.count),
            backgroundColor: 'rgba(34,197,94,.6)',
            borderColor: '#22c55e',
            borderWidth: 1,
            borderRadius: 6,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#6b9e7a' }, grid: { color: 'rgba(30,48,39,.5)' } },
            y: { ticks: { color: '#6b9e7a' }, grid: { color: 'rgba(30,48,39,.5)' }, beginAtZero: true }
          }
        }
      });
    })
    .catch(() => {});
}


/* ── Expiry countdown ────────────────────────────────────── */
function updateExpiryCountdowns() {
  document.querySelectorAll('[data-expiry]').forEach(el => {
    const expiry = new Date(el.dataset.expiry);
    if (isNaN(expiry)) return;
    const now = new Date();
    const diffMs = expiry - now;
    if (diffMs < 0) {
      el.textContent = 'Expired';
      el.style.color = '#ef4444';
      return;
    }
    const diffH = Math.floor(diffMs / 3600000);
    const diffM = Math.floor((diffMs % 3600000) / 60000);
    if (diffH < 3) el.style.color = '#ef4444';
    else if (diffH < 12) el.style.color = '#f59e0b';
    el.textContent = diffH > 0 ? `${diffH}h ${diffM}m left` : `${diffM}m left`;
  });
}


/* ── Confirm delete ──────────────────────────────────────── */
function confirmDelete(url, msg) {
  if (confirm(msg || 'Are you sure you want to delete this?')) {
    window.location.href = url;
  }
}


/* ── Image preview on file select ─────────────────────────── */
function previewImage(input) {
  const preview = document.getElementById('imagePreview');
  if (!preview) return;
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = e => {
      preview.src = e.target.result;
      preview.style.display = 'block';
    };
    reader.readAsDataURL(input.files[0]);
  }
}
