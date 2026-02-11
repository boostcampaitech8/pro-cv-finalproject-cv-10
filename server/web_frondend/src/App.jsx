// src/App.jsx
import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  fetchEvents,
  fetchEventDetail,
  fetchHistoryEvents,
  fetchClientStatus,
  makeEventSource,
} from "./api";

import DeviceList from "./components/DeviceList";
import EventList from "./components/EventList";
import EventDetail from "./components/EventDetail";
import Toast from "./components/Toast";

export default function App() {
  // 전체 이벤트(실시간)
  const [events, setEvents] = useState([]);
  // 히스토리 검색 결과(전체)
  const [historyEvents, setHistoryEvents] = useState([]);

  // 디바이스 상태
  const [devices, setDevices] = useState([]);

  // 선택 상태
  const [selectedClientId, setSelectedClientId] = useState("ALL");
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);

  const [selectedSource, setSelectedSource] = useState("live"); // 'live' | 'history'

  // unseen 표시 (DeviceList 파란점)
  const [unseenByClient, setUnseenByClient] = useState({}); // { [client_id]: number }

  // UI
  const [toast, setToast] = useState("");

  const unseenCount = useMemo(() => {
    return Object.values(unseenByClient || {}).reduce((a, b) => a + (b || 0), 0);
  }, [unseenByClient]);


  const refreshList = useCallback(async () => {
    const data = await fetchEvents(50);
    setEvents(data);

    if (!selectedId && data.length) setSelectedId(data[0].event_id);
  }, [selectedId]);

  const refreshDevices = useCallback(async () => {
    const data = await fetchClientStatus();
    setDevices(data || []);
  }, []);

  const loadDetail = useCallback(async (eventId) => {
    const e = await fetchEventDetail(eventId);
    setSelected(e);
  }, []);

  useEffect(() => {
    refreshList();
    refreshDevices();
  }, [refreshList, refreshDevices]);

  useEffect(() => {
    if (selectedId && selectedSource === "live") loadDetail(selectedId);
  }, [selectedId, selectedSource, loadDetail]);


  useEffect(() => {
    const es = makeEventSource();

    const handlePayload = async (raw) => {
      try {
        const data = JSON.parse(raw.data);

        if (data?.kind === "new_event") {
          const cid = data?.event?.client_id ?? "-";
          const loc = data?.event?.location_name ?? "-";

          setUnseenByClient((prev) => {
            const next = { ...(prev || {}) };
            if (selectedClientId !== cid) {
              next[cid] = (next[cid] || 0) + 1;
            }
            return next;
          });

          setToast(`새 이벤트: ${cid} · ${loc}`);

          await refreshList();
        }

        if (data?.kind === "client_status") {
          setDevices(data?.clients || []);
        }
      } catch {
        // ignore parse errors
      }
    };

    es.addEventListener("new_event", handlePayload);
    es.addEventListener("client_status", handlePayload);

    es.addEventListener("message", handlePayload);

    es.onerror = () => {
      setToast("스트림 연결 문제 발생 (새로고침/재연결 필요)");
      try {
        es.close();
      } catch {}
    };

    return () => {
      try {
        es.close();
      } catch {}
    };
  }, [refreshList, selectedClientId]);

  // ---------
  // device select
  // ---------
  const onSelectDevice = useCallback(
    (cid) => {
      setSelectedClientId(cid);
      setSelectedSource("live");

      setUnseenByClient((prev) => {
        const next = { ...(prev || {}) };
        if (cid === "ALL") {
          return {}; // ALL 보면 전체 해제
        }
        delete next[cid];
        return next;
      });

      const list = cid === "ALL" ? events : events.filter((e) => e?.client_id === cid);
      if (list.length) setSelectedId(list[0].event_id);
    },
    [events]
  );

  const onSearchHistory = useCallback(
    async ({ start, end }) => {
      const data = await fetchHistoryEvents({
        start,
        end,
        clientId: selectedClientId ?? "ALL",
        limit: 200,
      });
      setHistoryEvents(data || []);

      if (data?.length) {
        setSelectedSource("history");
        setSelectedId(data[0].event_id);
        setSelected(data[0]);
      }
    },
    [selectedClientId, selectedId]
  );


  const onSelectHistoryItem = useCallback((ev) => {
    if (!ev) return;
    setSelectedSource("history");
    setSelectedId(ev.event_id);
    setSelected(ev);
  }, []);

  const liveView = useMemo(() => {
    if (selectedClientId === "ALL") return events || [];
    return (events || []).filter((e) => e?.client_id === selectedClientId);
  }, [events, selectedClientId]);

  const historyView = useMemo(() => {
    if (selectedClientId === "ALL") return historyEvents || [];
    return (historyEvents || []).filter((e) => e?.client_id === selectedClientId);
  }, [historyEvents, selectedClientId]);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "360px 420px 1fr",
        height: "100vh",
      }}
    >
      <Toast message={toast} onClose={() => setToast("")} />

      <DeviceList
        devices={devices}
        selectedClientId={selectedClientId}
        onSelect={onSelectDevice}
        unseenByClient={unseenByClient}
      />

      <EventList
        events={liveView}
        historyEvents={historyView}
        selectedId={selectedId}
        onSelect={(id) => {
          setSelectedSource("live");
          setSelectedId(id);
        }}
        onSelectHistory={onSelectHistoryItem}
        unseenCount={unseenCount}
        onSearchHistory={onSearchHistory}
        onClearHistory={() => setHistoryEvents([])}
      />

      <EventDetail event={selected} />
    </div>
  );
}
