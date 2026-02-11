// src/components/EventDetail.jsx
import React from "react";
import { API_BASE } from "../api";

function fmtTime(t) {
  try {
    return new Date(t).toLocaleString();
  } catch {
    return t;
  }
}

function fmtBBox(bbox) {
  if (!Array.isArray(bbox) || bbox.length !== 4) return "-";
  const [x, y, w, h] = bbox;
  return `x=${x}, y=${y}, w=${w}, h=${h}`;
}


function captureTime(event) {
  const mt = event?.metadata?.time;
  if (typeof mt === "number" && Number.isFinite(mt)) {
    return fmtTime(mt * 1000);
  }
  return fmtTime(event?.timestamp);
}


const CLASS_META = {
  0: { name: "어선" },
  1: { name: "상선" },
  2: { name: "군함" },
  3: { name: "사람" },
  4: { name: "유조류" },
  5: { name: "선박" },
};

const CLASS_COLOR_PALETTE = [
  "#ff3b30",
  "#ff9500",
  "#ffcc00",
  "#34c759",
  "#00c7be",
  "#007aff",
  "#5856d6",
  "#af52de",
  "#ff2d55",
  "#8e8e93",
  "#a2845e",
  "#30b0c7",
];

function colorForClassId(classId) {
  if (classId === undefined || classId === null || classId === "") return "#ff3b30";
  const n = Number(classId);
  if (Number.isFinite(n)) return CLASS_COLOR_PALETTE[Math.abs(n) % CLASS_COLOR_PALETTE.length];

  const s = String(classId);
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return CLASS_COLOR_PALETTE[h % CLASS_COLOR_PALETTE.length];
}

function isDark(hex) {
  const c = (hex || "").replace("#", "");
  if (c.length !== 6) return false;
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum < 140;
}

function classLabel(classId) {
  const meta = CLASS_META?.[classId];
  if (meta?.name) return `${meta.emoji ? meta.emoji + " " : ""}${meta.name}`;
  return `Class ${classId}`;
}

function confText(x) {
  if (typeof x !== "number" || !Number.isFinite(x)) return "-";
  return x.toFixed(2);
}

function clamp01(x) {
  if (typeof x !== "number" || !Number.isFinite(x)) return 0;
  return Math.max(0, Math.min(1, x));
}

function Row({ label, value }) {
  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 8, fontSize: 13 }}>
      <div style={{ width: 120, opacity: 0.65 }}>{label}</div>
      <div style={{ flex: 1, wordBreak: "break-word" }}>{value ?? "-"}</div>
    </div>
  );
}


function safeParseReport(reportRaw) {
  if (!reportRaw) return { rawText: null, json: null };
  if (typeof reportRaw === "object") return { rawText: JSON.stringify(reportRaw, null, 2), json: reportRaw };

  const s = String(reportRaw).trim();
  if (!s) return { rawText: null, json: null };

  // JSON string이면 파싱
  try {
    const obj = JSON.parse(s);
    return { rawText: JSON.stringify(obj, null, 2), json: obj };
  } catch {
    return { rawText: s, json: null };
  }
}

function weatherTextFromCode(v) {

  if (v === null || v === undefined) return null;
  if (typeof v === "number") {
    const m = {
      0: "맑음(코드 0)",
      1: "흐림(코드 1)",
      2: "비(코드 2)",
      3: "눈(코드 3)",
      4: "안개/연무(코드 4)",
    };
    return m[v] ?? `weather=${v}`;
  }
  return String(v);
}

