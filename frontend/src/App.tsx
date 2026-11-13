import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppProvider } from './context/AppProvider'
import { AppLayout } from './layouts/AppLayout'
import { ChatPage } from './pages/ChatPage'
import { DashboardPage } from './pages/DashboardPage'
import { GraphExplorerPage } from './pages/GraphExplorerPage'
import { InspectorPage } from './pages/InspectorPage'
import { QuizPage } from './pages/QuizPage'
import { SettingsPage } from './pages/SettingsPage'
import { SummarizerPage } from './pages/SummarizerPage'

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="chat/:threadId?" element={<ChatPage />} />
            <Route path="quiz" element={<QuizPage />} />
            <Route path="summarize" element={<SummarizerPage />} />
            <Route path="graph" element={<GraphExplorerPage />} />
            <Route path="inspector" element={<InspectorPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<DashboardPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}
