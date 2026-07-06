import { createBrowserRouter, createRoutesFromElements, Route, RouterProvider } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Scan from "./pages/Scan";
import Scans from "./pages/Scans";
import History from "./pages/History";
import Operations from "./pages/Operations";
import FicheDetail from "./pages/FicheDetail";
import Assistant from "./pages/Assistant";

// A data router (vs plain <BrowserRouter>) is required for useBlocker, which
// FicheDetail uses to ask "save or discard?" before navigating away from an
// unsaved edit.
const router = createBrowserRouter(
  createRoutesFromElements(
    <Route element={<Layout />}>
      <Route path="/" element={<Dashboard />} />
      <Route path="/scanner" element={<Scan />} />
      <Route path="/suivi" element={<Scans />} />
      <Route path="/historique" element={<History />} />
      <Route path="/operations" element={<Operations />} />
      <Route path="/assistant" element={<Assistant />} />
      <Route path="/fiches/:id" element={<FicheDetail />} />
    </Route>
  )
);

export default function App() {
  return <RouterProvider router={router} />;
}
