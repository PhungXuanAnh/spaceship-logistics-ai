import "../styles/globals.css";
import { Providers } from "@/lib/providers";

export const metadata = {
  title: "Spaceship Logistics AI",
  description: "AI-powered logistics analytics dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
