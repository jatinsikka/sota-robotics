import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "sota-robotics — live SOTA tracker",
  description:
    "Robotics-native, full-embodiment SOTA tracker. Rankings always surface eval conditions, sim vs real, and origin.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
