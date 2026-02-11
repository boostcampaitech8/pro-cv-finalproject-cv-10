import React from "react";

function fmtTime(t) {
  try {
    return new Date(t).toLocaleString();
  } catch {
    return t;
  }
}

function StatusDot({ status }) {
  // status: true(alive) / false(dead) / null(unknown)
  const color = status === true ? "#22c55e" : status === false ? "#ef4444" : "#9ca3af";
  const label = status === true ? "alive" : status === false ? "dead" : "unknown";

  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: 999,
        marginRight: 8,
        background: color,
      }}
      title={label}
    />
  );
}

function NewDot({ show }) {
  if (!show) return null;
  return (
    <span
      title="new events"
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: 999,
        background: "#2563eb",
        marginLeft: 8,
      }}
    />
  );
}

export default function DeviceList({
  devices,
  selectedClientId,
  onSelect,
  unseenByClient, // { [client_id]: number }
}) {
  const sorted = [...(devices || [])].sort((a, b) => {
    const rank = (st) => (st === false ? 0 : st === null ? 1 : 2);
    const ra = rank(typeof a?.status === "boolean" ? a.status : null);
    const rb = rank(typeof b?.status === "boolean" ? b.status : null);
    if (ra !== rb) return ra - rb;

    const ta = new Date(a?.updated_at || 0).getTime();
    const tb = new Date(b?.updated_at || 0).getTime();
    return tb - ta;
  });

  const totalUnseen =
    unseenByClient &&
    Object.values(unseenByClient).some((v) => v > 0);

  return (
    <div style={{ borderRight: "1px solid #ddd", padding: 12, overflow: "auto" }}>
      <h2 style={{ marginTop: 0 }}>
        📷 CCTV{" "}
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
          {sorted.length}
        </span>
      </h2>

      {/* ALL: new dot만 표시 */}
      <div
        onClick={() => onSelect("ALL")}
        style={{
          border: "1px solid #ddd",
          borderRadius: 10,
          padding: 10,
          cursor: "pointer",
          background: selectedClientId === "ALL" ? "#f4f6ff" : "white",
          display: "flex",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <StatusDot status={null} />
        <div style={{ fontWeight: 800 }}>
          ALL
          <NewDot show={totalUnseen} />
        </div>
      </div>

      {sorted.map((d) => {
        const cid = d?.client_id || "(unknown)";
        const st = typeof d?.status === "boolean" ? d.status : null;
        const unseen = unseenByClient?.[cid] || 0;

        return (
          <div
            key={cid}
            onClick={() => onSelect(cid)}
            style={{
              border: "1px solid #ddd",
              borderRadius: 10,
              padding: 10,
              marginBottom: 8,
              cursor: "pointer",
              background: selectedClientId === cid ? "#f4f6ff" : "white",
            }}
          >
            <div style={{ display: "flex", alignItems: "center" }}>
              <StatusDot status={st} />
              <div style={{ fontWeight: 800 }}>
                {cid}
                <NewDot show={unseen > 0} />
              </div>
              {st === null ? (
                <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.7 }}>
                  (unknown)
                </span>
              ) : null}
            </div>

            <div style={{ fontSize: 12, opacity: 0.7, marginTop: 6 }}>
              last ping · {d?.updated_at ? fmtTime(d.updated_at) : "-"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
