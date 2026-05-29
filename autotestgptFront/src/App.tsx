import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import NewTest from './pages/NewTest'
import Requirements from './pages/Requirements'
import TestCases from './pages/TestCases'
import Executions from './pages/Executions'
import RequirementDetail from './pages/RequirementDetail'
import Chat from './pages/Chat'
import CodeReviews from './pages/CodeReviews'
import KnowledgeBases from './pages/KnowledgeBases'
import AgentWorkbench from './pages/AgentWorkbench'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="new" element={<NewTest />} />
          <Route path="reviews" element={<CodeReviews />} />
          <Route path="knowledge-bases" element={<KnowledgeBases />} />
          <Route path="requirements" element={<Requirements />} />
          <Route path="requirements/:id" element={<RequirementDetail />} />
          <Route path="workbench" element={<AgentWorkbench />} />
          <Route path="workbench/:requirementId" element={<AgentWorkbench />} />
          <Route path="cases" element={<TestCases />} />
          <Route path="executions" element={<Executions />} />
          <Route path="chat" element={<Chat />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
