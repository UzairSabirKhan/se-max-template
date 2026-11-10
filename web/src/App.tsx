import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Toaster } from "./components/ui";
import { DataPage } from "./pages/DataPage";
import { FlowsPage } from "./pages/FlowsPage";
import { FlowPage } from "./pages/FlowPage";

/** Old links to a flow's Data tab now open the Data page on that flow. */
function DataRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/data?flow=${encodeURIComponent(id)}`} replace />;
}

export default function App() {
  return (
    <>
      <AppShell>
        <Routes>
          <Route path="/" element={<FlowsPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/flows/:id/data" element={<DataRedirect />} />
          <Route path="/flows/:id" element={<FlowPage />} />
          <Route path="/flows/:id/:tab" element={<FlowPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
      <Toaster />
    </>
  );
}
