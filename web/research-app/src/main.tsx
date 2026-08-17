import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PreregistrationWorkbench } from "./preregistration-workbench";
import { ResearchApp } from "./research-app";
import "./styles.css";
import "./preregistration-workbench.css";

const root = document.getElementById("root");
if (!root) throw new Error("RESEARCH_ROOT_MISSING");

createRoot(root).render(
  <StrictMode>
    <ResearchApp />
    <PreregistrationWorkbench />
  </StrictMode>,
);
