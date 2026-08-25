import { createRoot } from "react-dom/client";

import { AppShell } from "./AppShell";
import "./styles-legacy.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<AppShell />);