function buildControlReport({ event, caption, reportRaw, annotations }) {
  const clientId = event?.client_id ?? "-";
  const loc = event?.location_name ?? "-";
  const t = captureTime(event);

  const meta = event?.metadata ?? {};
  const lat = meta?.latitude;
  const lon = meta?.longitude;
  const weatherCode = weatherTextFromCode(meta?.weather);

  const parsed = safeParseReport(reportRaw);
  const weatherDesc = parsed?.json?.weather?.description ?? null;
  const detectedDesc = parsed?.json?.detected_object?.description ?? null;

  const count = Array.isArray(annotations) ? annotations.length : 0;

  const top = (Array.isArray(annotations) ? annotations : [])
    .slice()
    .sort((a, b) => (b?.confidence ?? 0) - (a?.confidence ?? 0))
    .slice(0, 5)
    .map((a) => `${classLabel(a?.class)}(${confText(a?.confidence)})`)
    .join(", ");

  // 본문(캡션/리포트 섞기)
  const lines = [];
  lines.push(`관제 보고서`);
  lines.push(`- 시각: ${t}`);
  lines.push(`- 대상: ${clientId}`);
  lines.push(`- 위치: ${loc ?? "-"}, ${lat ?? "-"}, ${lon ?? "-"}`);
  lines.push(`- 날씨: ${weatherDesc ?? weatherCode ?? "-"}`);
  lines.push(`- 탐지: ${count}개`);
  lines.push("");

  lines.push("상황 요약:");

  const parts = [];
  if (detectedDesc) parts.push(String(detectedDesc).trim());
  if (caption) parts.push(String(caption).trim());

  if (parts.length === 0 && parsed?.rawText) parts.push(String(parsed.rawText).trim());

  const merged = parts
    .filter(Boolean)
    .join(" ");

  lines.push(merged ? `- ${merged}` : "- -");

  lines.push("");
  lines.push("권장 조치:");
  if (count > 0) {
    lines.push("- 탐지 객체가 존재합니다. 이미지/박스 위치를 확인하고 필요 시 추가 확인(재촬영/확대) 또는 현장 대응을 진행하세요.");
  } else {
    lines.push("- 현재 탐지된 객체가 없습니다. 추적 관찰을 지속하세요.");
  }

  return lines.join("\n");
}


function BBoxesOverlay({ annotations, natural, display, selectedIdx, onSelect }) {
  if (!Array.isArray(annotations) || annotations.length === 0) return null;

  const { nw, nh } = natural || {};
  const { dw, dh } = display || {};
  if (!nw || !nh || !dw || !dh) return null;

  const sx = dw / nw;
  const sy = dh / nh;

  return (
    <>
      {annotations.map((a, idx) => {
        const bbox = a?.bbox;
        if (!Array.isArray(bbox) || bbox.length !== 4) return null;
        const [x, y, w, h] = bbox;

        const classId = a?.class;
        const color = colorForClassId(classId);
        const selected = idx === selectedIdx;

        const label = `${classLabel(classId)} · ${confText(a?.confidence)}`;

        return (
          <div
            key={idx}
            onMouseEnter={() => onSelect?.(idx)}
            onClick={() => onSelect?.(idx)}
            style={{
              position: "absolute",
              left: x * sx,
              top: y * sy,
              width: w * sx,
              height: h * sy,
              border: selected ? `3px solid ${color}` : `2px solid ${color}`,
              borderRadius: 8,
              boxSizing: "border-box",
              pointerEvents: "auto",
              cursor: "pointer",
              boxShadow: selected ? `0 0 0 4px ${color}22` : "none",
              background: selected ? `${color}10` : "transparent",
            }}
          >
            <div
              style={{
                position: "absolute",
                left: 6,
                top: -22,
                padding: "3px 8px",
                fontSize: 12,
                fontWeight: 700,
                borderRadius: 999,
                background: color,
                color: isDark(color) ? "white" : "black",
                whiteSpace: "nowrap",
                boxShadow: "0 8px 18px rgba(0,0,0,0.18)",
              }}
            >
              {label}
            </div>
          </div>
        );
      })}
    </>
  );
}

