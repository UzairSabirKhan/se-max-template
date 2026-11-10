import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Toaster } from "./components/ui";
import { FlowsPage } from "./pages/FlowsPage";
import { FlowPage } from "./pages/FlowPage";

export default function App() {
  return (
    <>
      <AppShell>
        <Routes>
          <Route path="/" element={<FlowsPage />} />
          <Route path="/flows/:id" element={<FlowPage />} />
          <Route path="/flows/:id/:tab" element={<FlowPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
      <Toaster />
    </>
  );
}
