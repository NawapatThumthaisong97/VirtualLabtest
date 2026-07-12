import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { applyTheme } from "./modules/theme.js";
import "./styles.css";

applyTheme(document.documentElement);

// theme.js is a plain module (no React component), so without an explicit accept()
// boundary Vite falls back to a full page reload on edit - that would reset any
// playing track. Accept it here so editing the student's theme.js hot-swaps live.
if (import.meta.hot) {
  import.meta.hot.accept("./modules/theme.js", (mod) => {
    mod?.applyTheme(document.documentElement);
  });
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