export default function EventDetail({ event }) {
  if (!event) return <div style={{ padding: 16, opacity: 0.7 }}>이벤트를 선택하세요.</div>;

  const clientId = event?.client_id ?? "-";
  const loc = event?.location_name ?? "-";

  const caption = event?.caption ?? event?.file?.caption ?? null;
  const reportRaw = event?.report ?? event?.file?.report ?? null;

  const meta = event?.metadata ?? {};
  const lat = meta?.latitude;
  const lon = meta?.longitude;
  const weather = meta?.weather;

  const annotations = Array.isArray(meta?.annotations) ? meta.annotations : [];

  const imgRef = React.useRef(null);
  const [natural, setNatural] = React.useState({ nw: 0, nh: 0 });
  const [display, setDisplay] = React.useState({ dw: 0, dh: 0 });

  const [selectedIdx, setSelectedIdx] = React.useState(null);

  const [showReport, setShowReport] = React.useState(false);
  const [generatedText, setGeneratedText] = React.useState("");

  React.useEffect(() => {
    setSelectedIdx(null);
    setShowReport(false);
    setGeneratedText("");
  }, [event?.event_id]);

  React.useEffect(() => {
    const el = imgRef.current;
    if (!el) return;

    const update = () => {
      setDisplay({ dw: el.clientWidth || 0, dh: el.clientHeight || 0 });
    };

    update();

    let ro = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => update());
      ro.observe(el);
    } else {
      window.addEventListener("resize", update);
    }

    return () => {
      if (ro) ro.disconnect();
      else window.removeEventListener("resize", update);
    };
  }, [event?.image_url]);

  const imgUrl = event?.image_url ? `${API_BASE}${event.image_url}` : null;

  const onGenerate = () => {
    const text = buildControlReport({ event, caption, reportRaw, annotations });
    setGeneratedText(text);
    setShowReport(true);
  };

  return (
    <div style={{ padding: 16, overflow: "auto", position: "relative" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
        <h2 style={{ marginTop: 0, marginBottom: 6 }}>📌 Detail</h2>
        <div style={{ fontSize: 12, opacity: 0.65 }}>
          {clientId} · {loc}
        </div>
      </div>

      <div style={{ fontSize: 13, marginBottom: 12 }}>
        <b>Captured</b>: {captureTime(event)}
      </div>

      {/* 이미지 sticky */}
      {imgUrl ? (
        <div
          style={{
            position: "sticky",
            top: 0,
            zIndex: 20,
            background: "white",
            paddingTop: 6,
            paddingBottom: 12,
            borderBottom: "1px solid rgba(0,0,0,0.06)",
          }}
        >
          <div style={{ position: "relative", width: "100%" }}>
            <img
              ref={imgRef}
              src={imgUrl}
              alt="event"
              style={{
                width: "100%",
                borderRadius: 16,
                border: "1px solid rgba(0,0,0,0.10)",
                display: "block",
                boxShadow: "0 14px 28px rgba(0,0,0,0.12)",
              }}
              onLoad={(e) => {
                const img = e.currentTarget;
                setNatural({ nw: img.naturalWidth, nh: img.naturalHeight });
                setDisplay({ dw: img.clientWidth, dh: img.clientHeight });
              }}
            />

            <BBoxesOverlay
              annotations={annotations}
              natural={natural}
              display={display}
              selectedIdx={selectedIdx}
              onSelect={(idx) => setSelectedIdx(idx)}
            />
          </div>
        </div>
      ) : (
        <div style={{ padding: 20, border: "1px dashed #999", borderRadius: 16 }}>이미지 없음</div>
      )}

      {/* 아래 영역 */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 14 }}>
        {/* Detections */}
        <div
          style={{
            border: "1px solid rgba(0,0,0,0.10)",
            borderRadius: 16,
            padding: 14,
            flex: "2 1 520px",
            boxShadow: "0 10px 22px rgba(0,0,0,0.06)",
            background: "white",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
            <h3 style={{ marginTop: 0, marginBottom: 12 }}>Detections</h3>
          </div>

          {annotations.length === 0 ? (
            <div style={{ opacity: 0.7 }}>annotations 없음</div>
          ) : (
            annotations.map((a, idx) => {
              const cid = a?.class;
              const color = colorForClassId(cid);
              const selected = idx === selectedIdx;

              const conf = clamp01(a?.confidence);
              const title = classLabel(cid);

              return (
                <div
                  key={idx}
                  onMouseEnter={() => setSelectedIdx(idx)}
                  onClick={() => setSelectedIdx(idx)}
                  style={{
                    border: selected ? `2px solid ${color}` : "1px solid rgba(0,0,0,0.08)",
                    borderRadius: 14,
                    padding: 12,
                    marginBottom: 10,
                    fontSize: 13,
                    cursor: "pointer",
                    boxShadow: selected ? `0 10px 20px ${color}22` : "none",
                    background: selected ? `${color}0F` : "white",
                    transition: "all 120ms ease",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                    <div
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 99,
                        background: color,
                        boxShadow: `0 0 0 3px ${color}22`,
                      }}
                    />
                    <div style={{ fontWeight: 900, color }}>{title}</div>
                    <div style={{ marginLeft: "auto", fontSize: 12, opacity: 0.7 }}>
                      #{idx} · conf {confText(a?.confidence)}
                    </div>
                  </div>

                  <div
                    style={{
                      height: 8,
                      borderRadius: 999,
                      background: "rgba(0,0,0,0.06)",
                      overflow: "hidden",
                      marginBottom: 10,
                    }}
                  >
                    <div
                      style={{
                        width: `${Math.round(conf * 100)}%`,
                        height: "100%",
                        background: color,
                        opacity: 0.85,
                      }}
                    />
                  </div>

                  <Row label="Class ID" value={<span style={{ fontWeight: 800 }}>{cid ?? "-"}</span>} />
                  <Row label="BBox" value={fmtBBox(a?.bbox)} />
                </div>
              );
            })
          )}
        </div>

        {/* Summary + Report(아래) */}
        <div
          style={{
            border: "1px solid rgba(0,0,0,0.10)",
            borderRadius: 16,
            padding: 14,
            flex: "1 1 320px",
            boxShadow: "0 10px 22px rgba(0,0,0,0.06)",
            background: "white",
          }}
        >
          <h3 style={{ marginTop: 0, marginBottom: 12 }}>Summary</h3>

          <Row label="Client" value={<b>{clientId}</b>} />
          <Row label="Location" value={<b>{loc}</b>} />
          <Row label="Captured" value={<b>{captureTime(event)}</b>} />
          <Row label="Detected" value={<b>{annotations.length}</b>} />
          <Row label="Latitude" value={lat ?? "-"} />
          <Row label="Longitude" value={lon ?? "-"} />
          <Row label="Weather" value={weatherTextFromCode(weather) ?? "-"} />

          {/*  Report 섹션 */}
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ fontWeight: 900 }}>Report</div>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={onGenerate}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 12,
                    border: "1px solid rgba(0,0,0,0.12)",
                    background: "white",
                    cursor: "pointer",
                    fontWeight: 900,
                  }}
                  title="관제용 보고서 생성"
                >
                  보고서 생성
                </button>

                <button
                  onClick={() => setShowReport((v) => !v)}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 12,
                    border: "1px solid rgba(0,0,0,0.12)",
                    background: "white",
                    cursor: "pointer",
                    fontWeight: 900,
                    opacity: 0.9,
                  }}
                  disabled={!generatedText}
                  title={!generatedText ? "'보고서 생성'을 눌러주세요" : "펼치기/접기"}
                >
                  {showReport ? "접기" : "펼치기"}
                </button>
              </div>
            </div>

            {!generatedText ? (
              <div style={{ marginTop: 10, fontSize: 12, opacity: 0.7, lineHeight: 1.4 }}>
                [보고서 생성]을 누르면 관제 상황 요약 글이 생성됩니다.
              </div>
            ) : null}

            {showReport && generatedText ? (
              <pre
                style={{
                  marginTop: 10,
                  marginBottom: 0,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontSize: 12,
                  lineHeight: 1.45,
                  opacity: 0.95,
                  background: "rgba(0,0,0,0.04)",
                  padding: 10,
                  borderRadius: 12,
                }}
              >
                {generatedText}
              </pre>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
