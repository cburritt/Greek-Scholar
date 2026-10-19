// helpers shared by every page

const STATUS_LABELS = {
  on_time: "On time",
  late: "Late",
  missing: "Missing",
  open: "Not due yet",
  not_member: "Before joining",
};

const FLAG_LABELS = {
  missing: "Missing a week",
  late: "Late submission",
  gpa_below: "GPA below",
  class_below: "Any class below (%)",
  gpa_drop: "GPA dropped by at least",
  class_drop: "A class dropped by at least (%)",
  missed_in_row: "Missed weeks in a row",
};

const NAV = {
  member: [
    { href: "submit.html", text: "Submit" },
    { href: "classes.html", text: "My classes" },
    { href: "history.html", text: "History" },
  ],
  chair: [
    { href: "chair.html", text: "Members" },
    { href: "settings.html", text: "Settings" },
  ],
};

function homeFor(user) {
  if (user.role === "chair") {
    return "chair.html";
  }
  return "submit.html";
}

// send them away if they are not logged in as the right role
function requireRole(role) {
  const user = currentUser();
  if (!user) {
    window.location.href = "index.html";
    return null;
  }
  if (user.role !== role) {
    window.location.href = homeFor(user);
    return null;
  }
  renderHeader(user);
  return user;
}

function renderHeader(user) {
  const header = document.getElementById("header");
  header.innerHTML = "";

  const left = el("div", { class: "header-left" });
  left.appendChild(el("h1", {}, "Greek Scholar"));
  const nav = el("nav");
  const page = window.location.pathname.split("/").pop();
  NAV[user.role].forEach((link) => {
    const a = el("a", { href: link.href }, link.text);
    if (page === link.href) {
      a.className = "active";
    }
    nav.appendChild(a);
  });
  left.appendChild(nav);

  const right = el("div", { class: "header-right" });
  right.appendChild(el("span", { class: "muted" }, user.name));
  const out = el("button", { class: "link", type: "button" }, "Log out");
  out.addEventListener("click", () => {
    logout();
    window.location.href = "index.html";
  });
  right.appendChild(out);

  header.appendChild(left);
  header.appendChild(right);
}

// small dom builder
function el(tag, attrs, text) {
  const node = document.createElement(tag);
  if (attrs) {
    Object.keys(attrs).forEach((key) => node.setAttribute(key, attrs[key]));
  }
  if (text !== undefined && text !== null) {
    node.textContent = text;
  }
  return node;
}

function showMessage(id, text, kind) {
  const msg = document.getElementById(id);
  msg.textContent = text;
  msg.className = "message " + kind;
}

function statusBadge(status) {
  return el("span", { class: "badge status-" + status }, STATUS_LABELS[status] || status);
}

function flagBadge(flag) {
  return el("span", { class: "badge flag" }, flag.label);
}

function formatDue(iso) {
  return new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatGpa(gpa) {
  if (gpa === null || gpa === undefined) {
    return "–";
  }
  return gpa.toFixed(2);
}

// arrow and size of a change, empty if there is nothing to compare
function changeCell(change, digits, suffix) {
  const span = el("span", { class: "change" });
  if (change === null || change === undefined) {
    span.textContent = "–";
    span.classList.add("muted");
    return span;
  }
  if (change > 0) {
    span.textContent = "▲ " + change.toFixed(digits) + suffix;
    span.classList.add("up");
  } else if (change < 0) {
    span.textContent = "▼ " + Math.abs(change).toFixed(digits) + suffix;
    span.classList.add("down");
  } else {
    span.textContent = "0" + suffix;
    span.classList.add("muted");
  }
  return span;
}

// same math as the backend so the submit page can preview
function letterFor(percent, scale) {
  for (const row of scale) {
    if (percent >= row.min_percent) {
      return row;
    }
  }
  return null;
}

function previewGpa(entries, scale) {
  let points = 0;
  let credits = 0;
  entries.forEach((e) => {
    const row = letterFor(e.percent, scale);
    if (row) {
      points += row.points * e.credits;
      credits += e.credits;
    }
  });
  if (credits === 0) {
    return null;
  }
  return points / credits;
}

function weekLabel(week) {
  let text = "Week " + week.number + " · due " + formatDue(week.due_at);
  if (week.status) {
    text += " · " + STATUS_LABELS[week.status];
  }
  return text;
}

// shared chart colors
const CHART_COLORS = ["#2f5bd3", "#d9534f", "#1e8e4e", "#e6a23c", "#8e44ad", "#16a2b8", "#7f8c8d"];
