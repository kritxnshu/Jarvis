import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./design/tokens.css";
import { App } from "./app/App";
import { BridgeProvider } from "./app/BridgeContext";
import { createTauriBridge } from "./bridge/tauri";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root element");

createRoot(root).render(
  <StrictMode>
    <BridgeProvider bridge={createTauriBridge()}>
      <App />
    </BridgeProvider>
  </StrictMode>,
);
