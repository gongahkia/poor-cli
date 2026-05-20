import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { ToastProvider } from "@/components/notifications/ToastProvider";

const SearchPage = lazy(() => import("@/pages/SearchPage").then((module) => ({ default: module.SearchPage })));
const CounterpartyPage = lazy(() => import("@/pages/CounterpartyPage").then((module) => ({ default: module.CounterpartyPage })));
const WorkspacePage = lazy(() => import("@/pages/WorkspacePage").then((module) => ({ default: module.WorkspacePage })));

function RouteFallback() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-7xl items-center px-6 text-sm text-muted-foreground">
      Loading Dude...
    </main>
  );
}

export function App() {
  return (
    <ToastProvider>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/c/:identifier" element={<CounterpartyPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
        </Routes>
      </Suspense>
    </ToastProvider>
  );
}
