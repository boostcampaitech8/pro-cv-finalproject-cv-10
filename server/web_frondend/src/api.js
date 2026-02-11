export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function fetchEvents(limit = 50) {
  const res = await fetch(`${API_BASE}/events?limit=${limit}`);
  if (!res.ok) throw new Error("failed to fetch events");
  return await res.json();
}

export async function fetchEventDetail(eventId) {
  const res = await fetch(`${API_BASE}/events/${eventId}`);
  if (!res.ok) throw new Error("failed to fetch event detail");
  return await res.json();
}

export async function fetchClientStatus() {
  const res = await fetch(`${API_BASE}/client_status`);
  if (!res.ok) throw new Error("failed to fetch client_status");
  return await res.json();
}


export async function fetchHistoryEvents({ start, end, clientId = "ALL", limit = 200 }) {
  const params = new URLSearchParams();

  if (start) params.set("start", start);
  if (end) params.set("end", end);
  params.set("limit", String(limit));

  if (clientId && clientId !== "ALL") {
    params.set("client_id", clientId);
  }

  const res = await fetch(`${API_BASE}/events/history?${params.toString()}`);
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`failed to fetch history events: ${res.status} ${txt}`);
  }
  return await res.json();
}

export function makeEventSource() {
  return new EventSource(`${API_BASE}/stream`);
}
