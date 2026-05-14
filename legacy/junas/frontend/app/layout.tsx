import type { Metadata } from "next";
import SideNav from "../components/side-nav";
import ToastContainer from "../components/toast-container";
import { ThemeProvider } from "../lib/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Junas",
  description: "Legal AI platform — multi-jurisdiction retrieval, AI chat, contract analysis, and more.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&display=swap" rel="stylesheet" />
        <script dangerouslySetInnerHTML={{ __html: `try{if(localStorage.getItem("junas-theme")==="dark"||(!localStorage.getItem("junas-theme")&&window.matchMedia("(prefers-color-scheme:dark)").matches)){document.documentElement.classList.add("dark")}}catch(e){}` }} />
      </head>
      <body>
        <ThemeProvider>
          <div className="shell">
            <SideNav />
            <main className="content">{children}</main>
          </div>
          <ToastContainer />
        </ThemeProvider>
      </body>
    </html>
  );
}
