// charts and the week by week table, used by the member history page and the chair member page

const charts = {};

function drawChart(canvasId, config) {
  // redraws replace the old chart on the same canvas
  if (charts[canvasId]) {
    charts[canvasId].destroy();
  }
  charts[canvasId] = new Chart(document.getElementById(canvasId), config);
}

function allClassCodes(weeks) {
  const codes = new Set();
  weeks.forEach((w) => w.classes.forEach((c) => codes.add(c.code)));
  return [...codes].sort();
}

function renderGpaChart(canvasId, weeks) {
  drawChart(canvasId, {
    type: "line",
    data: {
      labels: weeks.map((w) => "Wk " + w.number),
      datasets: [{
        label: "GPA",
        data: weeks.map((w) => w.gpa),
        borderColor: CHART_COLORS[0],
        backgroundColor: CHART_COLORS[0],
        tension: 0.2,
      }],
    },
    options: {
      maintainAspectRatio: false,
      scales: { y: { min: 0, max: 4 } },
      plugins: { legend: { display: false } },
    },
  });
}

function renderClassChart(canvasId, weeks) {
  const datasets = allClassCodes(weeks).map((code, i) => {
    const color = CHART_COLORS[i % CHART_COLORS.length];
    return {
      label: code,
      data: weeks.map((w) => {
        const c = w.classes.find((x) => x.code === code);
        if (c) {
          return c.percent;
        }
        return null;
      }),
      borderColor: color,
      backgroundColor: color,
      tension: 0.2,
    };
  });

  drawChart(canvasId, {
    type: "line",
    data: { labels: weeks.map((w) => "Wk " + w.number), datasets },
    options: {
      maintainAspectRatio: false,
      scales: { y: { suggestedMin: 50, suggestedMax: 100 } },
    },
  });
}

function renderHouseChart(canvasId, stats) {
  drawChart(canvasId, {
    data: {
      labels: stats.map((s) => "Wk " + s.number),
      datasets: [
        {
          type: "line",
          label: "Average GPA",
          data: stats.map((s) => s.avg_gpa),
          borderColor: CHART_COLORS[0],
          backgroundColor: CHART_COLORS[0],
          yAxisID: "gpa",
          tension: 0.2,
        },
        {
          type: "bar",
          label: "Missing",
          data: stats.map((s) => s.missing),
          backgroundColor: "rgba(217, 83, 79, 0.35)",
          yAxisID: "count",
        },
        {
          type: "bar",
          label: "Late",
          data: stats.map((s) => s.late),
          backgroundColor: "rgba(230, 162, 60, 0.4)",
          yAxisID: "count",
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      scales: {
        gpa: { position: "left", min: 0, max: 4, title: { display: true, text: "GPA" } },
        count: { position: "right", beginAtZero: true, ticks: { precision: 0 }, grid: { drawOnChartArea: false }, title: { display: true, text: "Members" } },
      },
    },
  });
}

// newest week first, one column per class
// actions (chair only): { onMute(week, flag), onUnmute(flag), onCorrect(week), onScreenshot(week) }
function renderHistoryTable(weeks, showFlags, actions) {
  const codes = allClassCodes(weeks);

  const head = document.getElementById("table-head");
  head.innerHTML = "";
  const hr = el("tr");
  ["Week", "Status", "GPA", "Change"].forEach((t) => hr.appendChild(el("th", {}, t)));
  codes.forEach((code) => hr.appendChild(el("th", {}, code)));
  if (showFlags) {
    hr.appendChild(el("th", {}, "Flags"));
  }
  if (actions) {
    hr.appendChild(el("th", {}, ""));
  }
  head.appendChild(hr);

  const body = document.getElementById("table-body");
  body.innerHTML = "";
  [...weeks].reverse().forEach((w) => {
    const tr = el("tr");
    if (showFlags && activeFlags(w.flags).length > 0) {
      tr.className = "flagged";
    }

    const weekCell = el("td", { class: "nowrap" }, "Week " + w.number);
    weekCell.appendChild(el("div", { class: "muted" }, "due " + formatDate(w.due_at)));
    if (actions && w.screenshot_id) {
      const shot = el("button", { type: "button", class: "secondary small shot-btn", title: "View Canvas screenshot" }, "📷 View");
      shot.addEventListener("click", () => actions.onScreenshot(w));
      weekCell.appendChild(shot);
    }
    tr.appendChild(weekCell);

    const statusCell = el("td");
    statusCell.appendChild(statusBadge(w.status));
    tr.appendChild(statusCell);

    tr.appendChild(el("td", {}, formatGpa(w.gpa)));

    const changeTd = el("td", { class: "nowrap" });
    changeTd.appendChild(changeCell(w.gpa_change, 2, ""));
    tr.appendChild(changeTd);

    codes.forEach((code) => {
      const td = el("td", { class: "nowrap" });
      const c = w.classes.find((x) => x.code === code);
      if (c) {
        td.appendChild(el("span", {}, c.percent + "% " + (c.letter || "")));
        if (c.corrected) {
          td.appendChild(el("span", { class: "corrected", title: "Corrected by the scholarship chair" }, " ✎"));
        }
        if (c.change !== null) {
          td.appendChild(el("br"));
          td.appendChild(changeCell(c.change, 1, "%"));
        }
      } else {
        td.textContent = "–";
        td.className = "muted";
      }
      tr.appendChild(td);
    });

    if (showFlags) {
      const td = el("td");
      w.flags.forEach((f) => {
        const wrap = el("span", { class: "flag-wrap" });
        wrap.appendChild(flagBadge(f));
        if (actions) {
          let btn;
          if (f.muted) {
            btn = el("button", { type: "button", class: "link tiny" }, "unmute");
            btn.addEventListener("click", () => actions.onUnmute(f));
          } else {
            btn = el("button", { type: "button", class: "link tiny" }, "mute");
            btn.addEventListener("click", () => actions.onMute(w, f));
          }
          wrap.appendChild(btn);
        }
        td.appendChild(wrap);
      });
      tr.appendChild(td);
    }

    if (actions) {
      const td = el("td");
      // only weeks the member actually submitted can be corrected
      if (w.classes.length > 0) {
        const btn = el("button", { type: "button", class: "secondary small" }, "Correct");
        btn.addEventListener("click", () => actions.onCorrect(w));
        td.appendChild(btn);
      }
      tr.appendChild(td);
    }
    body.appendChild(tr);
  });
}
