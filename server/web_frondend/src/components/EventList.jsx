// src/components/EventList.jsx
import React, { useMemo, useState } from "react";

function fmtTime(t) {
  try {
    return new Date(t).toLocaleString();
  } catch {
    return t;
  }
}

function detectCount(e) {
  const anns = e?.metadata?.annotations;
  return Array.isArray(anns) ? anns.length : 0;
}


function captureTime(e) {
  const mt = e?.metadata?.time;

  if (mt !== undefined && mt !== null) {
    const n = typeof mt === "string" ? Number(mt) : mt;
    if (typeof n === "number" && Number.isFinite(n)) {
      const ms = n > 1e12 ? n : n * 1000;
      return fmtTime(ms);
    }
  }

  const ct = e?.captured_time ?? e?.capture_time ?? e?.metadata?.captured_time;
  if (ct) return fmtTime(ct);

  return fmtTime(e?.timestamp);
}

function EventCard({ e, active, onClick, badge }) {
  const id = e?.event_id;
  const clientId = e?.client_id ?? "-";
  const loc = e?.location_name ?? "-";
  const cnt = detectCount(e);

  return (
    <div
      key={id}
      onClick={onClick}
      style={{
        border: "1px solid #ddd",
        borderRadius: 10,
        padding: 10,
        marginBottom: 8,
        cursor: "pointer",
        background: active ? "#f4f6ff" : "white",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ fontWeight: 800 }}>
          {clientId} <span style={{ fontWeight: 600, opacity: 0.7 }}>· {loc}</span>
        </div>
        {badge ? (
          <span
            style={{
              fontSize: 11,
              padding: "2px 8px",
              borderRadius: 999,
              border: "1px solid #ddd",
              opacity: 0.85,
            }}
          >
            {badge}
          </span>
        ) : null}
      </div>

      {/* ✅ FIX: EventDetail과 같은 "촬영 시각" 표시 */}
      <div style={{ fontSize: 12, opacity: 0.7, marginTop: 4 }}>{captureTime(e)}</div>

      <div style={{ fontSize: 12, marginTop: 6 }}>
        detected: <b>{cnt}</b>
      </div>

      {e?.__virtual ? (
        <div style={{ fontSize: 12, marginTop: 6, opacity: 0.65 }}>(virtual from files)</div>
      ) : null}
    </div>
  );
}

export default function EventList({
  events,
  historyEvents,
  selectedId,
  onSelect,
  onSelectHistory, 
  unseenCount,
  onSearchHistory,
  onClearHistory,
}) {
  const [historyOpen, setHistoryOpen] = useState(false);

  const [from, setFrom] = useState(""); // "YYYY-MM-DD"
  const [to, setTo] = useState(""); // "YYYY-MM-DD"

  const merged = useMemo(() => {
    return {
      live: events || [],
      history: historyEvents || [],
    };
  }, [events, historyEvents]);

  const hasHistory = merged.history.length > 0;

  return (
    <div
      style={{
        borderRight: "1px solid #ddd",
        padding: 12,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <h2 style={{ marginTop: 0, marginBottom: 10 }}>
        🚨 Events{" "}
        <span
          style={{
            display: "inline-block",
            marginLeft: 8,
            padding: "2px 8px",
            border: "1px solid #ddd",
            borderRadius: 999,
            fontSize: 12,
          }}
        >
          {unseenCount}
        </span>
      </h2>

      {/* LIVE만 스크롤 */}
      <div style={{ flex: 1, overflow: "auto", paddingRight: 4 }}>
        {merged.live.map((e) => (
          <EventCard
            key={e.event_id}
            e={e}
            active={e.event_id === selectedId}
            onClick={() => onSelect(e.event_id)}
          />
        ))}
      </div>

      {/* HISTORY는 하단 고정 */}
      <div
        style={{
          marginTop: 12,
          borderTop: "1px dashed #ddd",
          paddingTop: 10,
          background: "white",
          position: "sticky",
          bottom: 0,
        }}
      >
        <div
          style={{
            cursor: "pointer",
            fontWeight: 800,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
          onClick={() => setHistoryOpen((v) => !v)}
        >
          <div>🕒 History {historyOpen ? "▲" : "▼"}</div>
          {hasHistory ? (
            <span style={{ fontSize: 12, opacity: 0.7 }}>{merged.history.length} results</span>
          ) : (
            <span style={{ fontSize: 12, opacity: 0.6 }}>검색 결과 없음</span>
          )}
        </div>

        {historyOpen ? (
          <>
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={{ flex: 1 }} />
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={{ flex: 1 }} />
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button
                onClick={() => onSearchHistory({ start: from, end: to })}
                style={{ padding: "6px 10px", cursor: "pointer" }}
                disabled={!from || !to}
                title={!from || !to ? "from/to 날짜를 채워주세요" : "조회"}
              >
                조회
              </button>

              <button
                onClick={() => {
                  setFrom("");
                  setTo("");
                  onClearHistory?.();
                }}
                style={{ padding: "6px 10px", cursor: "pointer", opacity: 0.8 }}
              >
                초기화
              </button>
            </div>

            <div style={{ marginTop: 10, maxHeight: 260, overflow: "auto", paddingRight: 4 }}>
              {merged.history.map((e) => (
                <EventCard
                  key={`h-${e.event_id}`}
                  e={e}
                  active={e.event_id === selectedId}
                  onClick={() => (onSelectHistory ? onSelectHistory(e) : onSelect(e.event_id))}
                  badge="history"
                />
              ))}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
