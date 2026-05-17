import { Route, Routes } from "react-router-dom";

import { ToastProvider } from "@/components/notifications/ToastProvider";
import { CounterpartyPage } from "@/pages/CounterpartyPage";
import { SearchPage } from "@/pages/SearchPage";

export function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/c/:identifier" element={<CounterpartyPage />} />
      </Routes>
    </ToastProvider>
  );
}
