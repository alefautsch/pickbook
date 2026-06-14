import type { Metadata, Viewport } from "next";
import { FontBootstrap } from "@/components/FontBootstrap";
import { FONT_IDS } from "@/lib/fonts";
import { htmlFontClassName } from "@/lib/fontFaces";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dynasty Blackbook",
  description: "Personal dynasty research hub",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

const fontBootstrapScript = `(function(){try{var k="bb-font-preference";var f=localStorage.getItem(k);var ok=${JSON.stringify(FONT_IDS)};if(f&&ok.indexOf(f)!==-1)document.documentElement.dataset.font=f}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${htmlFontClassName} h-full antialiased`}
      data-font="geist"
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: fontBootstrapScript }} />
      </head>
      <body className="flex min-h-full flex-col overflow-x-hidden">
        <FontBootstrap />
        {children}
      </body>
    </html>
  );
}
