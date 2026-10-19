// fake api that keeps everything in localStorage
// swap these functions for fetch calls once the fastapi backend exists

const DB_KEY = "gs_db";
const SESSION_KEY = "gs_session";

// sample data so the chair table has something to show
function seedDb() {
  return {
    nextUserId: 7,
    users: [
      { id: 1, name: "Chair", email: "chair@test.com", password: "chair123", role: "chair", pledgeClass: "" },
      { id: 2, name: "Alex Carter", email: "alex@test.com", password: "test123", role: "member", pledgeClass: "Fall 2024" },
      { id: 3, name: "Jordan Lee", email: "jordan@test.com", password: "test123", role: "member", pledgeClass: "Fall 2024" },
      { id: 4, name: "Sam Rivera", email: "sam@test.com", password: "test123", role: "member", pledgeClass: "Spring 2025" },
      { id: 5, name: "Taylor Brooks", email: "taylor@test.com", password: "test123", role: "member", pledgeClass: "Spring 2025" },
      { id: 6, name: "Morgan Diaz", email: "morgan@test.com", password: "test123", role: "member", pledgeClass: "Fall 2025" },
    ],
    grades: [
      { userId: 2, term: "Spring 2026", gpa: 3.62, creditHours: 15, submittedAt: "2026-05-20T12:00:00" },
      { userId: 3, term: "Spring 2026", gpa: 2.31, creditHours: 12, submittedAt: "2026-05-22T12:00:00" },
      { userId: 4, term: "Spring 2026", gpa: 3.05, creditHours: 16, submittedAt: "2026-05-19T12:00:00" },
      { userId: 5, term: "Spring 2026", gpa: 3.88, creditHours: 14, submittedAt: "2026-05-21T12:00:00" },
      { userId: 2, term: "Fall 2026", gpa: 3.4, creditHours: 15, submittedAt: "2026-10-10T12:00:00" },
      { userId: 4, term: "Fall 2026", gpa: 2.45, creditHours: 13, submittedAt: "2026-10-12T12:00:00" },
    ],
  };
}

function loadDb() {
  const raw = localStorage.getItem(DB_KEY);
  if (raw) {
    return JSON.parse(raw);
  }
  const db = seedDb();
  saveDb(db);
  return db;
}

function saveDb(db) {
  localStorage.setItem(DB_KEY, JSON.stringify(db));
}

function resetDemoData() {
  localStorage.removeItem(DB_KEY);
  localStorage.removeItem(SESSION_KEY);
}

// strip the password before handing a user to the page
function publicUser(user) {
  return { id: user.id, name: user.name, email: user.email, role: user.role, pledgeClass: user.pledgeClass };
}

function currentUser() {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) {
    return null;
  }
  return JSON.parse(raw);
}

function logout() {
  localStorage.removeItem(SESSION_KEY);
}

function register(name, email, password, pledgeClass) {
  const db = loadDb();
  email = email.trim().toLowerCase();
  if (db.users.some((u) => u.email === email)) {
    throw new Error("An account with that email already exists.");
  }
  // everyone who registers is a member
  const user = { id: db.nextUserId, name: name.trim(), email, password, role: "member", pledgeClass };
  db.nextUserId += 1;
  db.users.push(user);
  saveDb(db);
  localStorage.setItem(SESSION_KEY, JSON.stringify(publicUser(user)));
  return publicUser(user);
}

function login(email, password) {
  const db = loadDb();
  email = email.trim().toLowerCase();
  const user = db.users.find((u) => u.email === email && u.password === password);
  if (!user) {
    throw new Error("Wrong email or password.");
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(publicUser(user)));
  return publicUser(user);
}

function submitGrade(term, gpa, creditHours) {
  const user = currentUser();
  if (!user) {
    throw new Error("You need to log in first.");
  }
  if (!term.trim()) {
    throw new Error("Pick a term.");
  }
  if (isNaN(gpa) || gpa < 0 || gpa > 4) {
    throw new Error("GPA must be between 0.0 and 4.0.");
  }
  if (!Number.isInteger(creditHours) || creditHours <= 0) {
    throw new Error("Credit hours must be a whole number above 0.");
  }

  const db = loadDb();
  // one submission per member per term, so a resubmit replaces the old one
  db.grades = db.grades.filter((g) => !(g.userId === user.id && g.term === term));
  db.grades.push({ userId: user.id, term, gpa, creditHours, submittedAt: new Date().toISOString() });
  saveDb(db);
}

function getTerms() {
  const db = loadDb();
  return [...new Set(db.grades.map((g) => g.term))].sort(compareTerms);
}

function getPledgeClasses() {
  const db = loadDb();
  const classes = db.users.filter((u) => u.role === "member").map((u) => u.pledgeClass);
  return [...new Set(classes)].filter((c) => c).sort(compareTerms);
}

// newest term first, "Fall 2026" comes before "Spring 2026"
function compareTerms(a, b) {
  const order = { Spring: 1, Summer: 2, Fall: 3 };
  const [seasonA, yearA] = a.split(" ");
  const [seasonB, yearB] = b.split(" ");
  if (yearA !== yearB) {
    return Number(yearB) - Number(yearA);
  }
  return (order[seasonB] || 0) - (order[seasonA] || 0);
}

// filters: term, pledgeClass, maxGpa, submitted ("yes" / "no" / ""), sort ("name" / "gpa")
function getMembers(filters) {
  const user = currentUser();
  if (!user || user.role !== "chair") {
    throw new Error("Only the chair can see this.");
  }

  const db = loadDb();
  let rows = db.users
    .filter((u) => u.role === "member")
    .map((u) => {
      const grade = db.grades.find((g) => g.userId === u.id && g.term === filters.term);
      const row = { name: u.name, email: u.email, pledgeClass: u.pledgeClass, term: filters.term, gpa: null, creditHours: null, submittedAt: null };
      if (grade) {
        row.gpa = grade.gpa;
        row.creditHours = grade.creditHours;
        row.submittedAt = grade.submittedAt;
      }
      return row;
    });

  if (filters.pledgeClass) {
    rows = rows.filter((r) => r.pledgeClass === filters.pledgeClass);
  }
  if (filters.submitted === "yes") {
    rows = rows.filter((r) => r.gpa !== null);
  }
  if (filters.submitted === "no") {
    rows = rows.filter((r) => r.gpa === null);
  }
  if (filters.maxGpa !== "" && filters.maxGpa !== undefined) {
    rows = rows.filter((r) => r.gpa !== null && r.gpa <= Number(filters.maxGpa));
  }

  if (filters.sort === "gpa") {
    // lowest gpa first, missing ones at the bottom
    rows.sort((a, b) => {
      if (a.gpa === null) return 1;
      if (b.gpa === null) return -1;
      return a.gpa - b.gpa;
    });
  } else {
    rows.sort((a, b) => a.name.localeCompare(b.name));
  }

  return rows;
}
