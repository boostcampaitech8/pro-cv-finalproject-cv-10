import React, { useEffect } from "react";

export default function Toast({ message, onClose }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onClose, 1800);
    return () => clearTimeout(t);
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div style={{
      position: "fixed", top: 14, right: 14,
      background: "#111", color: "#fff",
      padding: "10px 12px", borderRadius: 10,
      boxShadow: "0 8px 20px rgba(0,0,0,0.2)"
    }}>
      {message}
    </div>
  );
}
