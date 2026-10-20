// calls to the fastapi backend

const API_BASE = "http://localhost:8000";
const TOKEN_KEY = "gs_token";
const USER_KEY = "gs_user";

// sessionStorage keeps each tab logged in on its own, so logging in somewhere
// else never changes which account another tab is using

// turn fastapi error bodies into one readable message
function errorMessage(body, status) {
  if (body && typeof body.detail === "string") {
    return body.detail;
  }
  if (body && Array.isArray(body.detail) && body.detail.length > 0) {
    const first = body.detail[0];
    const field = first.loc[first.loc.length - 1];
    return field + ": " + first.msg;
  }
  return "Something went wrong (" + status + ")";
}

async function request(method, path, body) {
  const headers = {};
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) {
    headers["Authorization"] = "Bearer " + token;
  }

  const options = { method, headers };
  if (body instanceof URLSearchParams) {
    options.body = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(API_BASE + path, options);
  } catch (err) {
    throw new Error("Can't reach the server. Is the backend running on port 8000?");
  }

  let data = null;
  const text = await res.text();
  if (text) {
    // a server crash sends plain text, not json
    try {
      data = JSON.parse(text);
    } catch (err) {
      data = null;
    }
  }

  // expired or bad token, send them back to log in
  if (res.status === 401 && path !== "/login") {
    logout();
    window.location.href = "index.html";
  }
  if (!res.ok) {
    throw new Error(errorMessage(data, res.status));
  }
  return data;
}

function saveSession(data) {
  sessionStorage.setItem(TOKEN_KEY, data.access_token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(data.user));
  return data.user;
}

function currentUser() {
  const raw = sessionStorage.getItem(USER_KEY);
  if (!raw || !sessionStorage.getItem(TOKEN_KEY)) {
    return null;
  }
  return JSON.parse(raw);
}

function logout() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

function query(params) {
  const q = new URLSearchParams();
  Object.keys(params).forEach((key) => {
    if (params[key] !== "" && params[key] !== null && params[key] !== undefined) {
      q.append(key, params[key]);
    }
  });
  const s = q.toString();
  if (!s) {
    return "";
  }
  return "?" + s;
}

// auth

async function login(email, password) {
  const form = new URLSearchParams({ username: email, password });
  return saveSession(await request("POST", "/login", form));
}

async function register(name, email, password, pledgeClass) {
  return saveSession(await request("POST", "/register", { name, email, password, pledge_class: pledgeClass }));
}

// shared

const getCurrentTerm = () => request("GET", "/terms/current");
const getWeeks = () => request("GET", "/weeks");
const getGradeScale = () => request("GET", "/settings/grade-scale");

// member

const getCourses = (includeDropped) => request("GET", "/courses" + query({ include_dropped: includeDropped }));
const addCourse = (code, name, credits) => request("POST", "/courses", { code, name, credits });
const dropCourse = (id) => request("DELETE", "/courses/" + id);
const getWeekCourses = (weekId) => request("GET", "/weeks/" + weekId + "/courses");
const submitWeek = (weekId, grades) => request("POST", "/submissions", { week_id: weekId, grades });
const getMyHistory = () => request("GET", "/submissions/me");

// chair

const getMembers = (filters) => request("GET", "/members" + query(filters));
const getMemberHistory = (id) => request("GET", "/members/" + id + "/history");
const getWeeklyStats = () => request("GET", "/stats/weekly");
const getPledgeClasses = () => request("GET", "/pledge-classes");
const getFlagRules = () => request("GET", "/settings/flags");
const saveFlagRules = (rules) => request("PUT", "/settings/flags", rules);
const saveGradeScale = (rows) => request("PUT", "/settings/grade-scale", rows);
const createTerm = (term) => request("POST", "/terms", term);

// chair management, always done as the chair on the member's data

const muteFlag = (userId, weekId, kind, courseId, reason) =>
  request("POST", "/members/" + userId + "/weeks/" + weekId + "/mutes", { kind, course_id: courseId, reason });
const unmuteFlag = (muteId) => request("DELETE", "/mutes/" + muteId);
const correctGrade = (userId, weekId, courseId, percent, reason) =>
  request("PUT", "/members/" + userId + "/weeks/" + weekId + "/grades/" + courseId, { percent, reason });
const getNotes = (userId) => request("GET", "/members/" + userId + "/notes");
const addNote = (userId, text, weekId) => request("POST", "/members/" + userId + "/notes", { text, week_id: weekId });
const editNote = (noteId, text, weekId) => request("PUT", "/notes/" + noteId, { text, week_id: weekId });
const deleteNote = (noteId) => request("DELETE", "/notes/" + noteId);
const editMember = (userId, changes) => request("PATCH", "/members/" + userId, changes);
const deactivateMember = (userId, reason) => request("POST", "/members/" + userId + "/deactivate", { reason });
const reactivateMember = (userId, reason) => request("POST", "/members/" + userId + "/reactivate", { reason });
const deleteMember = (userId, confirmName, reason) => request("DELETE", "/members/" + userId, { confirm_name: confirmName, reason });
const getMemberLog = (userId) => request("GET", "/members/" + userId + "/log");
