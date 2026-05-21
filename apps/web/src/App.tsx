import { Route, Routes } from "react-router-dom";

import { CounterpartyPage } from "@/pages/CounterpartyPage";
import { SearchPage } from "@/pages/SearchPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<SearchPage />} />
      <Route path="/c/:identifier" element={<CounterpartyPage />} />
      <Route path="/case/:caseId" element={<CounterpartyPage />} />
      <Route path="*" element={<SearchPage />} />
    </Routes>
  );
}
