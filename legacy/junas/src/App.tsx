import { ErrorBoundary } from "@/components/ErrorBoundary";
import { JunasProvider } from "@/lib/context/JunasContext";
import Home from "@/app/page";
export default function App() {
  return (
    <ErrorBoundary>
      <JunasProvider>
        <Home />
      </JunasProvider>
    </ErrorBoundary>
  );
}
