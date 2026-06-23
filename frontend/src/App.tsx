import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Scan from "./pages/Scan";
import History from "./pages/History";
import FicheDetail from "./pages/FicheDetail";
import Assistant from "./pages/Assistant";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/scanner" element={<Scan />} />
        <Route path="/historique" element={<History />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/fiches/:id" element={<FicheDetail />} />
      </Routes>
    </Layout>
  );
}
