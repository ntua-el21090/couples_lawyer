// Remembers which seat this device claimed in a case, so a reload doesn't lose it.
// Browser storage can be blocked, so every call is guarded and the page still works
// for as long as it stays open.

const key = (caseId) => `lot-seat:${caseId}`;

export function loadSeat(caseId) {
  try {
    const seat = JSON.parse(localStorage.getItem(key(caseId)));
    return seat && typeof seat.token === "string" && (seat.person === "boy" || seat.person === "girl")
      ? seat
      : null;
  } catch {
    return null;
  }
}

export function saveSeat(caseId, seat) {
  try {
    localStorage.setItem(key(caseId), JSON.stringify(seat));
  } catch {
    // Not remembered across reloads. Nothing else to do.
  }
}

export function forgetSeat(caseId) {
  try {
    localStorage.removeItem(key(caseId));
  } catch {
    // Same as above.
  }
}
