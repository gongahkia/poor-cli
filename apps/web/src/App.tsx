import { Route, Routes } from "react-router-dom";

import { DashboardPage } from "@/pages/DashboardPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="*" element={<DashboardPage />} />
    </Routes>
  );
}
