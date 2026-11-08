// All calls to the backend. Vite forwards /api to FastAPI in development, and in
// production FastAPI serves both the page and the API from one address.

const UNREACHABLE = "The court can't be reached. Check your connection, then try again.";
const FAILED = "Something went wrong. Please try again.";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status; // 0 means the request never got an answer
  }
}

async function request(path, { method = "GET", body, seatToken } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // The secret this device was given when it claimed its seat.
  if (seatToken) headers["X-Seat-Token"] = seatToken;

  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = typeof payload?.detail === "string" ? payload.detail : FAILED;
    throw new ApiError(detail, response.status);
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  session: () => request("/session"),
  login: (passcode) => request("/login", { method: "POST", body: { passcode } }),
  createCase: () => request("/cases", { method: "POST" }),
  getCase: (id) => request(`/cases/${id}`),
  claimSeat: (id, person) => request(`/cases/${id}/seats`, { method: "POST", body: { person } }),
  // route is "statements" or "answers".
  submit: (id, route, person, text, seatToken) =>
    request(`/cases/${id}/${route}`, { method: "POST", body: { person, text }, seatToken }),
  retry: (id, seatToken) => request(`/cases/${id}/retry`, { method: "POST", seatToken }),
  endCase: (id, seatToken) => request(`/cases/${id}`, { method: "DELETE", seatToken }),
};
