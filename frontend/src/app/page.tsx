import dynamic from 'next/dynamic';

// DVMCanvas uses Cytoscape which is browser-only — load the entire app
// shell without SSR so we never try to instantiate it on the server.
const MainApp = dynamic(() => import('@/components/MainApp'), { ssr: false });

export default function Home() {
  return <MainApp />;
}
