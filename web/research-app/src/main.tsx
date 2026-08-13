import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ResearchApp } from "./research-app";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("RESEARCH_ROOT_MISSING");

createRoot(root).render(
  <StrictMode>
    <ResearchApp />
  </StrictMode>,
);
